"""Integration tests for causal investigation, not an exact-card-count quiz."""
import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from server.app import API, APIError, CATALOG, Store
from server.shift import assess


PROFILE={'fullName':'Тестовый исследователь','contact':'shift@example.org','birthDate':'2004-06-12','direction':'production','availability':'На практике','education':'Учебный колледж','consent':True}


def correct_solution(task_id='shift-1'):
    if task_id=='shift-1':
        return {'observedChange':'packaging_restriction','explanation':'packaging_setting','evidence':['metric-packaging','history-queue','journal-mode'],'nextStep':'report_coordinate_packaging','responsible':'packaging_specialist'}
    return {'observedChange':'upstream_shortage','explanation':'feed_interruption','evidence':['metric-feed','history-queue','journal-feed'],'nextStep':'report_coordinate_supply','responsible':'upstream_coordinator'}


class ShiftTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'shift.db'
        self.api=API(Store(self.path),{'DEV_AUTH':'1'})
        auth=self.api.auth({'devUserId':'investigator'},'127.0.0.1')
        self.headers={'Authorization':'Bearer '+auth['token']}
        self.call('PUT','/api/profile',PROFILE)
    def tearDown(self):self.temp.cleanup()
    def call(self,method,path,body=None):return self.api.dispatch(method,path,body,self.headers)
    def task(self,id='shift-1'):return next(task for task in CATALOG['tasks'] if task['id']==id)
    def save_evidence(self,evidence,task_id='shift-1',note='Моя заметка'):
        observations=[{'factId':fact_id,'note':note} for fact_id in evidence]
        return self.call('PUT',f'/api/tasks/{task_id}/draft',{'draft':{'observations':observations,'hypothesis':'Моя проверяемая гипотеза'}})
    def complete(self,attempt,task_id='shift-1'):
        return self.call('POST',f'/api/tasks/{task_id}/complete',{'solution':attempt})

    def test_multiple_sufficient_paths_and_normal_extras_are_accepted(self):
        task=self.task()
        paths=[['metric-packaging','history-queue','journal-mode'],
               ['scheme-flow','journal-mode','check-settings'],
               ['history-packaging','metric-feed','check-settings'],
               ['scheme-flow','check-settings'],
               ['metric-packaging','metric-queue','journal-mode','metric-temperature','check-quality','journal-report']]
        for evidence in paths:
            attempt={**correct_solution(),'evidence':evidence}
            self.assertEqual(assess(task,attempt),[],evidence)
            self.save_evidence(evidence)
            result=self.complete(attempt)
            self.assertTrue(result['correct'],result)
            self.assertEqual(result['assessment'],{'localization':10,'cause':10,'nextStep':10})
            self.assertTrue(result['outcome']['before'])
            self.assertTrue(result['outcome']['after'])
        self.assertEqual(self.call('GET','/api/bootstrap')['balance'],30)

    def test_insufficient_contradictory_forged_and_unsafe_conclusions_fail(self):
        variants=[
            {**correct_solution(),'evidence':['journal-mode']},
            {**correct_solution(),'evidence':['metric-packaging','history-queue']},
            {**correct_solution(),'evidence':['metric-output','metric-signals','metric-temperature']},
            {**correct_solution(),'evidence':['metric-packaging','history-queue','journal-mode','journal-hypothesis']},
            {**correct_solution(),'evidence':['scheme-flow','check-settings','made-up-fact']},
            {**correct_solution(),'observedChange':'sensor_failure'},
            {**correct_solution(),'explanation':'sensor_misses'},
            {**correct_solution(),'nextStep':'self_raise_limit'},
            {**correct_solution(),'nextStep':'bypass_sensor'},
            {**correct_solution(),'responsible':'player_alone'},
        ]
        for attempt in variants:
            with self.subTest(attempt=attempt):
                known={f['id'] for f in self.task()['puzzle']['facts']}
                self.save_evidence([f for f in attempt['evidence'] if f in known])
                result=self.complete(attempt)
                self.assertFalse(result['correct'])
                self.assertTrue(result['errors'])
        bootstrap=self.call('GET','/api/bootstrap')
        self.assertEqual(bootstrap['balance'],0)
        self.assertTrue(all(not item['completed'] for item in bootstrap['progress']))

    def test_evidence_must_be_from_own_saved_observations(self):
        result=self.complete(correct_solution())
        self.assertFalse(result['correct'])
        self.assertIn('наблюдениях',' '.join(result['errors']))
        self.save_evidence(['metric-packaging','history-queue'])
        self.assertFalse(self.complete(correct_solution())['correct'])
        self.save_evidence(correct_solution()['evidence'])
        self.assertTrue(self.complete(correct_solution())['correct'])

    def test_notes_are_preserved_canonically_and_not_magically_graded(self):
        evidence=correct_solution()['evidence']
        note='Проверю ещё раз; это мой свободный комментарий, а не оцениваемая строка.'
        fake={'factId':evidence[0],'source':'подменённый источник','time':'неверное время','fact':'подменённый факт','note':note}
        result=self.call('PUT','/api/tasks/shift-1/draft',{'draft':{'observations':[fake],'hypothesis':'Гипотеза своими словами'},'revision':123})
        stored=result['progress'][0]['draft']['observations'][0]
        canonical=next(f for f in self.task()['puzzle']['facts'] if f['id']==evidence[0])
        self.assertEqual(stored['source'],canonical['source'])
        self.assertEqual(stored['time'],canonical['time'])
        self.assertEqual(stored['fact'],canonical['text'])
        self.assertEqual(stored['note'],note)
        # Edit and remove cards, then reload a new API/DB connection.
        result=self.save_evidence(evidence,note=note)
        edited_note='Изменённая заметка после удаления лишней карточки'
        self.save_evidence(evidence[:2],note=edited_note)
        reopened=API(Store(self.path),{'DEV_AUTH':'1'})
        restored=reopened.dispatch('GET','/api/bootstrap',headers=self.headers)['progress'][0]['draft']
        self.assertEqual(len(restored['observations']),2)
        self.assertEqual(restored['observations'][0]['note'],edited_note)
        self.assertEqual(restored['hypothesis'],'Моя проверяемая гипотеза')
        self.save_evidence(evidence,note=edited_note)
        self.assertTrue(self.complete(correct_solution())['correct'])

    def test_observation_limits_and_unknown_fact_ids(self):
        # The cap is a practical safeguard, not a requirement to choose exactly a small set.
        full_set=[fact['id'] for fact in self.task()['puzzle']['facts'][:32]]
        self.assertEqual(len(full_set),32)
        result=self.save_evidence(full_set)
        self.assertEqual(len(result['progress'][0]['draft']['observations']),32)
        bad_drafts=[{'observations':[{'factId':'forged'}]},
                    {'observations':[{'factId':'metric-output'},{'factId':'metric-output'}]},
                    {'observations':[{'factId':'metric-output','note':'x'*2001}]},
                    {'observations':[{'factId':fact['id']} for fact in self.task()['puzzle']['facts'][:33]]},
                    {'observations':'not a list'},
                    {'observations':[],'hypothesis':'x'*4001}]
        for draft in bad_drafts:
            with self.assertRaises(APIError) as cm:self.call('PUT','/api/tasks/shift-1/draft',{'draft':draft})
            self.assertEqual(cm.exception.status,400)

    def test_repeat_variant_has_different_cause_and_evidence(self):
        first,second=self.task('shift-1'),self.task('shift-2')
        self.assertEqual(len(first['puzzle']['metrics']),12)
        self.assertEqual(len(second['puzzle']['metrics']),12)
        self.assertEqual(next(m for m in first['puzzle']['metrics'] if m['id']=='output')['value'],42)
        self.assertEqual(next(m for m in second['puzzle']['metrics'] if m['id']=='output')['value'],42)
        # The same symptom does not admit memorizing the first round's explanation.
        old_solution={**correct_solution(),'evidence':['metric-packaging','history-queue','check-settings']}
        self.save_evidence(old_solution['evidence'],'shift-2')
        self.assertFalse(self.complete(old_solution,'shift-2')['correct'])
        for path in [['metric-feed','history-queue','journal-feed'],['scheme-flow','check-feed','check-settings'],['history-feed','metric-capping','check-feed']]:
            attempt={**correct_solution('shift-2'),'evidence':path}
            self.save_evidence(path,'shift-2')
            self.assertTrue(self.complete(attempt,'shift-2')['correct'])
        self.assertEqual(self.call('GET','/api/bootstrap')['balance'],30)

    def test_concurrent_shift_completions_award_once(self):
        self.save_evidence(correct_solution()['evidence'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.complete(correct_solution()),range(12)))
        self.assertTrue(all(r['correct'] for r in results))
        self.assertEqual(sum(r['pointsAwarded'] for r in results),30)
        boot=self.call('GET','/api/bootstrap')
        self.assertEqual(len(boot['ledger']),1)
        self.assertEqual(boot['routeProgress']['total'],6)
        self.assertIn('shift-1',boot['routeProgress']['completedTaskIds'])
        self.assertFalse(boot['routeCompleted'])

    def test_graphs_show_causal_order_and_end_at_current_metric(self):
        def seconds(clock):
            hours,minutes,seconds=map(int,clock.split(':'))
            return hours*3600+minutes*60+seconds
        def first_change(metric):
            return next((seconds(point['time']) for point in metric['series'] if point['value']!=metric['previous']),None)
        def first_drop(metric):
            return next((seconds(point['time']) for point in metric['series'] if point['value']<metric['previous']),None)
        for task_id in ('shift-1','shift-2'):
            puzzle=self.task(task_id)['puzzle']
            metrics={metric['id']:metric for metric in puzzle['metrics']}
            facts={fact['id']:fact for fact in puzzle['facts']}
            for metric in metrics.values():
                with self.subTest(task=task_id,metric=metric['id']):
                    self.assertEqual(len(metric['series']),6)
                    timestamps=[seconds(point['time']) for point in metric['series']]
                    intervals=[right-left for left,right in zip(timestamps,timestamps[1:])]
                    self.assertTrue(all(interval>0 for interval in intervals))
                    self.assertGreater(len(set(intervals)),1) # Charts must use actual time spacing.
                    self.assertEqual(metric['series'][0]['value'],metric['previous'])
                    self.assertEqual(metric['series'][-1]['value'],metric['value'])
                    history=facts[metric['historyFactId']]
                    self.assertIn(metric['series'][0]['time'],history['time'])
                    self.assertIn(metric['series'][-1]['time'],history['time'])
                    for point in metric['series']:
                        self.assertIn(point['time'],history['text'])
            if task_id=='shift-1':
                packaging=first_drop(metrics['packaging'])
                self.assertEqual(packaging,seconds('14:06:40'))
                self.assertLess(packaging,first_drop(metrics['output']))
                self.assertLess(packaging,first_change(metrics['queue']))
                self.assertEqual(first_drop(metrics['output']),first_drop(metrics['signals']))
                self.assertIsNone(first_change(metrics['feed']))
                self.assertIsNone(first_change(metrics['capping']))
                self.assertGreater(metrics['queue']['value'],metrics['queue']['previous'])
            else:
                feed,capping,packaging,output=[first_drop(metrics[key]) for key in ('feed','capping','packaging','output')]
                self.assertEqual(feed,seconds('14:06:40'))
                self.assertLess(feed,capping)
                self.assertLess(capping,packaging)
                self.assertLess(packaging,output)
                self.assertLess(feed,first_drop(metrics['queue']))
                self.assertEqual(output,first_drop(metrics['signals']))
                self.assertEqual(metrics['queue']['value'],0)

    def test_public_puzzle_has_no_private_answer_rules_or_result(self):
        catalog=self.call('GET','/api/catalog')
        for task in catalog['tasks']:
            if task['game']!='shift':continue
            raw=json.dumps(task)
            for private_key in ('localizationPaths','causeFacts','contradictoryFacts','explanationText','outcome'):
                self.assertNotIn(private_key,raw)
            known={fact['id'] for fact in task['puzzle']['facts']}
            self.assertEqual(len(known),len(task['puzzle']['facts']))
            for metric in task['puzzle']['metrics']:
                self.assertIn(metric['factId'],known)
                self.assertIn(metric['historyFactId'],known)


if __name__=='__main__':unittest.main()
