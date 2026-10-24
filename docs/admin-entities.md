# Сущности приложения и модель будущей админки

Документ описывает текущую модель «Очаково: изнутри» и требования к будущей админке, включая модульные игровые спрайты v5. Это схема по исходному коду, а не выгрузка пользователей или рабочей базы. Реальные QR, ключи, токены, анкеты и приватные ссылки дизайна сюда не включены.

**Статусы документа:** `implemented` — существует в приложении; `proposed` — предложение для будущей реализации. Наличие сущности в проектной модели не означает, что её редактор, таблица или API уже реализованы.

Источники: `server/app.py`, `server/catalog.json`, `server/solutions.py`, `server/shift.py`, `server/level_rules.py`, `server/level-rules.json`, `src/types.ts`, `src/games/types.ts`, `src/games/ShiftTypes.ts`, `src/games/sprites.ts`, `src/games/GameSprite.tsx`, `src/games/sprite-manifest.json`. Машиночитаемое дополнение — [admin-entities.json](admin-entities.json).

## 1. Где находится источник истины

| Слой | Сущности | Текущее хранение | Управление сейчас |
|---|---|---|---|
| Пользовательские данные | Пользователь, профиль, сессия, прогресс, ledger, отклик, запись, обмен, аналитическое событие | 8 таблиц SQLite | Только существующие пользовательские действия и ограниченный HR-доступ |
| Активности событий | Определение активности, выполнение активности | 2 таблицы SQLite | Публичный просмотр и сканирование; organizer CRUD и выдачи QR нет |
| Контент | Семейства игр, задания/уровни, предложения карьеры, мероприятия, награды | `server/catalog.json` | Правка исходных файлов; редактора контента нет |
| Правила игры | Проверка решения; приватные определения истории и смены | Python-валидаторы и `server/level-rules.json` | Правка исходного файла с перезапуском; контентного CRUD/публикации нет |
| Представление v5 | 16 модульных SpriteAsset, роли, GamePresentation, SceneObject; компоненты и CSS | Публичный asset manifest и `Task.presentation` | Runtime-композиция реализована; редактора/загрузки assets через админку нет |
| Будущий редактор | Версии LevelDefinition/RuleSet, SpriteModule со слотами, LevelObject с привязкой к puzzle | **proposed** | Расширение существующих runtime-сущностей, не действующая админка |

В исходном каталоге сейчас 6 GameDefinition и 15 заданий: два раунда смены, по три уровня алгоритма, механизма, лаборатории и комплектации, один исторический тест. В нём также 6 карьерных предложений, 3 мероприятия, 5 наград и 6 seed-определений активностей. Это числа определений из репозитория, не статистика пользователей.

Runtime-источник активностей — SQLite. `events[].activities` в JSON используется только для первоначального добавления отсутствующих seed-ID. Перезапуск не перезаписывает уже существующие определения, токены или деактивацию.

## 2. Все десять таблиц SQLite — implemented

Обозначения: **PK** — первичный ключ, **UQ** — уникальность, **FK** — реально объявленный внешний ключ. Ссылки на JSON-каталоги ниже — логические: SQLite не проверяет существование соответствующего каталожного ID. `PRAGMA foreign_keys=ON` включён на каждом соединении; каскадных удалений нет.

Схема прототипа не везде содержит `NOT NULL` и `CHECK`. Например, большинство полей первых восьми таблиц допускают SQL NULL; текстовый или составной PK в обычной SQLite-таблице сам по себе не заменяет явный `NOT NULL`. Обязательность многих значений сейчас обеспечивает API. Будущая миграция должна учитывать это, не приписывая текущей БД отсутствующие ограничения.

