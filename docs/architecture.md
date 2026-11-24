# Архитектура системы

```mermaid
flowchart TB
    subgraph SRC["Источники данных"]
        CSV["CSV: история матчей 2000–2026<br/>(файл, разовая загрузка)"]
        API["football-data.org<br/>(REST API, инкрементально)"]
        RSS["BBC Sport RSS<br/>(текст новостей)"]
    end

    SCH["Планировщик (scheduler)<br/>раз в N часов запускает три шага"]

    subgraph PIPE["1. Сбор данных: backend/pipeline"]
        COL["Сборщики: повторы, лимиты запросов,<br/>UPSERT (идемпотентность)"]
        DQ["Проверки качества и разметка<br/>достоверности посещаемости"]
    end

    subgraph DB["PostgreSQL (миграции Alembic)"]
        RAW["Сырые факты:<br/>teams, matches, news_articles"]
        OPS["Служебные: ingest_runs (журнал),<br/>dq_checks"]
        FEAT["match_features<br/>(витрина признаков)"]
        REG["experiments, model_versions,<br/>predictions"]
        VIEWS["Представления для дашборда:<br/>v_match_forecast, v_model_quality"]
    end

    subgraph ML["backend/ml"]
        FB["2. build_features.py<br/>один код признаков для обучения и прогноза<br/>+ проверки качества витрины"]
        PR["3. predict.py: прогноз новых матчей<br/>рабочей моделью"]
        TR["train.py: наивная база, линейная модель,<br/>бустинг, лес; подбор параметров и проверка во времени"]
        ART[("models/*.joblib")]
    end

    GF["Grafana: дашборд и служебный дашборд<br/>(читает под пользователем только на чтение)"]
    BACK["FastAPI: модель, матчи, качество"]
    NB["notebooks/overview<br/>(обзор для отчёта)"]
    REPLAY["reproduce.py: повтор эксперимента по ID"]

    CSV --> COL
    API --> COL
    RSS --> COL
    COL --> RAW
    COL --> OPS
    RAW --> DQ
    DQ --> OPS
    DQ --> RAW
    RAW --> FB
    FB --> FEAT
    FB --> OPS
    FEAT --> TR
    TR --> REG
    TR --> ART
    ART --> PR
    FEAT --> PR
    PR --> REG
    REG --> VIEWS
    RAW --> VIEWS
    VIEWS --> GF
    OPS --> GF
    REG --> BACK
    REG --> NB
    OPS --> NB
    SCH --> COL
    SCH --> FB
    SCH --> PR
    REG --> REPLAY
    FEAT --> REPLAY
    REG --> GF
```

## Как запускается

```
docker compose run --rm --build pipeline                       сбор данных (+ миграции, база)
docker compose run --rm --build ml                              признаки
docker compose run --rm --build ml python -m ml.train           обучение, выбор модели, прогнозы
docker compose up -d --build grafana api                        дашборд и API
docker compose --profile schedule up -d --build scheduler       регулярное обновление (по желанию)
```

## Слои

| Слой | Где | Что делает |
|---|---|---|
| Источники и сбор | `backend/pipeline/` | Забирает данные, не дублирует, переживает сбои, пишет журнал |
| Хранилище | PostgreSQL, `backend/db/`, `backend/alembic/` | Сырые факты, журнал, результаты проверок, признаки, реестр моделей |
| Качество | `pipeline/quality.py`, `ml/quality.py` | Проверки входных данных, разметка недостоверных сезонов, проверки витрины признаков |
| Признаки | `backend/ml/features.py` | Лаговые, оконные, календарные признаки без утечки из будущего |
| Модели | `backend/ml/train.py`, `predict.py` | Обучение и выбор модели, версии, прогноз новых матчей без переобучения |
| Показ | `grafana/`, `backend/api/` | Дашборды и API |
| Регулярность | `backend/scheduler.py` | Раз в N часов: сбор, признаки, прогноз |
