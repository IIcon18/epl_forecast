# epl_forecast

Прогнозно-аналитическая система: прогноз посещаемости матчей английской Премьер-лиги.
Проектный практикум, предметная область № 29 «Спортивная индустрия».

## Стек

Python · FastAPI · PostgreSQL 16 · SQLAlchemy 2 + Alembic · React · Docker Compose

## Источники данных

| Источник | Что даёт | Тип |
|---|---|---|
| [EPL match dataset (RezaGooner, CC BY-NC 4.0)](https://github.com/RezaGooner/english-premier-league-match-dataset) | история матчей 2000–2026 с посещаемостью | CSV, разовая загрузка |
| [football-data.org](https://www.football-data.org) | текущие результаты и расписание | REST API, инкрементально |
| BBC Sport RSS | новости для признаков тональности | RSS / текст |

## Запуск

```bash
cp .env.example .env          # впиши FOOTBALL_DATA_TOKEN
docker compose up -d db
docker compose run --rm migrate
```

Схема БД: [docs/db_schema.md](docs/db_schema.md).

## Структура

```
backend/
  db/          модели SQLAlchemy и конфигурация подключения
  alembic/     миграции
  pipeline/    сбор данных
  ml/          признаки и модели
  api/         FastAPI
frontend/      дашборд
scratch/       разведочные скрипты проверки источников
docs/          документация
```

_README дополняется по мере реализации этапов._