| Таблица | SQL-поля | Ключи и ограничения | Связи / смысл |
|---|---|---|---|
| `users` | `id TEXT`, `profile TEXT` | PK `id` | `profile` — nullable JSON-текст. `id` имеет namespace `vk:` или `demo:` |
| `sessions` | `token TEXT`, `user_id TEXT`, `expires REAL` | PK `token`; FK `user_id → users.id` | В `token` хранится SHA-256 хеш bearer-токена; `expires` — Unix seconds |
| `progress` | `user_id TEXT`, `task TEXT`, `draft TEXT DEFAULT '{}'`, `completed TEXT`, `draft_revision INTEGER NOT NULL DEFAULT 0` | PK `(user_id, task)`; FK `user_id → users.id` | `task → tasks.id` логически; черновик JSON, первое завершение — timestamp или NULL |
| `ledger` | `id TEXT`, `user_id TEXT`, `reason TEXT`, `delta INTEGER`, `created TEXT` | PK `id`; UQ `(user_id, reason)`; FK `user_id → users.id` | Журнал положительных начислений и отрицательных обменов; баланс не хранится отдельно |
| `applications` | `id TEXT`, `user_id TEXT`, `offer TEXT`, `profile TEXT`, `status TEXT`, `created TEXT` | PK `id`; UQ `(user_id, offer)`; FK `user_id → users.id` | `offer → offers.id` логически; `profile` — снимок анкеты при отправке |
| `registrations` | `id TEXT`, `user_id TEXT`, `event TEXT`, `status TEXT`, `created TEXT` | PK `id`; UQ `(user_id, event)`; FK `user_id → users.id` | `event → events.id` логически; отменённая запись остаётся в таблице |
| `exchanges` | `id TEXT`, `user_id TEXT`, `reward TEXT`, `created TEXT` | PK `id`; UQ `(user_id, reward)`; FK `user_id → users.id` | `reward → rewards.id` логически; одна награда — один обмен на пользователя |
| `analytics` | `id INTEGER`, `user_id TEXT`, `event TEXT`, `created TEXT` | INTEGER PK `id`; FK `user_id → users.id` | `event` — имя аналитического события, **не** ID мероприятия. Нет JSON properties |
| `event_activities` | `id TEXT`, `event_id TEXT NOT NULL`, `title TEXT NOT NULL`, `description TEXT NOT NULL`, `points INTEGER NOT NULL`, `active INTEGER NOT NULL DEFAULT 1`, `qr_token TEXT NOT NULL` | PK `id`; UQ `qr_token`; CHECK `points BETWEEN 1 AND 1000`; CHECK `active IN (0,1)` | `event_id → events.id` логически; QR-токен приватный, стабильный, создан из 32 случайных байтов |
| `activity_completions` | `user_id TEXT NOT NULL`, `activity_id TEXT NOT NULL`, `completed_at TEXT NOT NULL`, `awarded_points INTEGER NOT NULL` | PK `(user_id, activity_id)`; FK `user_id → users.id`; FK `activity_id → event_activities.id`; CHECK `awarded_points BETWEEN 1 AND 1000` | Снимок времени и суммы первого выполнения; повтор не начисляет новые баллы |

Именованные индексы: `sessions(expires)`, `registrations(event,status)`, `exchanges(reward)`, `ledger(user_id)`, `event_activities(event_id,active)`, `activity_completions(activity_id)`. PK/UQ дополнительно создают соответствующие SQLite-индексы.

### 2.1. Профиль и согласия — вложенный JSON

Профиль существует как `users.profile`, затем копируется в `applications.profile`. Отдельных таблиц `profiles`, `consents`, `contacts` сейчас нет.

| Поле JSON/API | Тип / обязательность | Текущее правило |
|---|---|---|
| `fullName` | string, обязательно | Не более 300 символов, минимум два слова |
| `contact` | string, обязательно | Телефон с 10–15 цифрами или email; одно поле |
| `birthDate` | string, обязательно | Канонический `YYYY-MM-DD`, существующая дата не из будущего; возраст 18–100 по Москве |
| `direction` | string, обязательно | Значение интереса; варианты задаёт UI, сервер проверяет непустую строку, не enum |
| `availability` | string, обязательно | Готовность выйти; варианты UI не являются серверным enum |
| `education` | string, обязательно | Вуз/колледж/подтверждённое пользователем описание |
| `schedule` | string, необязательно | По умолчанию `""`, до 300 символов |
| `consent` | boolean, обязательно true | Согласие на обработку профиля и заявок |
| `futureContact` | boolean, необязательно | Отдельное согласие на будущие предложения; по умолчанию false |
| `consentedAt` | string, серверное поле | UTC ISO timestamp текущего сохранения профиля |

`consentedAt` обновляется при каждом сохранении; отдельной версионируемой истории согласий, текста политики, отзыва, IP или журнала изменений сейчас нет. В будущем это самостоятельная задача, а не существующая функция.

Возраст младше 18 возвращает `422 age_restricted`, некорректная/будущая дата — `422 validation_error`. Отказ не создаёт постоянный бан, не сохраняет новую анкету и не меняет ранее сохранённую взрослую. Для 29 февраля в невисокосном году календарная граница наступает 1 марта.

Снимок `applications.profile` сохраняет анкету и согласия на момент отклика. Редактирование текущего профиля не меняет уже отправленный snapshot. Удаление или обезличивание данных должно учитывать обе копии.

### 2.2. Сессия и права

Bearer-токен возвращается при входе; в БД сохраняется только его хеш. Сессия действует 24 часа, истёкшие сессии очищаются при новом входе; проверка срока выполняется на каждом запросе. Пользователь может завершить свою текущую сессию.

VK-идентичность проверяется сервером по HMAC подписанных launch parameters. Локальный демонстрационный вход включается отдельно и не является production-авторизацией. В БД нет ролей администратора, организаций или списка сотрудников. Текущий HR-доступ использует отдельный серверный ключ, не `users.role`.

