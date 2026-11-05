import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def load_matches(conn: Connection) -> pd.DataFrame:
    return pd.read_sql(text(
        "SELECT id AS match_id, season, match_date, home_team_id, away_team_id, status, "
        "home_goals, away_goals, attendance, attendance_status, stadium, is_derby FROM matches"
    ), conn)


def load_news(conn: Connection) -> pd.DataFrame:
    return pd.read_sql(text(
        "SELECT l.team_id, a.published_at, a.title, a.summary "
        "FROM news_articles a JOIN news_article_teams l ON l.article_id = a.id"
    ), conn)
