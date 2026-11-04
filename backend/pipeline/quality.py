import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import DqCheck
from pipeline import settings

MAX_ATTENDANCE = 100_000
MIN_CORRELATION = 0.85
MIN_COMPARABLE_MATCHES = 100
NEWS_MAX_AGE_DAYS = 7


def record(session: Session, run_id: int, table: str, name: str, severity: str,
           passed: bool, details: dict | None = None) -> None:
    session.add(DqCheck(run_id=run_id, table_name=table, check_name=name,
                        severity=severity, passed=passed, details=details))


def season_consistency(matches: pd.DataFrame) -> list[dict]:
    played = matches[(matches["attendance"] > 0) & matches["stadium"].notna()]
    result = []
    for season, group in played.groupby("season"):
        baseline = played[played["season"] != season].groupby("stadium")["attendance"].median()
        comparable = group.assign(base=group["stadium"].map(baseline)).dropna(subset=["base"])
        corr = comparable["attendance"].corr(comparable["base"]) if len(comparable) > 2 else None
        result.append({
            "season": int(season),
            "comparable": len(comparable),
            "correlation": None if corr is None or pd.isna(corr) else round(float(corr), 2),
        })
    return result


def flag_attendance(session: Session, run_id: int) -> None:
    """Размечает посещаемость: ok / fanless / suspect / missing."""
    matches = pd.read_sql(text("SELECT season, stadium, attendance FROM matches"), session.connection())
    seasons = season_consistency(matches)
    suspect = [
        s["season"] for s in seasons
        if s["comparable"] < MIN_COMPARABLE_MATCHES
        or s["correlation"] is None or s["correlation"] < MIN_CORRELATION
    ]
    status = (
        "CASE WHEN attendance IS NULL THEN 'missing' WHEN attendance = 0 THEN 'fanless' "
        "WHEN season = ANY(CAST(:suspect AS int[])) THEN 'suspect' ELSE 'ok' END"
    )
    session.execute(
        text(f"UPDATE matches SET attendance_status = {status} "
             f"WHERE attendance_status IS DISTINCT FROM {status}"),
        {"suspect": suspect},
    )
    record(session, run_id, "matches", "attendance_consistent_with_stadium", "warn", not suspect,
           {"min_correlation": MIN_CORRELATION, "suspect_seasons": suspect, "seasons": seasons})


def check_matches(session: Session, run_id: int) -> None:
    season = settings.current_season()

    def scalar(sql: str, **params):
        return session.execute(text(sql), params).scalar()

    def rows(sql: str, **params):
        return [dict(r._mapping) for r in session.execute(text(sql), params)]

    n = scalar("SELECT count(*) FROM matches WHERE attendance > :m", m=MAX_ATTENDANCE)
    record(session, run_id, "matches", "attendance_not_above_100k", "error", n == 0, {"violations": n})

    fanless = rows(
        "SELECT season, count(*) AS matches FROM matches WHERE attendance = 0 "
        "GROUP BY season ORDER BY season"
    )
    record(session, run_id, "matches", "fanless_matches", "warn", not fanless, {"by_season": fanless})

    bad = rows(
        "SELECT m.season, m.matches, t.teams "
        "FROM (SELECT season, count(*) AS matches FROM matches GROUP BY season) m "
        "JOIN (SELECT season, count(DISTINCT team) AS teams FROM ("
        "  SELECT season, home_team_id AS team FROM matches UNION ALL "
        "  SELECT season, away_team_id FROM matches) u GROUP BY season) t ON t.season = m.season "
        "WHERE m.season < :cur AND (m.matches <> 380 OR t.teams <> 20) ORDER BY m.season",
        cur=season,
    )
    record(session, run_id, "matches", "completed_seasons_380_matches_20_teams", "error",
           not bad, {"violations": bad})

    n = scalar(
        "SELECT count(DISTINCT team) FROM ("
        "  SELECT home_team_id AS team FROM matches WHERE season = :cur UNION ALL "
        "  SELECT away_team_id FROM matches WHERE season = :cur) u",
        cur=season,
    )
    record(session, run_id, "matches", "current_season_at_most_20_teams", "error", n <= 20, {"teams": n})

    n = scalar(
        "SELECT count(*) FROM matches WHERE status = 'FINISHED' "
        "AND (home_goals IS NULL OR away_goals IS NULL)"
    )
    record(session, run_id, "matches", "finished_matches_have_score", "error", n == 0, {"violations": n})

    n = scalar(
        "SELECT count(*) FROM matches WHERE status IN ('SCHEDULED', 'TIMED') "
        "AND (home_goals IS NOT NULL OR away_goals IS NOT NULL)"
    )
    record(session, run_id, "matches", "future_matches_have_no_score", "error", n == 0, {"violations": n})

    n = scalar(
        "SELECT count(*) FROM matches WHERE season < :cur AND status = 'FINISHED' "
        "AND attendance IS NULL",
        cur=season,
    )
    record(session, run_id, "matches", "completed_matches_have_attendance", "warn", n == 0, {"missing": n})


def check_news(session: Session, run_id: int) -> None:
    age = session.execute(
        text("SELECT EXTRACT(EPOCH FROM (now() - max(published_at))) / 86400 FROM news_articles")
    ).scalar()
    record(session, run_id, "news_articles", "news_not_stale", "warn",
           age is not None and age <= NEWS_MAX_AGE_DAYS,
           {"newest_article_age_days": None if age is None else round(float(age), 2)})

    n = session.execute(
        text("SELECT count(*) FROM news_articles WHERE trim(title) = ''")
    ).scalar()
    record(session, run_id, "news_articles", "titles_not_empty", "error", n == 0, {"violations": n})