### 2.3. Баллы и неизменяемая история

У `ledger.reason` три рабочих соглашения:

- `task:<taskId>` — первое содержательное завершение задания/уровня.
- `exchange:<rewardId>` — списание при обмене награды.
- `event-activity:<activityId>` — первое выполнение активности по QR.

Ссылки внутри reason не являются FK. UQ `(user_id,reason)` и транзакции защищают повторные начисления. Для активности дополнительно существует уникальный completion. `awarded_points` — историческая сумма: изменение определения активности не переписывает заработок. Для обмена историческая стоимость отражена отрицательным `ledger.delta`; отдельного `cost` в `exchanges` нет.

Прямой API редактирования баланса отсутствует. Будущую корректировку следует проектировать как отдельную обоснованную запись/операцию с аудитом, сохраняя историю, а не заменять вычисленный баланс.

## 3. Поля SQL и форма API

| SQL / хранилище | API | Примечание |
|---|---|---|
| `users.id` | `bootstrap.user.id`, `auth.userId` | Верхнеуровневого `bootstrap.userId` текущий сервер не выдаёт |
| `users.profile` | `profile` object или null | JSON декодируется |
| `sessions.token` | Нет чтения хеша через публичный API | `auth.token` — исходный bearer, а не значение столбца |
| `progress.task` | `progress[].task` | Отдельного `taskId` алиаса нет |
| `progress.draft` | `progress[].draft` object | JSON декодируется |
| `progress.draft_revision` | `progress[].revision` | В bootstrap snake_case удаляется; frontend сохраняет совместимость со старым именем |
| `progress.completed` | `progress[].completed` | Timestamp/null, не boolean |
| `applications.offer` | `offer` и дополнительный `offerId` | Сохраняются оба имени |
| `registrations.event` | `event` и дополнительный `eventId` в bootstrap | `analytics.event` к этому алиасу не относится |
| `exchanges.reward` | `reward` и дополнительный `rewardId` в bootstrap | Историческая сумма обмена — ledger |
| `event_activities.event_id` | `eventId` | Snake_case наружу не выдаётся |
| `event_activities.active` | `active` boolean | INTEGER 0/1 преобразуется в boolean |
| `event_activities.qr_token` | Не выдаётся текущими API | QR содержит versioned opaque payload, но получение/выдача организатором сейчас не реализованы |
| `activity_completions.activity_id` | `activityId` | Completion принадлежит только текущему пользователю |
| `activity_completions.completed_at` | `completedAt` | UTC ISO timestamp |
| `activity_completions.awarded_points` | `awardedPoints` | В repeat scan это исходная сумма, а `pointsAwarded` ответа равен 0 |
| JOIN `event_activities.event_id` | `activityCompletions[].eventId` | Вычисляется по текущему определению активности; не хранится snapshot-колонкой completion |
| `user_id` в пользовательских rows | Обычно скрыт в bootstrap | В HR-списке откликов преобразуется в `userId` |

Ответы отдельных mutations исторически не полностью унифицированы: registration POST/DELETE и повтор exchange могут вернуть raw row с `user_id`, `event`/`reward`; bootstrap нормализует aliases по таблице выше. Будущая админка должна выбрать единый контракт явно, не выводить его только из frontend interface.

## 4. Каталожные сущности — implemented как JSON

### 4.1. Task — текущая единица задания и начисления

Поля: `id`, `game`, `level`, `title`, `description`, `direction`, `points`, `duration`, `offerId`, `demo`, `explanation`, `puzzle`, необязательный `presentation`. Ключ `id` уникален по соглашению каталога, не ограничением SQLite. Значения `game`: `shift`, `signal`, `movement`, `lab`, `delivery`, `history`.

Каталог `games[]` содержит определения семейств GameDefinition (раздел 4.7); отдельной SQL-таблицы уровней нет: каждый уровень является записью Task. Связь уровней — `Task.game → games.id` и номер `level`. `offerId → offers.id` и `direction` логические. Прогресс и ledger привязаны к стабильному `Task.id`, не к UI-номеру уровня.

