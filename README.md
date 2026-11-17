# Прогноз посещаемости матчей АПЛ

Прогнозно-аналитическая система: собирает данные о матчах английской Премьер-лиги и новости, хранит их в PostgreSQL,
строит признаки, обучает и сравнивает модели, показывает факт, прогноз и качество модели на дашборде.

Проектный практикум, предметная область № 29 «Спортивная индустрия» (посещаемость матчей).
Пользователь системы: аналитик клуба или лиги, которому нужно знать ожидаемую посещаемость предстоящих матчей.

## Архитектура

Схема потоков данных: [docs/architecture.md](docs/architecture.md).

```
CSV (история)       ─┐
football-data.org   ─┼─►  pipeline  ─►  PostgreSQL  ─►  признаки  ─►  модели  ─►  Grafana
RSS BBC Sport       ─┘   (сбор)         (хранение)     (ml)          (ml)        FastAPI
```

| Слой | Технология | Где |
|---|---|---|
| Сбор данных | Python, requests, feedparser | `backend/pipeline/` |
| Хранение | PostgreSQL 16, SQLAlchemy 2, Alembic | `backend/db/`, `backend/alembic/` |
| Признаки и модели | pandas, scikit-learn | `backend/ml/` |
| API | FastAPI | `backend/api/` |
| Дашборд | Grafana 11 | `grafana/` |
| Запуск | Docker Compose | `docker-compose.yml` |

Дашборд сделан на Grafana: она читает базу напрямую, даёт фильтры и автообновление, а дашборд хранится в репозитории файлом.

## Быстрый старт

Нужны Docker и бесплатный ключ [football-data.org](https://www.football-data.org).

```bash
cp .env.example .env                                          # впиши FOOTBALL_DATA_TOKEN
docker compose run --rm --build pipeline                      # база, миграции, загрузка трёх источников
docker compose run --rm --build ml                            # признаки
docker compose run --rm --build ml python -m ml.train         # обучение, сравнение моделей, прогнозы
docker compose up -d --build grafana api                      # дашборд и API
```

- Дашборд: http://localhost:3000 (просмотр без входа; администратор `admin`, пароль в `GRAFANA_ADMIN_PASSWORD`)
- API и пробные запросы: http://localhost:8000/docs

Ключ `--build` нужен всегда: без него Docker запускает старый образ без свежих миграций и кода.
Без токена CSV и RSS загрузятся, а football-data.org будет помечен в журнале как `failed`.
Сброс: `docker compose down -v` удаляет базу, шаги выше создают её заново.

Конфигурация только через `.env` и переменные окружения (шаблон: `.env.example`), в репозиторий секреты не попадают.

## Что внутри и где это проверить

| Требование | Реализация | Подробности |
|---|---|---|
| Несколько разнородных источников | CSV, REST API, RSS (текст) | ниже |
| Инкрементальность и идемпотентность | UPSERT по `(season, home, away)`, водяные знаки по `lastUpdated`, дедупликация RSS; повторный запуск: 0 вставок, 0 обновлений | [docs/db_schema.md](docs/db_schema.md) |
| Устойчивость к сбоям, журнал загрузок | повторы с паузой, лимит запросов (429), сбой источника не останавливает остальные; таблица `ingest_runs` | |
| Контроль качества данных | таблица `dq_checks`, разметка достоверности посещаемости | [docs/db_schema.md](docs/db_schema.md) |
| Признаки без утечки | лаговые, оконные, календарные, тональность новостей; единый код для обучения и прогноза; 43 теста на утечку | [docs/features.md](docs/features.md) |
| Модели и валидация | наивная база, линейная модель, бустинг, случайный лес; проверка во времени; метрики в зрителях и в % вместимости | [docs/models.md](docs/models.md) |
| Реестр экспериментов и версий моделей | таблицы `experiments`, `model_versions`, `predictions` | [docs/models.md](docs/models.md) |
| Дашборд | Grafana: факт, прогноз, качество модели, фильтры, автообновление | `grafana/dashboards/overview.json` |

### Источники данных

| Источник | Что даёт | Тип |
|---|---|---|
| [EPL match dataset (RezaGooner, CC BY-NC 4.0)](https://github.com/RezaGooner/english-premier-league-match-dataset) | история матчей 2000–2026 с посещаемостью | CSV, скачивается автоматически по зафиксированному коммиту |
| [football-data.org](https://www.football-data.org) | текущие результаты и расписание | REST API, инкрементально |
| BBC Sport RSS | новости клубов | RSS, слабоструктурированный текст |

Посещаемость API football-data.org не отдаёт, поэтому её источник — CSV.

## Результаты и ограничения

- **Посещаемость в CSV недостоверна для сезонов 2019/20, 2021/22, 2023/24, 2024/25 и 2025/26** (не связана со стадионом).
  Система размечает такие матчи сама (`attendance_status`), обучается и оценивается на 7 600 достоверных матчах.
- **Посещаемость почти полностью определяется вместимостью стадиона.** Ошибка наивного прогноза (средняя посещаемость последних
  10 домашних матчей) около 1,5 тысячи зрителей (≈ 4 % вместимости). Лучшая модель (бустинг) на его уровне: выигрыш около 0,3 %.
  Подробности и таблицы: [docs/models.md](docs/models.md).
- Переезды и расширения стадионов по данным не видны, для прогноза на 2026/27 последняя достоверная история относится к 2022/23.

## Разработка

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
docker compose up -d db
(cd backend && ../.venv/bin/python -m alembic upgrade head)
(cd backend && ../.venv/bin/python -m pytest -q)        # 54 теста; тесты API пропускаются без базы
```

- Миграции: `cd backend && ../.venv/bin/python -m alembic revision --autogenerate -m "описание"`.
- Отбор признаков: `docker compose run --rm --build ml python -m ml.select_features`.
- Загрузить один источник: `docker compose run --rm --build pipeline python -m pipeline.run csv|football_data|rss`.
- Расписание: та же команда `pipeline` из cron.
- Дашборд можно править в интерфейсе Grafana, но правка хранится только в самой Grafana. Чтобы сохранить в репозитории:
  Share → Export → Save to file и заменить `grafana/dashboards/overview.json`.
- Ноутбук с результатами `notebooks/overview.ipynb` (`overview.html` — то же без кода, для отправки):
  `cd notebooks && ../.venv/bin/python -m nbconvert --to notebook --execute overview.ipynb --inplace`.

## Структура

```
backend/
  db/          модели SQLAlchemy, подключение
  alembic/     миграции
  pipeline/    сбор данных, проверки качества, журнал загрузок
  ml/          признаки, обучение, валидация, реестр
  api/         FastAPI
  tests/       тесты (в том числе на утечку признаков)
grafana/       источник данных и дашборд
notebooks/     обзор данных и моделей
docs/          схема БД, признаки, модели, архитектура
scratch/       разведочные скрипты проверки источников
```
