# Схема базы данных

Миграции: Alembic (`backend/alembic/versions`), модели: `backend/db/models.py`.
Применить: `docker compose run --rm migrate`.

```mermaid
erDiagram
    teams ||--o{ team_aliases : "названия в источниках"
    teams ||--o{ matches : "home_team_id"
    teams ||--o{ matches : "away_team_id"
    teams ||--o{ news_article_teams : "упомянута в"
    news_articles ||--o{ news_article_teams : "упоминает"
    ingest_runs ||--o{ dq_checks : "проверки запуска"

    teams {
        int id PK
        string name UK
        int football_data_id UK
    }
    team_aliases {
        string alias PK
        int team_id FK
    }
    matches {
        int id PK
        smallint season
        date match_date
        timestamptz kickoff_utc
        smallint matchday
        int home_team_id FK
        int away_team_id FK
        string status
        smallint home_goals
        smallint away_goals
        int attendance "целевая переменная"
        string stadium
        string referee
        bool is_derby
        int football_data_id UK
        string source
    }
    news_articles {
        int id PK
        string source
        text guid "UK вместе с source"
        text title
        text summary
        text url
        timestamptz published_at
    }
    news_article_teams {
        int article_id PK
        int team_id PK
    }
    ingest_runs {
        int id PK
        string source
        timestamptz started_at
        timestamptz finished_at
        string status
        int rows_fetched
        int rows_inserted
        int rows_updated
        int rows_skipped
        timestamptz watermark
        text error
        jsonb params
    }
    dq_checks {
        int id PK
        int run_id FK
        string table_name
        string check_name
        string severity
        bool passed
        jsonb details
    }
```

## Ключевые решения

| Решение | Зачем |
|---|---|
| Внешние ключи на `teams.id`, а не на название | Источники называют клуб по-разному (`Man City` / `Manchester City FC`). Сопоставление делается один раз при загрузке через `team_aliases`. |
| `UNIQUE (season, home_team_id, away_team_id)` в `matches` | В чемпионате пара «хозяева–гости» встречается в сезоне ровно один раз. Это естественный ключ для UPSERT: исторический CSV и live-API описывают один и тот же матч и не создадут дубль. Отсюда идемпотентность. |
| `season` — число (год начала сезона: 2023 = 2023/24) | В CSV сезон записан строкой `"2324"`, pandas по умолчанию теряет ведущие нули (`"0001"` → `1`). Число однозначно и сортируется. |
| Итоги и посещаемость — колонки `matches`, а не отдельная таблица | Один матч = один результат (связь 1:1). |
| `attendance`, `home_goals`, `away_goals` допускают NULL | Будущие матчи из football-data.org ещё не сыграны. |
| Стадион хранится в матче, а не в клубе | Клубы меняют стадион (Вест Хэм в 2016 г.), для старых матчей значение клуба было бы неверным. |
| В БД хранятся только **сырые факты** | Позиция в таблице, форма, лаги и тональность вычисляются в слое признаков. Колонки CSV `SeasonPos*`/`SeasonPoints*`/`SeasonPlayed*` — это **итоговая** таблица сезона (`played = 38` в каждой строке), использовать их как признаки нельзя: это утечка из будущего. |
| Новости привязаны к клубам через `news_article_teams` (M:N), а не к матчу | Статья про трансфер или травму не относится к одному матчу и может упоминать несколько клубов. Окно «новости клуба за N дней до матча» собирается на этапе признаков. |
| `UNIQUE (source, guid)` в `news_articles` | Идемпотентная загрузка RSS: повторный запуск не дублирует статьи. |
| `ingest_runs` с `watermark` | Журнал загрузок (требование задания) и точка, с которой нужно догружать данные при следующем запуске (инкрементальность). |
| `dq_checks` | Контроль качества данных (требование задания): результаты проверок сохраняются и привязаны к запуску. |

## Что добавится следующими миграциями

- `0002`: `model_versions` (реестр моделей), `predictions`, таблицы для журнала экспериментов и мониторинга.