| Тип | Вложенные сущности puzzle | Что остаётся серверной логикой |
|---|---|---|
| `signal` | `stream[{color,marked}]`, `allowedConditions`, `outputs`, `rule`, `maxRules`; пользовательские `rules[{condition,output}]` | First-match исполнение и проверка всех комбинаций входа |
| `movement` | `width,height`, `source{x,y,direction}`, `target{x,y,direction}`, `maxGears`, необязательные `maxBelts,beltLinks[{from:{x,y},to:{x,y}}]`; пользовательские `gears[{x,y}],belts[{from,to}]` | Контакт шестерён меняет направление, открытый ремень сохраняет; сервер проверяет единую сеть, занятые валы, allowlist, лимиты, дубликаты и противоречивые циклы |
| `lab` | `samples[{id,name,properties}]`, `tests[{id,label}]`, `observations` — канонические результаты исследований | Совместимость и однозначность вывода по выбранным evidence |
| `delivery` | `width,height`, `batches[{id,product,cells,reserved,location}]`, `order[{product,quantity}]`, `start`, `warehouse{width,height}` | Комплект, резерв, геометрия, пересечения, соседство и охват маршрута |
| `history` | `questions[{id,text,options[{id,text}],source}]` | Правильные answer keys находятся в приватном registry `level-rules.json` |
| `shift` | `scenarioId`, `snapshotTime`, `measurementWindow`, `modelNote`, `metrics`, `scheme`, `journal`, `checks`, `facts`, `conclusion`, `hints`, `maxObservations` | Принятые утверждения, категории достаточности и противоречий, безопасное действие, объяснение результата |

В механизме `BeltLink` — допустимая пара координат валов в puzzle, а `Belt` — выбранная связь в пользовательском решении/draft. Концы должны быть различными занятыми валами (привод, цель или установленная шестерня); обратная запись той же пары считается повтором. Без `maxBelts` и `beltLinks` старые уровни работают только с шестернями; отсутствующий `solution.belts` означает пустой список. Чисто ремённая передача допустима без добавленных шестерён. Отдельных SQL-таблиц ремней и валов нет.

Во вложенной модели смены различаются:

- `Metric`: `id,label,value,unit,previous,series[{time,value}],factId,historyFactId,source,time`; необязательные `shortLabel,highlight,format`.
- `SchemeNode`: `id,label,value,unit,factId`; необязательные `position,display,metricId,format`. `SchemeFlow`: `id,from,to,label,factId`.
- `JournalEvent`: `id,time,title,detail,factId`.
- `Check`: `id,title,description,result,factId`.
- `Fact`: `id,source,time,text` — канонический источник наблюдения.
- `ConclusionOption`: `id,label` в группах `observedChange`, `explanation`, `nextStep`, `responsible`.
- `Observation`: сохранённые в draft `factId,source,time,fact,note`; можно удалить/редактировать note. Evidence — ссылки на собственные сохранённые observations.
- `ShiftConclusion`: `observedChange,explanation,evidence[],nextStep,responsible`; свободный текст гипотезы не оценивается автоматически.

Эти вложенные модели — части JSON определения или черновика, не дополнительные SQL-таблицы. RuleSet в проектной модели ниже должен позволить их версионировать, не раскрывая клиенту приватные ответы.

### 4.2. CareerOffer

Поля JSON: `id,title,direction,type,location,schedule,pay,description,tasks[],requirements[],demo`. В UI-типе дополнительно предусмотрен `deadline?`, но текущие определения его не содержат. Типы сейчас текстовые «Практика»/«Работа», а не SQL enum. Связанные отклики ссылаются на offer ID логически.

### 4.3. CareerEvent

Поля JSON: `id,title,date,startTime,location,type,description,capacity,remaining,demo,activities[]`. В UI-типе предусмотрены `requirements?` и `program?`; это необязательные возможности интерфейса. `remaining` пересчитывается сервером, JSON-значение не является источником текущего остатка. Дата/время события интерпретируются в UTC+3.

### 4.4. Reward

Поля JSON: `id,title,cost,stock,remaining,description,demo`. Ключ `id` логический. `cost` — цена обмена, `stock` — общий запас; `remaining` пересчитывается сервером. Состояния реальной выдачи, сертификат, адрес доставки или fulfilment-заявка не реализованы.

### 4.5. EventActivity

Публичные поля: `id,eventId,title,description,points,active`. Runtime хранение — `event_activities`, приватный `qr_token` не входит в публичную модель. Seed JSON не содержит готового QR. Выполнение возможно без регистрации на мероприятие и не занимает место.

Completion хранит исторические `completedAt` и `awardedPoints`. Scan подтверждает предъявление QR в прототипе, а не физическое присутствие. Повтор возвращает `pointsAwarded:0`; inactive даёт отказ даже для ранее выполненной активности, не удаляя историю.

Создание/редактирование/выдача QR организаторам сейчас **не реализованы**. Эти операции перечислены только как требования к отдельной будущей админке.

### 4.6. Приватный реестр правил — implemented в исходном коде

`server/level-rules.json` отделяет данные проверки history и shift от Python-движков. Форма: `{schemaVersion:1,levels:{taskId:ruleRef},rules:{ruleRef:definition}}`. `levels` — приватная связь стабильного Task.id с повторно используемым правилом; она не попадает в публичный каталог. Сейчас есть три связи для истории и двух сценариев смены.

