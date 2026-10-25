# Размещение «Очаково: изнутри» в VK Mini Apps

Приложение VK: **54850900**, [адрес запуска](https://vk.com/app54850900). Репозиторий содержит Docker Compose для Django 5.2, Unfold, PostgreSQL 16, Gunicorn и HTTPS через Caddy. Публичный домен, сертификат и реальный вход через VK проверяются отдельно в целевой среде; наличие локальной сборки и тестов не подтверждает публикацию. Актуальные результаты проверок — [verification.md](verification.md).

## Схема размещения

Caddy принимает HTTPS и передаёт запросы внутреннему Gunicorn. Django обслуживает мини-приложение, `/api/`, `/admin/`, безопасную статику и опубликованные игровые ассеты. PostgreSQL — отдельный сервис `db`; его порт наружу не опубликован. API-порт 3001 также не открыт на хосте. Данные, версии, медиа, сессии и QR-токены находятся в PostgreSQL volume `postgres_data`; `.data` приложения хранит собранную статику и служебные файлы. Сертификаты Caddy сохраняются в собственных volumes.

Нужен Linux VPS с Docker Engine и Compose, публичным IP и DNS-доменом. На сборку и работу приложения выделяйте ресурсы по фактическому размеру медиа и нагрузке; нагрузочный предел не измерен. Откройте TCP 80/443, при необходимости UDP443. Python и Node на production-хосте отдельно не требуются для работы контейнеров. Настроечный скрипт использует системный Python3.

При одном HTTPS-origin дополнительные CORS-настройки не нужны. Секреты никогда не передаются сборке Vite. В Compose принудительно установлены `DEV_AUTH=0` и `DJANGO_DEBUG=0`; вход в админку — персональный Django-аккаунт, общего HR-ключа нет.

## Конфигурация сервера

1. Направьте A-запись домена на VPS. AAAA используйте только при действующем IPv6 этого сервера.
2. Получите защищённый ключ приложения VK; это серверный ключ проверки подписи, не пользовательский access token.
3. Перенесите исходники выбранной версии проекта без `.data`, `.env*`, `.venv`, `node_modules`, старого `dist` и приватных копий. Примеры `.env.example` и `.env.production.example` секретов не содержат.
4. Из корня проекта создайте приватную конфигурацию:

```sh
python3 scripts/setup-deploy.py --domain mini.example.ru --app-id 54850900
```

Замените `mini.example.ru` своим доменом. Скрипт скрыто запросит ключ VK, создаст случайные PostgreSQL password и Django `SECRET_KEY`, запишет `.env.production` с правами 0600. Существующий файл он не заменяет. В `DATABASE_URL` production-host — `db`, порт 5432; локальный setup использует `127.0.0.1:55432`, эти адреса не взаимозаменяемы.

Секреты не публикуйте в Git или переписке. Не отправляйте полный вывод `docker compose config` и `docker inspect`: переменные процесса могут содержать ключи. `DJANGO_ALLOWED_HOSTS` содержит домен, `CSRF_TRUSTED_ORIGINS` — его HTTPS-origin. Compose включает доверие `X-Forwarded-Proto` только за своим Caddy.

## Новый запуск без старых данных

Если нужно перенести SQLite, сначала выполните следующий раздел вместо обычного запуска.

```sh
docker compose --env-file .env.production up -d --build
docker compose --env-file .env.production ps
docker compose --env-file .env.production exec app python manage.py createsuperuser
```

Entrypoint приложения выполняет `migrate`, `bootstrap_miniapp`, `collectstatic`, затем запускает Gunicorn. Bootstrap добавляет отсутствующее содержимое без замены редакторских изменений и пользовательских результатов. Создание суперпользователя интерактивное; логин и пароль локальной разработки не копируются.

Caddy автоматически получает и продлевает сертификаты при корректном домене и доступных портах. Его публичный DNS должен вести на сервер. [Официальная документация автоматического HTTPS](https://caddyserver.com/docs/automatic-https).

Откройте `https://mini.example.ru/admin/`, создайте персональные Django-аккаунты с `is_staff` и назначьте нужные группы. Для явного обновления штатных групп:

```sh
docker compose --env-file .env.production exec app python manage.py setup_backoffice_roles
```

Команда заменяет набор разрешений именованных групп, но не создаёт людей и не назначает им роли. Права Django User/Group, личных опросов и обезличивания не выдаются всем администраторам автоматически. [Роли и работа кабинета](django-admin.md).

## Перенос существующей SQLite-базы

Выполняется до обычного запуска `app`/bootstrap, в пустые legacy-таблицы PostgreSQL. Получите согласованный SQLite snapshot старого сервера; обычное копирование работающего файла без WAL/backup не подходит. Сохраните исходник отдельно. Команды ниже используют приватный snapshot `/private/path/legacy.sqlite3`; замените этот путь своим.

```sh
docker compose --env-file .env.production up -d db
docker compose --env-file .env.production build app
docker compose --env-file .env.production run --rm --no-deps app python manage.py migrate --noinput
sudo install -d -m 0700 -o 10001 -g 10001 .data/sqlite-import
sudo install -m 0400 -o 10001 -g 10001 /private/path/legacy.sqlite3 .data/sqlite-import/legacy.sqlite3
docker compose --env-file .env.production run --rm --no-deps -v "$PWD/.data/sqlite-import:/migration-source:ro" app python manage.py import_sqlite --source /migration-source/legacy.sqlite3 --dry-run
docker compose --env-file .env.production run --rm --no-deps -v "$PWD/.data/sqlite-import:/migration-source:ro" app python manage.py import_sqlite --source /migration-source/legacy.sqlite3
docker compose --env-file .env.production up -d
docker compose --env-file .env.production exec app python manage.py createsuperuser
```

Одноразовая команда переопределяет CMD контейнера, поэтому не выполняет bootstrap до импорта. Источник подключён read-only и доступен только контейнерному UID 10001. Importer проверяет схему всех 31 таблиц, FK и количество строк, сохраняет копию с SHA256 в постоянном `/app/.data/migration-backups`, переносит данные одной транзакцией. `--dry-run` откатывает записи и не создаёт копию. Исходный файл не меняется; стабильные ID, QR, баллы и история сохраняются. Отсутствующие старые определения мероприятий становятся скрытыми архивными заглушками.

Любая непустая целевая legacy-таблица приводит к отказу. После уже выполненного bootstrap нужен отдельный пустой PostgreSQL target; режима force/перезаписи нет. Не удаляйте рабочий volume ради повторной попытки. Полные условия — [runbook переноса](django-admin.md#перенос-старого-прототипа).

## Проверка размещения и настройки VK

С компьютера с Node и зависимостями проекта:

```sh
npm run check:deployment -- https://mini.example.ru
```

Команда проверяет доступность API и сборки, наличие VK-конфигурации, запрет dev-входа и поддельной подписи, закрытый пользовательский bootstrap и отсутствие заголовков, блокирующих iframe мини-приложения. Старые `/api/admin/*` должны возвращать `410 admin_api_retired`, а `/admin/` без персональной сессии направляет на вход. Проверка не заменяет настоящий запуск VK.

В настройках приложения 54850900 укажите одинаковый корень `https://mini.example.ru/` для поддерживаемых платформ и, если используется, режима разработки. Точные названия полей сверяйте с текущим кабинетом VK. Откройте [приложение из VK](https://vk.com/app54850900), включая мобильный клиент. Прямой домен без подписанных параметров не должен выдавать пользовательскую сессию.

Проверьте инициализацию, подпись запуска, анкету 18+, сохранение прогресса и баланса после повторного открытия, отклик с появлением в персональной HR-админке, запись на событие и QR. Отдельно проверьте HTTPS-вход админки, CSRF и ограничения каждой роли. URL с параметрами запуска и `sign` не передавайте другим людям. Разрешение уведомлений запрашивается только по действию пользователя.

## Обновления и резервные копии

Перед обновлением сохраните согласованный PostgreSQL dump и приватную конфигурацию:

```sh
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file .env.production exec -T db pg_dump -U ochakovo -d ochakovo -Fc > backups/ochakovo.dump
docker compose --env-file .env.production up -d --build
```

Меняйте имя копии, чтобы сохранять поколения, и переносите её в защищённое хранилище отдельно от VPS. `pg_dump` создаёт согласованную логическую копию, включая медиа и закрытые QR-токены; [документация PostgreSQL 16](https://www.postgresql.org/docs/16/app-pgdump.html). Восстановление проверяйте в отдельной пустой БД, см. [runbook](django-admin.md#резервные-копии-postgresql). SQLite-копия после миграции не отражает новые пользовательские действия.

Обычная пересборка сохраняет PostgreSQL/Caddy volumes. **Не используйте `docker compose down -v`** для обновлений: она удаляет постоянные данные. Автоматическое расписание копирования, внешнее хранилище и восстановление на момент времени этим Compose не настроены. Production-проверки Django можно выполнить через `python manage.py check --deploy`; [официальный checklist Django 5.2](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
