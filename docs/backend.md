# Сервер VK Mini App «Очаково: изнутри»

Python 3.10+; зависимости отсутствуют. SQLite сохраняет профиль, сессии, черновики, завершения заданий, реестр баллов, отклики, записи на события и обмены. Каталог — `server/catalog.json`. Все карьерные предложения, события, награды и профессиональные модели демонстрационные; реального найма или обещания выдачи награды нет.

## Локальный запуск

Из корня проекта:

```sh
DEV_AUTH=1 ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 python3 -m server --host 127.0.0.1 --port 3001
```

Фронтенд направляет `/api` на этот сервер через Vite proxy. `DEV_AUTH=1` разрешает демонстрационный вход только с loopback IP. По умолчанию он выключен. Демопользователь имеет namespace `demo:`, VK-пользователь — `vk:`; их данные не смешиваются.

В VK требуется серверная конфигурация:

```sh
VK_APP_ID=<application-id> VK_APP_SECRET=<secure-key> ADMIN_TOKEN=<private-HR-token> python3 -m server --host 127.0.0.1 --port 3001
```

Не передавайте VK_APP_SECRET и ADMIN_TOKEN во frontend env. Клиент отправляет исходный `window.location.search` как `launchParams`. Сервер сортирует только `vk_*`, кодирует `urlencode`, проверяет HMAC-SHA256 через constant-time comparison, ID приложения и `vk_ts` (TTL по умолчанию 3600 секунд, настраивается `VK_LAUNCH_TTL`; допускается 60 секунд рассинхронизации часов). Требуется положительный `vk_user_id`. Повторяющиеся параметры отклоняются. Алгоритм соответствует [официальному примеру VKCOM](https://github.com/VKCOM/vk-apps-launch-params/blob/master/examples/python3.py).

При доступе по публичному HTTPS-домену используйте reverse proxy: `/api` → Python server, остальное → собранный frontend. Не публикуйте stdlib development HTTP server непосредственно в интернет. Для production задайте DEV_AUTH=0, HTTPS, разрешённые домены ALLOWED_ORIGINS и политику хранения персональных данных. В VK нужно самостоятельно зарегистрировать приложение и указать HTTPS URL — наличие веб-прототипа не подтверждает настройку платформы.

`--db` меняет путь хранилища. По умолчанию `.data/ochakovo.sqlite3`. Схема расширяет существующие таблицы без удаления данных. WAL и `BEGIN IMMEDIATE` предотвращают одновременное двойное начисление, перерасход баланса и превышение мест/запасов. Не копируйте работающую SQLite-базу без согласованного snapshot/backup.

## Формат запросов

`Content-Type: application/json`, `Authorization: Bearer <session-token>`; срок сессии — 24 часа. В базе сохраняется SHA256-хеш токена. Лимит тела 128 KiB, черновика 64 KiB. Ответы `Cache-Control: no-store`.

Ошибка: `{error: string, code: string, details?: object}`. Ошибки полей профиля — HTTP422 с `details: {field: message}`. Неверное игровое решение — HTTP200 и `correct:false`; оно не создаёт завершение или начисление. Ресурсы другого пользователя не выдаются.

| Метод | URL | Тело / результат |
|---|---|---|
| GET | `/api/health` | `{ok, service}` |
| GET | `/api/config` | `{devAuth, vkConfigured}` |
| GET | `/api/catalog` | Публичный `{tasks,offers,events,rewards}`, актуальные `remaining` |
| POST | `/api/auth` | `{launchParams: string \| object}` → `{token,userId,mode}` |
| POST | `/api/auth` | Только в dev: `{devUserId: string}` → `{token,userId,mode:'demo'}` |
| DELETE | `/api/auth` | Завершает текущую сессию |
| GET | `/api/bootstrap` | `{user:{id},profile,balance,catalog,progress,ledger,applications,registrations,exchanges}` |
| GET | `/api/profile` | `{profile}` |
| PUT | `/api/profile` | Профиль → `{profile}` |
| PUT | `/api/tasks/:id/draft` | `{draft:object,revision?:integer}` → `{saved,revision,progress?}` |
| POST | `/api/tasks/:id/complete` | `{solution:object}` → `{correct,pointsAwarded,alreadyCompleted,explanation?,errors?,balance?,progress?}` |
| GET | `/api/ledger` | `{balance,ledger}` |
| POST | `/api/applications` | `{offerId}` → `{application,alreadyApplied,demo,message}` |
| POST | `/api/events/:id/registration` | `{}` → `{registration,catalog?}` |
| DELETE | `/api/events/:id/registration` | `{registration,catalog}`; отмену можно повторить |
| POST | `/api/rewards/:id/exchange` | `{}` → `{exchange,alreadyExchanged,balance,catalog?}` |
| POST | `/api/analytics` | `{event}` → `{ok}` |

Профиль: `{fullName,contact,birthDate:'YYYY-MM-DD',direction,availability,education,schedule?,consent:true,futureContact?:false}`. Контакт — телефон или email. Все основные текстовые поля обязательны. Для этого прототипа принимается возраст от 18 до 100 лет; он не используется для автоматического решения о найме. При сохранении сервер добавляет `consentedAt`. Согласие на будущие предложения независимо от обработки анкеты. Для игр, откликов, событий и наград нужен сохранённый профиль; баланс и завершения не являются условиями отклика.

`progress`: `{task,draft,completed:string|null,revision:number}`. Черновики имеют монотонную версию: клиент передаёт `revision = max(Date.now(), lastRevision + 1)` и начинает счётчик с максимума полученных `progress[].revision`. Запрос с меньшей версией не меняет базу и возвращает HTTP200 `{saved:false,reason:"stale",draft,revision}` с текущим серверным состоянием. Это предотвращает затирание свежего черновика поздним autosave/pagehide-запросом. Старым клиентам без revision сервер присваивает `max(now_ms,stored+1)`; завершение задания версию черновика не сбрасывает. Существующая схема обновляется добавлением draft_revision с начальным значением0 без удаления данных. `ledger`: `{id,reason,delta,created}`. Отклик содержит snapshot профиля на момент отправки. Для совместимости отклики имеют и `offer`, и `offerId`; записи `event`/`eventId`, обмены `reward`/`rewardId`. Один пользователь может отправить один отклик на предложение, иметь одну активную запись на событие и обменять каждую награду один раз. Отменённую запись можно восстановить при наличии мест. Время события — Москва (UTC+3).

За каждое содержательно завершённое задание/уровень баллы начисляются один раз. Перепрохождение и обновление черновика завершение не сбрасывают. За отклики, профиль и аналитику баллы не начисляются. Обмен и отрицательная запись ledger совершаются в одной транзакции, после проверки баланса и остатка награды. Нет клиентского API для произвольного начисления.

## Игровые форматы

Задачи: `signal-1..3`, `movement-1..3`, `lab-1..3`, `delivery-1..3`, `history-1`. Симулятор «Разберись в смене» исключён до появления новых экранов.

- **signal**: `{rules:[{condition:'red'|'blue'|'marked'|'unmarked'|'red_marked'|'always',output:'left'|'right'}]}`. До трёх блоков, первое совпадение определяет выход. Сервер проверяет все комбинации цвета/метки, включая невидимые примеры.
- **movement**: `{gears:[{x,y}]}`. Координаты целочисленные; привод и цель уже стоят на поле, повторно их передавать не нужно. Соседние по стороне колёса меняют направление. Все детали должны быть в границах, соединены, не пересекаться, а цель — вращаться как указано. Несколько конструкций допустимы.
- **lab**: `{sampleId,evidence:['color','acidity',...]}`. Результаты выбранных исследований должны оставить ровно один подходящий образец в матрице. Вымышленные вещества и условные исследования явно обозначены.
- **delivery**: `{placements:[{batchId,x,y,rotated:boolean}],route:[{x,y}]}`. Проверяются точный комплект, запрет резервированных и повторных партий, геометрия и непересечение. Маршрут начинается в `puzzle.start`, идёт по соседним клеткам и проходит через точки всех выбранных партий. Поворот меняет `(dx,dy)` на `(dy,dx)`.
- **history**: `{answers:{founded:'1978',event:'olympics',brand:'secret'}}`. Три вопроса об истории предприятия/бренда; [официальная история «Очаково»](https://ochakovo.ru/en/istoriya/) проверена 24.10.2026. Факты: открытие 18.12.1978; подготовка к Олимпиаде-80; белый квас «Семейный секрет», 2013.

## HR и аналитика

Защищённые запросы используют `X-Admin-Token: <ADMIN_TOKEN>` или `Authorization: Bearer <ADMIN_TOKEN>`. Токен нельзя включать в URL или распространять среди кандидатов. CLI берёт его из ADMIN_TOKEN; при отсутствии использует игнорируемый `.data/admin-token`, при отсутствии файла создаёт его с правами 0600. Содержимое не выводится в журнал.

- `GET /api/admin/applications` → `{applications,demo:true}`.
- `PATCH /api/admin/applications/:id` с `{status:'sent'|'reviewing'|'contacted'|'accepted'|'rejected'}`.
- `GET /api/admin/analytics` → агрегированные события, число профилей и откликов. Это наблюдения прототипа, не доказательство роста конверсии.

Клиентские события ограничены allowlist: onboarding_started, profile_form_opened, offer_viewed, task_opened, task_started, task_hint, event_viewed, reward_viewed, application_reviewed. Профиль, сессия, отклик, завершение игры, запись/отмена и обмен фиксируются сервером. Аналитика не принимает произвольные персональные поля.

## Проверка

```sh
python3 -m unittest discover -s server/tests -v
```

Тесты используют отдельную временную базу, не меняют пользовательскую `.data`. Проверяются все 13 решаемых уровней, неверные решения, сохранение после нового подключения, изоляция пользователей, профиль и согласие, реальный HTTP-путь отклика, HR-статус, VK HMAC/подмена/срок/ID, запрещённый dev-вход, параллельное повторное завершение, обмен и конкурентная запись сверх лимита, конкурентные черновики с переставленными версиями и миграция старой схемы без потери прогресса.

## Сборка и развёртывание

После `npm run build` сервер также отдаёт `dist/index.html`, статические ассеты и SPA fallback для клиентских маршрутов. `npm start` обслуживает собранное приложение и `/api` с одного origin. Только файлы внутри dist доступны клиенту: `.data`, `.env`, серверный исходный код и traversal-пути не выдаются. HTML не кэшируется надолго, хешированные Vite assets имеют immutable cache. `DIST_DIR` позволяет указать другой каталог сборки.

Файл `.env.example` документирует переменные; Python автоматически `.env` не загружает. Передайте их через shell, секреты платформы или Docker `--env-file`.

```sh
docker build -t ochakovo-miniapp .
docker run --rm --name ochakovo-miniapp --env-file .env -p 127.0.0.1:3001:3001 -v ochakovo-data:/app/.data ochakovo-miniapp
```

Контейнер запускается от непривилегированного UID10001, хранит базу в постоянном volume, содержит только Python runtime и готовые frontend assets. VK_APP_ID, VK_APP_SECRET и ADMIN_TOKEN передаются при запуске; они не попадают в образ. Dockerfile и контейнер не настраивают домен, TLS, VK developer account или реальный HR-маршрут компании. Перед обратным proxy оставляйте DEV_AUTH=0. Демовход дополнительно запрещён для нелокального Host и при forwarded-заголовках: loopback-адрес proxy не должен становиться доказательством локального пользователя.

`bootstrap` содержит `routeCompleted:boolean` и `routeProgress:{completed,total,taskIds,completedTaskIds}` для первых уровней четырёх игр и исторического теста. Это основание показать приглашение на экскурсию. Возможность записаться через календарь не зависит от этого флага или баллов.
