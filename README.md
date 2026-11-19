# Triply

Веб-приложение для планирования путешествий: поездка, места, план по дням, карта, бюджет и совместная работа.
Командный проект по дисциплине «Создание программного обеспечения», РТУ МИРЭА, группа ЭФБО-03-24.

| Роль | Участник |
| --- | --- |
| Тимлид / аналитик | Казакова А.В. |
| Frontend | Зайцев А.А. |
| Backend | Севостьянова Е.К. |

Стек: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Docker; React + TypeScript + Tailwind + Leaflet (frontend).

## Быстрый старт (Docker)

```bash
cp .env.example .env              # и поменять JWT_SECRET
docker compose up --build         # БД + API, миграции применяются сами
docker compose exec api python -m app.scripts.seed   # демо-данные
```

- Документация API (Swagger): http://localhost:8000/docs
- Проверка: http://localhost:8000/health
- Демо-вход: `demo@triply.ru` / `demo12345`

## Запуск без Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://triply:triply@localhost:5432/triply
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload
```

## Тесты

Тесты идут на настоящем PostgreSQL (отдельная база `triply_test`), схема создаётся миграциями:

```bash
cd backend
export TEST_DATABASE_URL=postgresql+psycopg://triply:triply@localhost:5432/triply_test
pytest
ruff check .
```

На каждый push их же запускает GitHub Actions (`.github/workflows/ci.yml`).

## Что сделано к КТ-1 (backend)

- Регистрация и вход: пароли argon2id, JWT на 24 часа.
- Поездки: создание, список, просмотр целиком, изменение, удаление. Дни маршрута создаются автоматически по датам;
  при сокращении дат активности не теряются, а уходят в «нераспределённые».
- Права: зависимость `require_trip_role()` на каждом методе поездки. Чужая поездка — 404, мало прав — 403.
- Места: добавление (вручную или из поиска), изменение, удаление, защита от дублей.
- План по дням: активности, время, заметки, оценка стоимости, перенос между днями, новый порядок после drag-and-drop.
- Поиск мест через Photon (OpenStreetMap) с кэшем в БД; поиск по клику на карте.
- Точки поездки для карты в формате GeoJSON (готово для Leaflet).
- Единый формат ошибок: `{"code", "message", "details"}`.
- 25 автотестов, линтер, CI, Docker, демо-данные.

Шпаргалка для показа и скриншоты — в [docs/demo-kt1.md](docs/demo-kt1.md).

## Структура backend

```
backend/
  app/api/        роутеры (auth, trips, places, geo)
  app/services/   бизнес-логика (дни и порядок активностей, поиск мест)
  app/models/     SQLAlchemy-модели
  app/schemas/    Pydantic-схемы запросов и ответов
  app/core/       настройки, безопасность, проверка прав, ошибки
  alembic/        миграции (схема БД задаётся здесь)
  tests/          pytest
```
