import json
import math
from django.core.exceptions import ValidationError
from server.level_rules import LevelRuleRegistry, LevelRuleError
from server.solutions import validate

def require(condition, message):
    if not condition:
        raise ValidationError(message)

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def whole(value, minimum=0, maximum=1000):
    return type(value) is int and minimum <= value <= maximum

def ids(items, name='ID'):
    require(isinstance(items, list) and len(items) <= 200, f'{name}: нужен список до 200 элементов.')
    values = [item.get('id') for item in items if isinstance(item, dict)]
    require(len(values) == len(items) and all((isinstance(v, str) and v.strip() for v in values)) and (len(set(values)) == len(values)), f'{name}: ID должны быть непустыми и уникальными.')
    return set(values)

def point(p, width, height):
    return isinstance(p, dict) and whole(p.get('x'), 0, width - 1) and whole(p.get('y'), 0, height - 1)

def value_format(value):
    require(isinstance(value,dict) and set(value)<= {'minimumFractionDigits','maximumFractionDigits','suffix','compactSuffix','comparisonSuffix'},'Неизвестное поле формата значения.')
    for key in ('minimumFractionDigits','maximumFractionDigits'):
        if key in value:require(whole(value[key],0,20),'Количество десятичных знаков: 0–20.')
    require(value.get('minimumFractionDigits',0)<=value.get('maximumFractionDigits',max(value.get('minimumFractionDigits',0),2)),'Минимум знаков превышает максимум.')
    for key in ('suffix','compactSuffix','comparisonSuffix'):
        if key in value:require(isinstance(value[key],str) and len(value[key])<=100,'Подпись единиц должна быть коротким текстом.')

