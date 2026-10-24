"""Server-owned validators for the five distinct educational game mechanics."""
from collections import Counter, deque


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate(task, solution):
    if not isinstance(solution, dict):
        return ['Решение должно быть объектом.']
    puzzle, game = task['puzzle'], task['game']
    try:
        return globals()['validate_' + game](puzzle, solution)
    except (KeyError, TypeError, ValueError, IndexError):
        return ['Некорректный формат решения. Проверьте все элементы.']


def validate_signal(p, s):
    rules = s.get('rules')
    if not isinstance(rules, list) or not 1 <= len(rules) <= p['maxRules']:
        return ['Составьте алгоритм из 1–3 правил.']
    for r in rules:
        if not isinstance(r, dict) or r.get('condition') not in p['allowedConditions'] or r.get('output') not in p['outputs']:
            return ['Выберите допустимые условие и действие для каждого блока.']
    # Exhaustively test all input states, not just the sample stream shown by the client.
    conditions = {'red': lambda a:a['color']=='red', 'blue':lambda a:a['color']=='blue',
                  'marked':lambda a:a['marked'], 'unmarked':lambda a:not a['marked'],
                  'red_marked':lambda a:a['color']=='red' and a['marked'], 'always':lambda a:True}
    for color in ('red', 'blue'):
        for marked in (False, True):
            item = {'color':color, 'marked':marked}
            left = color == 'red' if p['rule']=='color' else marked if p['rule']=='mark' else color=='red' and marked
            expected = 'left' if left else 'right'
            actual = next((r['output'] for r in rules if conditions[r['condition']](item)), None)
            if actual != expected:
                return ['Некоторые упаковки направлены неверно или не обработаны. Проверьте порядок правил и правило для остальных случаев.']
    return []


def validate_movement(p, s):
    gears = s.get('gears')
    if not isinstance(gears, list) or not 1 <= len(gears) <= p['maxGears']:
        return ['Разместите доступные шестерни между приводом и целью.']
    source = (p['source']['x'],p['source']['y'])
    target = (p['target']['x'],p['target']['y'])
    cells = [source,target]
    for g in gears:
        if not isinstance(g,dict) or not all(integer(g.get(k)) for k in ('x','y')):
            return ['Некорректная координата шестерни.']
        if not 0 <= g['x'] < p['width'] or not 0 <= g['y'] < p['height']:
            return ['Шестерни должны находиться внутри поля.']
        cells.append((g['x'],g['y']))
    if len(set(cells))!=len(cells):
        return ['Шестерни не могут занимать одну клетку.']
    directions = {source:p['source']['direction']}
    pending = deque([source])
    while pending:
        cell = pending.popleft()
        for other in cells:
            if abs(cell[0]-other[0])+abs(cell[1]-other[1])!=1:
                continue
            direction = -directions[cell]
            if other in directions and directions[other]!=direction:
                return ['Механизм заблокирован противоположными передачами.']
            if other not in directions:
                directions[other]=direction
                pending.append(other)
    if target not in directions:
        return ['Нет непрерывного зацепления от привода до цели.']
    if len(directions)!=len(cells):
        return ['Одна из шестерён не соединена с механизмом.']
    if directions[target]!=p['target']['direction']:
        return ['Целевое колесо вращается в неверном направлении.']
    return []


def validate_lab(p,s):
    evidence = s.get('evidence')
    if not isinstance(evidence,list) or not 1 <= len(evidence) <= len(p['tests']) or len(set(evidence))!=len(evidence):
        return ['Выберите исследования, подтверждающие вывод.']
    if any(t not in p['observations'] for t in evidence):
        return ['Неизвестное исследование.']
    compatible = [sample for sample in p['samples'] if all(sample['properties'][key]==p['observations'][key] for key in evidence)]
    if len(compatible)!=1:
        return ['Этих наблюдений недостаточно: подходят несколько образцов. Выберите ещё одно исследование.']
    if compatible[0]['id']!=s.get('sampleId'):
        return ['Выбранный образец противоречит наблюдениям. Сравните признаки со справочником.']
    return []


def validate_delivery(p,s):
    placements,route=s.get('placements'),s.get('route')
    if not isinstance(placements,list) or not isinstance(route,list) or len(placements)>len(p['batches']) or len(route)>100:
        return ['Разместите партии и постройте маршрут.']
    batches={b['id']:b for b in p['batches']}
    selected,occupied,products=set(),set(),Counter()
    for place in placements:
        if not isinstance(place,dict) or place.get('batchId') not in batches or not all(integer(place.get(k)) for k in ('x','y')):
            return ['Некорректная партия или положение упаковки.']
        batch=batches[place['batchId']]
        if batch['reserved']:
            return ['Зарезервированная партия недоступна для комплектации.']
        if batch['id'] in selected:
            return ['Каждую партию можно взять только один раз.']
        if type(place.get('rotated',False)) is not bool:
            return ['Некорректный поворот упаковки.']
        selected.add(batch['id']);products[batch['product']]+=1
        for dx,dy in batch['cells']:
            if place.get('rotated',False): dx,dy=dy,dx
            cell=place['x']+dx,place['y']+dy
            if not (0<=cell[0]<p['width'] and 0<=cell[1]<p['height']):
                return ['Упаковка выходит за границу палеты.']
            if cell in occupied:
                return ['Упаковки пересекаются. Освободите место.']
            occupied.add(cell)
    if products!=Counter({o['product']:o['quantity'] for o in p['order']}):
        return ['Состав заказа не совпадает с заданием. Проверьте продукты и количество.']
    path=[]
    for point in route:
        if not isinstance(point,dict) or not all(integer(point.get(k)) for k in ('x','y')):
            return ['Некорректная точка маршрута.']
        cell=point['x'],point['y']
        if not 0<=cell[0]<p['warehouse']['width'] or not 0<=cell[1]<p['warehouse']['height']:
            return ['Маршрут выходит за границы склада.']
        if path and abs(path[-1][0]-cell[0])+abs(path[-1][1]-cell[1])!=1:
            return ['Соедините соседние клетки маршрута без скачков.']
        path.append(cell)
    if not path or path[0]!=(p['start']['x'],p['start']['y']):
        return ['Маршрут должен начинаться у входа.']
    if any((batches[k]['location']['x'],batches[k]['location']['y']) not in path for k in selected):
        return ['Маршрут не проходит через все выбранные точки хранения.']
    return []


def validate_history(p,s):
    answers=s.get('answers')
    expected={'founded':'1978','event':'olympics','brand':'secret'}
    if not isinstance(answers,dict) or set(answers)!=set(expected):
        return ['Ответьте на все вопросы.']
    if answers!=expected:
        return ['Не все ответы верны. Воспользуйтесь подсказкой и официальной историей компании.']
    return []
