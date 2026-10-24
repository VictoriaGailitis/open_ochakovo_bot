"""Private causal assessment for the educational shift simulator.

Only public readings are shipped in catalog.json. Sufficient evidence categories,
accepted claims, and result explanations stay on the server. Freeform notes are
preserved for reflection; this module does not pretend to assess their meaning.
"""


RULES = {
    'shift-1': {
        'observedChange': 'packaging_restriction',
        'explanation': 'packaging_setting',
        'nextStep': 'report_coordinate_packaging',
        'responsible': 'packaging_specialist',
        'localizationPaths': [
            [{'scheme-flow'}],
            [{'metric-packaging', 'history-packaging'}, {'metric-queue', 'history-queue'}],
            [{'metric-packaging', 'history-packaging'}, {'metric-feed', 'history-feed'}],
        ],
        'causeFacts': {'journal-mode', 'check-settings'},
        'contradictoryFacts': {'journal-hypothesis'},
        'explanationText': 'Упаковочный участок снизил темп до 42 упак./мин после изменения настройки в 14:06:40. Подача осталась 60 упак./мин, а очередь перед упаковкой выросла с 4 до 18. Настройка и наблюдаемый поток согласуются; проверка не подтверждает пропуски выходного датчика. Подтверждённые данные нужно передать ответственному специалисту и согласовать темп участков по установленному порядку. Самостоятельное изменение настройки не является действием игрока.',
        'outcome': {
            'summary': 'Учебная модель: команда получила обоснованное сообщение и согласовала работу участков.',
            'before': 'Упаковка и выход — 42 упак./мин при подаче 60; очередь — 18 упаковок.',
            'after': 'После проверки и согласования уполномоченными специалистами модель показывает согласованный темп подачи и упаковки. Очередь больше не растёт; игрок не выполняет ремонт или самостоятельный перезапуск.',
        },
    },
    'shift-2': {
        'observedChange': 'upstream_shortage',
        'explanation': 'feed_interruption',
        'nextStep': 'report_coordinate_supply',
        'responsible': 'upstream_coordinator',
        'localizationPaths': [
            [{'scheme-flow'}],
            [{'metric-feed', 'history-feed'}, {'metric-queue', 'history-queue'}],
            [{'metric-feed', 'history-feed'}, {'metric-capping', 'history-capping', 'metric-packaging', 'history-packaging'}],
        ],
        'causeFacts': {'journal-feed', 'check-feed'},
        'contradictoryFacts': {'journal-hypothesis'},
        'explanationText': 'В этом раунде первым сократился входной поток с предыдущего участка: с 60 до 42 упак./мин. Очередь перед упаковкой иссякла; укупорка и упаковка следуют доступной подаче. Журнал и проверка подтверждают перерыв подачи, а настройка упаковки остаётся 60 упак./мин. Повторение решения прошлого раунда не устранит причину. Нужно передать данные мастеру и ответственному за подачу и согласовать восстановление снабжения.',
        'outcome': {
            'summary': 'Учебная модель: команда получила сообщение о подаче с предыдущего участка.',
            'before': 'На входе, укупорке и упаковке — 42 упак./мин; очередь перед упаковкой — 0.',
            'after': 'После согласования снабжения мастер и ответственный за подачу восстанавливают согласованный поток в учебной модели. Менять исправную настройку упаковки игроку не требуется.',
        },
    },
}


def normalize_draft(task, draft):
    """Keep canonical source metadata, user notes, and all other UI draft fields."""
    if not isinstance(draft, dict):
        raise ValueError('Некорректный черновик смены.')
    observations = draft.get('observations', [])
    if not isinstance(observations, list) or len(observations) > 32:
        raise ValueError('Можно сохранить до 32 наблюдений.')
    facts = {fact['id']: fact for fact in task['puzzle']['facts']}
    seen = set()
    normalized = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError('Наблюдение должно содержать идентификатор факта.')
        fact_id = observation.get('factId')
        if not isinstance(fact_id, str) or fact_id not in facts or fact_id in seen:
            raise ValueError('Факт наблюдения неизвестен или уже закреплён.')
        note = observation.get('note', '')
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError('Заметка к наблюдению должна содержать не более 2 000 символов.')
        seen.add(fact_id)
        fact = facts[fact_id]
        normalized.append({'factId': fact_id, 'source': fact['source'], 'time': fact['time'], 'fact': fact['text'], 'note': note})
    hypothesis = draft.get('hypothesis', '')
    if not isinstance(hypothesis, str) or len(hypothesis) > 4000:
        raise ValueError('Гипотеза должна содержать не более 4 000 символов.')
    return {**draft, 'observations': normalized}


def assess(task, solution, observation_ids=None):
    """Assess causal categories rather than an exact list of clicked cards."""
    rule = RULES.get(task['id'])
    if not rule or not isinstance(solution, dict):
        return ['Некорректный вывод для сценария смены.']
    evidence = solution.get('evidence')
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 32 or not all(isinstance(fact_id, str) for fact_id in evidence):
        return ['Выберите основания из своих сохранённых наблюдений.']
    selected = set(evidence)
    if len(selected) != len(evidence):
        return ['Каждый факт нужно указывать в основаниях только один раз.']
    known = {fact['id'] for fact in task['puzzle']['facts']}
    if not selected <= known:
        return ['В основаниях есть неизвестные данные. Используйте факты этого раунда.']
    if observation_ids is not None and not selected <= set(observation_ids):
        return ['Сначала закрепите выбранные факты в «Моих наблюдениях», затем используйте их в выводе.']
    errors = []
    if solution.get('observedChange') != rule['observedChange']:
        errors.append('Локализация не согласуется с данными. Сравните поток на соседних участках и изменение очереди.')
    localized = any(all(bool(selected & category) for category in path) for path in rule['localizationPaths'])
    if not localized:
        errors.append('Оснований для локализации пока недостаточно: сопоставьте соседние потоки и очередь или закрепите наблюдение схемы.')
    if solution.get('explanation') != rule['explanation']:
        errors.append('Объяснение противоречит материалам этого раунда. Сопоставьте время изменения с журналом и проверками.')
    if not selected & rule['causeFacts']:
        errors.append('Причина пока не подтверждена: найдите запись или независимую проверку, которая объясняет изменение.')
    if selected & rule['contradictoryFacts']:
        errors.append('Непроверенное предположение коллеги не является подтверждением причины и не согласуется с результатом проверки. Уберите его из оснований или пересмотрите вывод.')
    if solution.get('nextStep') != rule['nextStep']:
        errors.append('Следующий шаг должен передавать проверенные данные команде и согласовывать действия в рамках роли. Самостоятельное вмешательство не требуется.')
    if solution.get('responsible') != rule['responsible']:
        errors.append('Уточните ответственного за участок и согласование действий. Игрок не выполняет самостоятельный ремонт или перезапуск.')
    return errors


def completion_details(task):
    rule = RULES[task['id']]
    return {'explanation': rule['explanationText'], 'outcome': dict(rule['outcome']), 'assessment': {'localization': 10, 'cause': 10, 'nextStep': 10}}