| Определение | Точные поля | Смысл |
|---|---|---|
| HistoryRule | `game:'history'`, `answers:{questionId:optionId}` | Приватные ключи ответов; каждый вопрос и option сверяются с публичным puzzle |
| ShiftRule | `game:'shift'`, `observedChange`, `explanation`, `nextStep`, `responsible`, `localizationPaths`, `causeFacts`, `contradictoryFacts`, `explanationText`, `outcome`, `assessment` | Принятые claims, достаточность наблюдений, противоречия и обратная связь |
| LocalizationPath | `string[][][]` на уровне `localizationPaths` | Достаточен один путь; в нём нужны все категории, в каждой достаточно одного fact ID |
| ShiftOutcome | `summary,before,after` | Учебный результат; все значения — строки |
| ShiftAssessment | `localization,cause,nextStep` | Целые значения 0–1000 для структурированной обратной связи; это не разрешение клиенту задавать сумму начисления |

Loader `server/level_rules.py` отвергает дублирующиеся JSON-ключи, лишние/недостающие поля и неподдерживаемую схему. При разрешении проверяет game и ссылки на факты/options текущего puzzle; отсутствующее/несовместимое правило не даёт успешного завершения. Клиент не выбирает ruleRef и не передаёт исполняемый код.

`schemaVersion` обозначает формат файла, а суффикс `v1` в именах rule refs — соглашение именования. Система опубликованных immutable-ревизий здесь **ещё не реализована**. Registry кешируется после загрузки: изменения файла применяются после перезапуска. Серверной выдачи файла, редактора или новых административных endpoints нет. Для signal/movement/lab/delivery остаются ограниченные Python-валидаторы, использующие публичный puzzle.

### 4.7. GameDefinition — implemented как каталог семейств

`catalog.games[]` содержит 6 записей: `id,title,description,previewSpriteId?`. `id` совпадает с поддерживаемым `Task.game`; каждый GameDefinition объединяет несколько Task. `previewSpriteId → SpriteAsset.id` — логическая ссылка на локальную библиотеку, для истории preview не обязателен. В интерфейсе пять игровых карточек и отдельная ссылка исторического теста.

GameDefinition сейчас хранит описание и превью, а не исполняемый движок или приватный validator. Создание новой карточки не добавляет новую механику. Поля `rendererKey`, lifecycle/versioning и настройки совместимых schema из проектной модели ниже ещё не реализованы.

## 5. Статусы и справочники

| Сущность | Серверные значения | Текущие подписи UI |
|---|---|---|
| Application | `sent`, `reviewing`, `contacted`, `accepted`, `rejected` | «Отправлен», «На рассмотрении», «HR связался», «Принят», «Завершён» |
| Registration | `registered`, `cancelled` | «Запись подтверждена», «Отменена» |
| Progress | NULL или timestamp в `completed` | «Новые», «Начатые», «Пройденные» — вычисленные фильтры |
| EventActivity | `active` 0/1 | «Ожидает QR-код» / «Пока недоступна»; «Выполнено» берётся из completion |
| ActivityCompletion | Наличие строки | Однократно «Выполнено»; отдельного status нет |
| Exchange | Наличие строки | «Обмен сохранён»; отдельного status нет |
| Profile eligibility | Ошибка `age_restricted` или сохранённый профиль | Возрастной экран — не постоянный бан и не SQL-статус пользователя |

UI-словарь также содержит legacy/совместимые подписи `received`, `new`, `submitted`, `invited`, `withdrawn`, `confirmed`. Текущий сервер не принимает их как статусы HR-обновления. Не добавлять их в будущий серверный enum только по наличию UI-label.

Направления в UI: `undecided`, `lab`, `production`, `technology`, `warehouse`, `automation`, `mechanics`. Это текущий справочник интерфейса, не таблица и не строго валидируемый сервером enum профиля. График, готовность выйти, вид события и тип предложения также сейчас строки.

### 5.1. Настройки браузера и временное состояние

В браузере хранятся выбор цели награды (на пользователя), локальный ID демонстрационного входа и временный переход к выбранному карьерному направлению. Они не являются централизованными сущностями будущей админки. Bearer-токен находится в памяти JS; сохранённые серверные draft и их revisions относятся к Progress, а не к самостоятельной локальной базе уровней.

Поля интерфейса вроде выбранной вкладки, открытого QR-сканера, сообщений об ошибках, фильтра задач и состояния анимации не имеют отдельной административной CRUD-модели. Справочники направлений, готовности выйти и графиков при необходимости можно вынести в управляемый контент; сейчас они заданы кодом интерфейса.

## 6. Вычисляемые поля и исторические особенности

