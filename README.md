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
cp .env.example .env          # впиши FOOTBALL_DATA_TOKEN (бесплатный ключ на football-data.org)
docker compose run --rm --build pipeline
```

Одна команда поднимает Postgres, применяет миграции и загружает все три источника.
CSV скачивается автоматически по зафиксированному коммиту (версия данных не зависит от ветки `main`).
Повторный запуск догружает только новое и ничего не дублирует. Расписание: та же команда из cron.
Ключ `--build` нужен, чтобы после изменений в коде не запускался старый образ.

Загрузить один источник: `docker compose run --rm --build pipeline python -m pipeline.run csv|football_data|rss`.

Схема БД: [docs/db_schema.md](docs/db_schema.md). Признаки: [docs/features.md](docs/features.md).

Таблица признаков: `docker compose run --rm --build ml`.
Обучение, сравнение моделей и прогнозы: `docker compose run --rm --build ml python -m ml.train` (описание: [docs/models.md](docs/models.md)).
Отбор признаков: `docker compose run --rm --build ml python -m ml.select_features`.
Тесты (в том числе на утечку): `cd backend && python -m pytest`.

## Ноутбук с результатами

`notebooks/overview.ipynb` показывает данные, качество посещаемости, признаки, сравнение моделей и прогнозы (код берётся из `backend/`, цифры совпадают с системой).
`notebooks/overview.html` — та же страница без кода, её удобно отправлять. Пересчитать после новых данных:

```bash
cd notebooks && ../.venv/bin/python -m nbconvert --to notebook --execute overview.ipynb --inplace && ../.venv/bin/python -m nbconvert --to html --no-input overview.ipynb
```

## Сбор данных

| Требование | Реализация |
|---|---|
| Инкрементальность | football-data.org: по `lastUpdated` каждого матча отдельно для сезона; RSS: дедупликация по ссылке на статью; CSV: UPSERT по `(season, home, away)` |
| Идемпотентность | `INSERT ... ON CONFLICT DO UPDATE ... WHERE <значения изменились>`: повторный запуск даёт 0 вставок и 0 обновлений |
| Устойчивость к сбоям | таймауты, повторы с нарастающей паузой, ожидание при лимите запросов (429), сбой одного источника не останавливает остальные |
| Журнал загрузок | таблица `ingest_runs`: источник, статус, сколько получено / вставлено / обновлено / пропущено / отклонено, ошибка, водяной знак |
| Контроль качества | таблица `dq_checks`: проверки диапазонов, полноты сезонов, согласованности источников |

Если один матч пришёл из двух источников, общие поля (время, тур, статус, счёт) берутся из API,
а поля, которые есть только в CSV (посещаемость, стадион, судья, дерби), из CSV. Итог не зависит от порядка запуска.

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