def validate_task(task, private_rule=None):
    require(isinstance(task, dict) and isinstance(task.get('puzzle'), dict), 'Нужно определение задачи.')
    require(whole(task.get('points'), 1, 1000) and whole(task.get('level'), 1, 1000), 'Проверьте баллы и номер уровня.')
    p, g = (task['puzzle'], task['game'])
    try:
        if g == 'signal':
            require(1 <= len(p['stream']) <= 100, 'Поток: 1–100 упаковок.')
            require(all((i['color'] in ('red', 'blue') and type(i['marked']) is bool for i in p['stream'])), 'Проверьте признаки потока.')
            require(p['rule'] in ('color', 'mark', 'combined') and whole(p['maxRules'], 1, 3), 'Недопустимый вид правила.')
            require(bool(p['allowedConditions']) and set(p['allowedConditions']) <= {'red', 'blue', 'marked', 'unmarked', 'red_marked', 'always'}, 'Неизвестное условие.')
            require(set(p['outputs']) == {'left', 'right'}, 'Нужны выходы left и right.')
        elif g == 'movement':
            require(whole(p['width'], 2, 12) and whole(p['height'], 1, 12), 'Поле: до 12×12.')
            require(point(p['source'], p['width'], p['height']) and point(p['target'], p['width'], p['height']), 'Источник и цель должны быть в поле.')
            require((p['source']['x'], p['source']['y']) != (p['target']['x'], p['target']['y']), 'Источник и цель не совпадают.')
            require(p['source']['direction'] in (-1, 1) and p['target']['direction'] in (-1, 1) and whole(p['maxGears'], 1, 100), 'Проверьте передачу вращения.')
            require(whole(p.get('maxBelts', 0), 0, 30), 'Лимит ремней 0–30.')
            pairs = set()
            for b in p.get('beltLinks', []):
                require(point(b['from'], p['width'], p['height']) and point(b['to'], p['width'], p['height']), 'Вал ремня вне поля.')
                pair = tuple(sorted([(b['from']['x'], b['from']['y']), (b['to']['x'], b['to']['y'])]))
                require(pair[0] != pair[1] and pair not in pairs, 'Повтор или самосоединение ремня.')
                pairs.add(pair)
        elif g == 'lab':
            ids(p['samples'], 'Образцы')
            tests = ids(p['tests'], 'Исследования')
            require(2 <= len(p['samples']) <= 30 and 1 <= len(tests) <= 10, 'Нужно 2–30 образцов, 1–10 исследований.')
            require(set(p['observations']) == tests and all((set(s['properties']) == tests for s in p['samples'])), 'Свойства всех образцов и наблюдений должны соответствовать исследованиям.')
        elif g == 'delivery':
            require(whole(p['width'], 1, 12) and whole(p['height'], 1, 12), 'Проверьте размеры площадки.')
            w, h = (p['warehouse']['width'], p['warehouse']['height'])
            require(whole(w, 1, 12) and whole(h, 1, 12) and point(p['start'], w, h), 'Проверьте склад и вход.')
            ids(p['batches'], 'Партии')
            products = []
            for b in p['batches']:
                require(point(b['location'], w, h) and type(b['reserved']) is bool and isinstance(b['product'], str), 'Проверьте партию.')
                require(1 <= len(b['cells']) <= 30 and all((len(c) == 2 and all((whole(v, 0, 11) for v in c)) for c in b['cells'])), 'Проверьте клетки упаковки.')
                require(len({tuple(c) for c in b['cells']}) == len(b['cells']), 'Повтор клетки упаковки.')
            for order in p['order']:
                require(isinstance(order['product'], str) and whole(order['quantity'], 1, 30), 'Проверьте заказ.')
                products.append(order['product'])
            require(bool(products) and len(set(products)) == len(products), 'Товары заказа должны различаться.')
        elif g == 'history':
            ids(p['questions'], 'Вопросы')
            require(1 <= len(p['questions']) <= 20, 'Нужно 1–20 вопросов.')
            for question in p['questions']:
                ids(question['options'], 'Варианты')
                require(2 <= len(question['options']) <= 6, 'Нужно 2–6 ответов.')
        elif g == 'shift':
            facts = ids(p['facts'], 'Факты')
            ids(p['metrics'], 'Показатели')
            nodes = ids(p['scheme']['nodes'], 'Узлы')
            ids(p['scheme']['flows'], 'Потоки')
            ids(p['journal'], 'Журнал')
            ids(p['checks'], 'Проверки')
            require(1 <= len(p['metrics']) <= 24 and bool(p['hints']), 'Добавьте показатели и подсказки.')
            metric_ids={m['id'] for m in p['metrics']}
            for node in p['scheme']['nodes']:
                require(finite(node['value']),'Значение узла должно быть числом.')
                require(node.get('display','card') in ('card','queue','extra'),'Неизвестный вид узла схемы.')
                if 'position' in node:
                    pos=node['position'];require(isinstance(pos,dict) and set(pos)=={'x','y'} and finite(pos['x']) and finite(pos['y']) and 0<=pos['x']<=350 and 0<=pos['y']<=270,'Координаты узла: x 0–350, y 0–270.')
                require(not node.get('metricId') or node['metricId'] in metric_ids,'Узел ссылается на неизвестный показатель.')
                if 'format' in node:value_format(node['format'])
            for flow in p['scheme']['flows']:
                require(flow['from']!=flow['to'],'Поток должен связывать разные узлы.')
                if 'primary' in flow:require(type(flow['primary']) is bool,'Основной поток: да или нет.')
            require(sum(bool(f.get('primary')) for f in p['scheme']['flows'])<=1,'Выберите не больше одного основного потока.')
            for metric in p['metrics']:
                if 'format' in metric:value_format(metric['format'])
                if 'highlight' in metric:require(type(metric['highlight']) is bool,'Выделение показателя: да или нет.')
                require(finite(metric['value']) and finite(metric['previous']) and (1 <= len(metric['series']) <= 200), 'Проверьте значения показателя.')
                require(all((finite(v['value']) and isinstance(v['time'], str) for v in metric['series'])), 'Проверьте временной ряд.')
            entities = p['metrics'] + p['scheme']['nodes'] + p['scheme']['flows'] + p['journal'] + p['checks']
            require(all((e['factId'] in facts for e in entities)), 'Ссылка на неизвестный факт.')
            require(all((not m.get('historyFactId') or m['historyFactId'] in facts for m in p['metrics'])), 'Неизвестный факт графика.')
            require(all((f['from'] in nodes and f['to'] in nodes for f in p['scheme']['flows'])), 'Поток ссылается на неизвестный узел.')
            for group in ('observedChange', 'explanation', 'nextStep', 'responsible'):
                ids(p['conclusion'][group], group)
        else:
            raise ValidationError('Неизвестная механика.')
        if g in ('history', 'shift'):
            require(private_rule is not None, 'Для этой механики требуется приватное правило.')
            registry = LevelRuleRegistry({'schemaVersion': 1, 'levels': {task['id']: 'rule'}, 'rules': {'rule': private_rule}})
            require(registry.resolve(task) is not None, 'Закрытое правило не согласуется с сущностями задачи.')
        else:
            registry = None
        return registry
    except (KeyError, TypeError, IndexError, ValueError, LevelRuleError) as error:
        raise ValidationError('Неполная или некорректная схема задачи/приватного правила.') from error

def validate_fixtures(task, fixtures, private_rule=None):
    registry = validate_task(task, private_rule)
    require(isinstance(fixtures, dict) and set(fixtures) == {'positive', 'negative'}, 'Добавьте правильные и ошибочные проверочные решения.')
    require(all((isinstance(fixtures[k], list) and 1 <= len(fixtures[k]) <= 20 for k in ('positive', 'negative'))), 'Нужны 1–20 решений каждого вида.')
    for expected in fixtures['positive']:
        errors = validate(task, expected, registry)
        require(not errors, 'Правильный пример не проходит серверную оценку: ' + '; '.join(errors))
    for negative in fixtures['negative']:
        require(bool(validate(task, negative, registry)), 'Ошибочный пример неожиданно засчитывается.')
    return {'positive': len(fixtures['positive']), 'negative': len(fixtures['negative']), 'solvable': True}