| Поле | Текущая формула / семантика |
|---|---|
| `balance` | `SUM(ledger.delta)` конкретного пользователя, default 0 |
| `event.remaining` | `max(0,capacity - COUNT(registrations WHERE event=id AND status='registered'))` |
| `reward.remaining` | `max(0,stock - COUNT(exchanges WHERE reward=id))` |
| `events[].activities` | Runtime SELECT по `event_activities.event_id`; seed JSON заменяется актуальными rows |
| `activityCompletions[].eventId` | JOIN с текущей event activity; исторический event ID отдельно не сохранён |
| `routeProgress` | Первые уровни `shift-1,signal-1,movement-1,lab-1,delivery-1,history-1`, completed count/IDs и total 6 |
| `routeCompleted` | Все шесть обязательных заданий имеют completed timestamp |
| `alreadyCompleted` / `pointsAwarded` | Проверка сохранённого первого начисления, не доверие клиентским баллам |
| UI progress «начато» | Есть progress row без completed; открытие/сохранение draft может создать row |
| Цель награды | Предпочтение браузера, не таблица сервера и не утверждённый заказ |

Смена статуса отклика не отправляет автоматически письмо или сообщение. Повторная регистрация после отмены сохраняет прежний `registrations.id`, меняет `status` и `created`. Отдельных `cancelledAt`, `statusUpdatedAt`, `changedBy`, журналов переходов и истории выдачи наград нет.

Аналитика хранит события, а не уникальные воронки. `task_completed` пишется и при корректных повторах без новых баллов; `event_cancelled` может записаться при повторной отмене. Нельзя считать число этих событий числом уникальных завершений. Для уникальных результатов нужны progress/completion/application rows.

Клиентская allowlist: `onboarding_started`, `profile_form_opened`, `offer_viewed`, `task_opened`, `task_started`, `task_hint`, `event_viewed`, `reward_viewed`, `application_reviewed`. Серверные события: `session_started`, `profile_saved`, `task_completed`, `application_sent`, `event_registered`, `event_cancelled`, `reward_exchanged`, `event_activity_completed`.

### 6.1. Что можно редактировать и что вычисляется

«Поля будущего редактора» в этой таблице — требования к отдельной админке. Сейчас их изменяют только поддерживаемые пользовательские/HR-действия либо исходный код; новых CRUD API нет.

| Сущность | Поля будущего редактора / допустимая операция | Защищённые или вычисляемые поля |
|---|---|---|
| User / Profile | Исправление профиля с возрастной проверкой и законным основанием; отдельная процедура согласий | `users.id` стабилен; нельзя подменять `consentedAt` ручной датой или выдавать согласие за пользователя |
| Session | Отзыв доступа, если такой инструмент будет добавлен | Хеш и исходный токен не выводятся; срок — серверный; редактора секрета нет |
| Task / Level | Текст, puzzle, разрешённое представление, связь с предложением, новая версия определения | Стабильный ID/award key; `completed`, draft/revision и полученные баллы принадлежат пользовательскому прогрессу |
| CareerOffer | Заголовок, направление, тип, место, график, оплата, описание, задачи/требования | ID стабилен; отправленные `applications.profile` — исторические snapshots |
| CareerApplication | Допустимый статус; в будущем ответственный/комментарий отдельными полями | Snapshot не заменяется текущим профилем, `created`/ID не редактируются как контент |
| CareerEvent | Заголовок, дата/время, место, описание, тип, capacity, программа/требования | `remaining` вычисляется; уменьшение capacity требует проверки действующих записей |
| Registration | Явная запись/отмена в рамках прав с будущим аудитом | ID/пользователь стабильны; число мест не задаётся вручную |
| EventActivity | В отдельной будущей админке: title, description, points, active | QR стабилен и приватен; связь event требует исторической политики; earned amounts не меняются |
| ActivityCompletion | Просмотр результата; возможные исправления отдельной компенсирующей процедурой | Первое время/сумма выполнения и уникальность `(user,activity)` не являются редактируемым контентом |
| Reward | Заголовок, описание, cost, stock | `remaining` вычисляется; старые списания сохраняются при смене цены |
| RewardExchange | Просмотр; будущая выдача требует отдельной модели | ID/время и списание сохраняются; текущего fulfilment-status нет |
| PointsEntry | Просмотр; будущая обоснованная компенсирующая операция | Баланс вычисляется; прошлые `delta/reason/created` не перезаписываются |
| AnalyticsEvent | Фильтры и агрегаты | События не становятся административным источником изменения профилей или баллов |
| SpriteAsset / SpriteModule / LevelObject | Библиотека assets, слоты, размещение и привязки из раздела 8 | Публичное представление не содержит приватный validator и не переопределяет puzzle |

## 7. Что существующая админка действительно умеет

У существующего HR API ровно три операции:

1. `GET /api/admin/applications` — список откликов с snapshot-профилем, userId и текущим статусом.
2. `PATCH /api/admin/applications/:id` — изменение на один из пяти действующих серверных статусов.
3. `GET /api/admin/analytics` — агрегированные количества по именам событий, число заполненных профилей и число откликов.

