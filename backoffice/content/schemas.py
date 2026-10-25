"""Editor schemas describe fields, not executable expressions."""

def obj(**properties):
    return {'type': 'object', 'properties': properties}

def arr(items):
    return {'type': 'array', 'items': items}

def text(default=''):
    return {'type': 'string', 'default': default}

def number(default=0):
    return {'type': 'number', 'default': default}

def integer(default=0):
    return {'type': 'integer', 'default': default}

def boolean(default=False):
    return {'type': 'boolean', 'default': default}

def enum(*values):
    return {'type': 'string', 'enum': list(values), 'default': values[0]}

def mapping(value):
    return {'type': 'map', 'values': value}
POINT = obj(x=integer(), y=integer())
BELT = obj(**{'from': POINT, 'to': POINT})
OPTION = obj(id=text(), label=text())
FACT = obj(id=text(), source=text(), time=text('14:00:00'), text=text())
VALUE_FORMAT=obj(minimumFractionDigits=integer(),maximumFractionDigits=integer(2),suffix=text(),compactSuffix=text(),comparisonSuffix=text())
METRIC = obj(id=text(), label=text(), shortLabel=text(), highlight=boolean(), value=number(), unit=text(), previous=number(), series=arr(obj(time=text('14:00:00'), value=number())), factId=text(), historyFactId=text(), source=text(), time=text('14:00:00'), format=VALUE_FORMAT)
PUZZLES = {'signal': obj(stream=arr(obj(color=enum('red', 'blue'), marked=boolean())), allowedConditions=arr(enum('red', 'blue', 'marked', 'unmarked', 'red_marked', 'always')), outputs=arr(enum('left', 'right')), rule=enum('color', 'mark', 'combined'), maxRules=integer(3)), 'movement': obj(width=integer(5), height=integer(3), source=obj(x=integer(), y=integer(1), direction=enum(1, -1)), target=obj(x=integer(4), y=integer(1), direction=enum(1, -1)), maxGears=integer(6), maxBelts=integer(2), beltLinks=arr(BELT)), 'lab': obj(samples=arr(obj(id=text(), name=text(), properties=mapping(text()))), tests=arr(obj(id=text(), label=text())), observations=mapping(text())), 'delivery': obj(width=integer(4), height=integer(3), batches=arr(obj(id=text(), product=text(), cells=arr(arr(integer())), reserved=boolean(), location=POINT)), order=arr(obj(product=text(), quantity=integer(1))), start=POINT, warehouse=obj(width=integer(4), height=integer(4))), 'history': obj(questions=arr(obj(id=text(), text=text(), options=arr(obj(id=text(), text=text())), source=text()))), 'shift': obj(scenarioId=text(), snapshotTime=text('14:07:30'), measurementWindow=text(), modelNote=text(), maxObservations=integer(32), metrics=arr(METRIC), scheme=obj(nodes=arr(obj(id=text(), label=text(), value=number(), unit=text(), factId=text(), position=obj(x=number(), y=number()), metricId=text(), display=enum('card', 'queue', 'extra'),format=VALUE_FORMAT)), flows=arr(obj(id=text(), **{'from': text(), 'to': text()}, label=text(), factId=text(),primary=boolean()))), journal=arr(obj(id=text(), time=text(), title=text(), detail=text(), factId=text())), checks=arr(obj(id=text(), title=text(), description=text(), result=text(), factId=text())), facts=arr(FACT), conclusion=obj(observedChange=arr(OPTION), explanation=arr(OPTION), nextStep=arr(OPTION), responsible=arr(OPTION)), hints=arr(text()))}
SOLUTIONS = {'signal': obj(rules=arr(obj(condition=enum('red', 'blue', 'marked', 'unmarked', 'red_marked', 'always'), output=enum('left', 'right')))), 'movement': obj(gears=arr(POINT), belts=arr(BELT)), 'lab': obj(sampleId=text(), evidence=arr(text())), 'delivery': obj(placements=arr(obj(batchId=text(), x=integer(), y=integer(), rotated=boolean())), route=arr(POINT)), 'history': obj(answers=mapping(text())), 'shift': obj(observedChange=text(), explanation=text(), evidence=arr(text()), nextStep=text(), responsible=text())}
SHIFT_RULE = obj(game=enum('shift'), observedChange=text(), explanation=text(), nextStep=text(), responsible=text(), localizationPaths=arr(arr(arr(text()))), causeFacts=arr(text()), contradictoryFacts=arr(text()), explanationText=text(), outcome=obj(summary=text(), before=text(), after=text()), assessment=obj(localization=integer(10), cause=integer(10), nextStep=integer(10)))
RULES = {'history': obj(game=enum('history'), answers=mapping(text())), 'shift': SHIFT_RULE}
SLOTS = arr(obj(id=text(), label=text(), spriteId=text(), role=text(), x=number(), y=number(), width=number(96), height=number(96), rotation=number(), layer=integer()))
PRESENTATION = obj(schemaVersion=integer(1), sprites=mapping(text()), scene=obj(width=number(358), height=number(441), objects=arr(obj(id=text(), spriteId=text(), x=number(), y=number(), width=number(96), height=number(96), rotation=number(), layer=integer()))))
BLOCKS = arr({'type': 'block'})
QUIZ = obj(points=integer(5), questions=arr(obj(id=text(), text=text(), options=arr(obj(id=text(), text=text())), correctOptionId=text(), explanation=text())))
