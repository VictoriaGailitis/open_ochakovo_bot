# Локальный запуск

Нужны Node.js 22+, Python 3.13 и запущенный Docker. Команды выполняются из корня репозитория:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/setup-local.py
npm ci
npm run dev
```

- Приложение: http://127.0.0.1:5188
- Админка: http://127.0.0.1:3001/admin/
- Локальные данные входа администратора: `.data/django-local-admin.json` (создаётся при подготовке; не коммитится).

`setup-local.py` поднимает PostgreSQL на `127.0.0.1:55432` и создаёт локальный `.env`. `npm run dev` подготавливает миграции и начальный контент, запускает Django и Vite. Данные сохраняются в Docker volume `open_ochakovo_pgdata`; повторный запуск не заменяет существующие настройки. Локальный режим использует `DEV_AUTH=1`, без проверки реального запуска VK. Демо-доступы опубликованного стенда не являются доступами новой локальной установки.

## Проверки

```sh
npm run build
npm test
```

Сборка проверяет TypeScript и создаёт `dist/`. `npm test` запускает серверные, Django/Unfold и TypeScript-тесты; нужен доступный локальный PostgreSQL. Только Django/Unfold можно проверить командой `npm run test:django`. Для проверки размещённой версии: `npm run check:deployment -- https://mini.example.ru https://admin.example.ru`.

## Где что находится

| Каталог | Назначение |
|---|---|
| `src/` | React-интерфейс; `games/` — игры, `practice/` — кабинеты сотрудников |
| `public/assets/` | Иллюстрации и игровые ассеты |
| `server/` | API, бизнес-правила, проверка решений и начальный контент |
| `backoffice/` | Django-проект: модели, миграции, Unfold, роли и редакторы |
| `scripts/` | Подготовка среды, тесты и проверка развёртывания |
| `deploy/`, `compose.yaml`, `Dockerfile` | Контейнерный запуск и HTTPS |

[Развёртывание на сервере и подключение VK](vk-deployment.md) · [Назад к описанию продукта](../README.md)