Доступ — отдельный HR-ключ. UI кабинета работает с откликами; наличие серверного агрегата аналитики не означает наличие отдельной полноценной BI-панели. RBAC, каталожный CRUD, организаторские операции, создание уровней и скачивание QR отсутствуют.

Пользовательские API предоставляют собственный bootstrap/profile/ledger, сохранение draft и завершение задания, отправку отклика, запись/отмену мероприятия, обмен награды, сканирование активности и logout. Эти действия не являются административным доступом к чужим данным. Публичный `/api/catalog` не содержит персональных анкет, session hashes или QR-токенов.

## 8. Модульное представление v5 — implemented

В библиотеке используются 16 отдельных прозрачных PNG-модулей, а не снимки целых игровых экранов. Design box каждого модуля — 96 × 96, исходный файл — 192 × 192 pixels. Публичный manifest имеет форму `{schemaVersion:1,sprites:[SpriteAsset]}` и находится в `src/games/sprite-manifest.json`.

### 8.1. SpriteAsset

Точные поля: `id,kind,src,width,height,pixelWidth,pixelHeight`. `id` — стабильный семантический ключ; `src` — локальный путь. Runtime получает asset только через manifest, не через произвольный URL из роли или scene object.

| Kind | SpriteAsset IDs |
|---|---|
| automation | `automation-bottle-circle`, `automation-bottle-square`, `automation-scanner`, `automation-tray` |
| mechanics | `mechanics-gear-ivory`, `mechanics-gear-red`, `mechanics-gear-silver`, `mechanics-socket` |
| laboratory | `laboratory-tube-red`, `laboratory-tube-gold`, `laboratory-dropper`, `laboratory-meter` |
| warehouse | `warehouse-crate-a`, `warehouse-crate-b`, `warehouse-pallet-jack`, `warehouse-barrier` |

### 8.2. GamePresentation и SceneObject

Точный текущий контракт:

```ts
Task.presentation?: {
  schemaVersion: 1;
  sprites: Record<semanticRole, spriteId>;
  scene?: {
    width: number;
    height: number;
    objects: Array<{
      id: string;
      spriteId: string;
      x: number;
      y: number;
      width: number;
      height: number;
      rotation?: number;
      layer?: number;
    }>;
  };
}
```

Связи: Task → одно GamePresentation; presentation role → SpriteAsset; scene → много SceneObject; SceneObject → один SpriteAsset. Object.id уникален внутри сцены. Координаты и размеры задаются относительно размеров scene; renderer преобразует их в доли доступного контейнера. `rotation` — градусы; `layer` — целый порядок слоя в пределах −100…100.

`spriteFor` выбирает существующий asset для семантической роли либо возвращает предусмотренный движком fallback. Сейчас role keys — строки, а не SQL enum; ограничений совместимости kind/role в виде административного справочника нет. `presentationErrors` проверяет schemaVersion, наличие библиотеки, положительные размеры, конечные числа, уникальность object IDs, допустимый слой и лимит 200 объектов.

`GameScene` показывает необязательные декоративные objects и живые игровые children. Декоративный слой не принимает касания и скрыт от accessibility tree. Интерактивные позиции клеток, состав заказа, образцы/исследования, связи механизма и правила остаются в `task.puzzle` и игровом движке; scene object не меняет правильное решение. Отдельной сущности `ModuleDefinition` со slot schema в runtime нет: текущие модули — сами SpriteAsset.

### 8.3. Настраиваемое представление смены

У ShiftMetric необязательны `shortLabel`, `highlight` и `format`. `highlight` обозначает выделение карточки; изменение температуры само по себе не становится причинной подсказкой. Формат содержит `minimumFractionDigits`, `maximumFractionDigits`, `suffix`, `compactSuffix`, `comparisonSuffix`; suffix — строка с собственным разделяющим пробелом. Мини-график карточки сравнивает previous/value; подробный график продолжает использовать всю временную серию.

У ShiftSchemeNode необязательны `position:{x,y}` в дизайн-координатах 350 × 270, `display:'card'|'queue'|'extra'`, `metricId` для сравнения с метрикой и `format`. Сохранены defaults старого каталога, а новые ID могут задавать подписи/формат/расположение данными. Текущая подложка соединения сохраняет геометрию утверждённой схемы; универсального конструктора произвольного графа потока нет.

### 8.4. Что позволяет текущая модульность

Новый уровень существующего game kind можно описать новой записью Task, совместимым puzzle, presentation и приватным правилом там, где его требует validator. Нужны проверки решаемости и сохранение уникального ID. Новая механика требует кода движка и серверной проверки. Ни библиотека спрайтов, ни декларативная сцена не являются административным редактором или произвольным игровым скриптом.

## 9. Проектная модель будущего редактора — proposed

