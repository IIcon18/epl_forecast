# Архитектура системы

Пунктирные блоки ещё не реализованы.

```mermaid
flowchart TB
    subgraph SRC["Источники данных"]
        CSV["CSV: история матчей 2000–2026<br/>(файл, разовая загрузка)"]
        API["football-data.org<br/>(REST API, инкрементально)"]
        RSS["BBC Sport RSS<br/>(текст новостей)"]
    end

    subgraph PIPE["Сбор данных: backend/pipeline"]
        COL["Сборщики: повторы, лимиты запросов,<br/>UPSERT (идемпотентность)"]
        DQ["Проверки качества и<br/>разметка достоверности посещаемости"]
    end

    subgraph DB["PostgreSQL (миграции Alembic)"]
        RAW["Сырые факты:<br/>teams, matches, news_articles"]
        OPS["Служебные: ingest_runs (журнал),<br/>dq_checks"]
        FEAT["match_features<br/>(витрина признаков)"]
        REG["experiments, model_versions,<br/>predictions"]
    end

    subgraph ML["Признаки и модели: backend/ml"]
        FB["features.py<br/>один код для обучения и прогноза"]
        TR["train.py: наивная база, линейная,<br/>бустинг, лес; проверка во времени"]
        ART[("models/*.joblib")]
    end

    NB["notebooks/overview<br/>(обзор для отчёта)"]
    BACK["FastAPI"]
    DASH["Дашборд React"]
    OPT["Факультативные: интерпретируемость,<br/>журнал экспериментов, мониторинг"]

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
    FEAT --> TR
    TR --> REG
    TR --> ART
    REG --> NB
    OPS --> NB
    REG -.-> BACK
    ART -.-> BACK
    BACK -.-> DASH
    REG -.-> OPT
    OPT -.-> DASH

    classDef planned stroke-dasharray: 5 5
    class BACK,DASH,OPT planned
```

## Как запускается

```
docker compose run --rm --build pipeline                       сбор данных (+ миграции, база)
docker compose run --rm --build ml                              признаки
docker compose run --rm --build ml python -m ml.train           обучение, прогнозы
```

## Слои

| Слой | Где | Что делает |
|---|---|---|
| Источники и сбор | `backend/pipeline/` | Забирает данные, не дублирует, переживает сбои, пишет журнал |
| Хранилище | PostgreSQL, `backend/db/`, `backend/alembic/` | Сырые факты, журнал, результаты проверок, признаки, реестр моделей |
| Качество | `pipeline/quality.py` | Проверки и пометка недостоверных сезонов посещаемости |
| Признаки | `backend/ml/features.py` | Лаговые, оконные, календарные признаки без утечки из будущего |
| Модели | `backend/ml/train.py` и др. | Обучение, проверка во времени, реестр версий, прогнозы |
| Показ | `backend/api`, `frontend/` (план) | API и дашборд |