| Сущность | Предлагаемое расширение | Связи и ограничения |
|---|---|---|
| GameDefinition | К существующим `id,title,description,previewSpriteId?` — поддерживаемые renderer/schema, допустимые kinds и правило по умолчанию | Одно семейство → много уровней; новая механика всё равно требует кода |
| LevelDefinition | Версионируемая запись уровня на основе текущего Task: `definitionVersion`, связанное серверное правило, draft/review/published/archived | Стабильный Task.id — идентичность прогресса и начисления; версии публикации сейчас не реализованы |
| SpriteAsset | К текущему manifest — revision, tags, alt, provenance/licensing и допустимые variants при необходимости | Изменение библиотеки не должно ломать используемые IDs; загрузка/редактор assets ещё отсутствуют |
| SpriteModule | Переиспользуемый шаблон `id,kind,slots:[{id,role,rect,allowedSpriteKinds}]` | Slot schema — предложение; в текущем runtime её нет |
| LevelObject | При необходимости расширить текущий SceneObject ссылкой на module/slots и типизированной `entityRef` на puzzle или клетку | Нельзя считать эти поля уже поддерживаемыми renderer; интерактивная привязка должна проверяться движком |
| RuleSet | К текущему приватному registry — версия, validatorKey, public/private config, fixtures, review и publishing | Правильные ответы и достаточные evidence paths остаются только на сервере |

Публикуемая версия должна быть неизменяемой: правки создают новый draft с проверкой и публикацией. Такие lifecycle-статусы, миграция сохранённых черновиков, схема version compatibility, role/module editor и журнал авторских изменений — будущая работа.

Стабильный `Task.id` и ledger reason `task:<id>` сохраняются при визуальном обновлении существующих 15 заданий. Новая ревизия картинки не начисляет баллы повторно. Содержательно новый оплачиваемый уровень получает новый стабильный ID. Произвольные JS/Python, eval, HTML и неподконтрольные пути не предлагаются как редактируемая конфигурация.

Будущему редактору нужны preview тем же renderer, валидация asset/puzzle/rule references, положительные и отрицательные fixtures, проверка читаемости/касаний/клавиатуры и совместимость старого прогресса. Визуальный preview не заменяет проверку решаемости.

## 10. Операции будущей админки — предложения, не существующие API

| Область | Предлагаемые операции | Что важно сохранить |
|---|---|---|
| Карьера | Создавать/редактировать/архивировать предложения, условия и связи с направлениями | Стабильный offer ID и snapshots уже отправленных откликов |
| HR | Фильтровать отклики, назначать ответственного, фиксировать ответ/историю статусов, согласованные экспорты | Отдельность профиля и отклика, доступ к персональным данным по роли |
| Мероприятия | Управлять программой, датой/местом, лимитом, регистрациями/отменами | История записи, запрет переполнения, отсутствие зависимости от игровых баллов |
| Активности / будущая отдельная админка организатора | Определять активности, включать/выключать, выдавать/печатать QR, видеть выполнения | Стабильный приватный QR, однократные начисления, исторические awardedPoints; сейчас этих операций нет |
| Награды | Управлять каталогом/запасами/ценами и отдельным процессом выдачи | Исторические списания, недопустимость отрицательного остатка и дублирования обменов |
| Игры / v5 | Управлять семействами, уровнями, assets, модулями, scenes, RuleSet и версиями | Серверная проверка, решаемость, неизменные award keys и совместимость старого прогресса |
| Пользователи / данные | Просмотр в пределах полномочий, исправление, процедура удаления/обезличивания и отзывов согласия | Текущий профиль, snapshots откликов и связанные данные рассматриваются совместно |
| Баллы | Просмотр ledger и обоснованные компенсирующие операции | Не заменять историю и вычисленный баланс произвольным числом |
| Аналитика | Фильтры/агрегации/периоды и корректные метрики воронки | Отличать повторные события от уникальных действий и не ранжировать кандидатов по баллам |
| Доступ | RBAC, отдельные роли HR/организатора/редактора/техадмина и журнал изменений | Сейчас есть только отдельный HR-ключ, роли/аудит ещё не реализованы |

Для будущей реализации нужны решения о хранении каталожного контента, versioning, статусной истории, журнале согласий, soft archive и неизменяемых ссылках. Например, `activityCompletions.eventId` сейчас вычисляется через активность: перенос активности на другое мероприятие без snapshot/migration изменил бы исторический eventId. Это нужно решить до появления редактора, а не считать существующей гарантией.

## 11. Решения перед разработкой админки

Нужно согласовать место хранения и публикации управляемого контента, модель ролей, журнал изменений, историю согласий, archive-политику и миграции версий. Модульные assets и scene schema уже существуют; редактор слотов/модулей, создание новой механики без кода и публикация версий к реализованным функциям не относятся.
