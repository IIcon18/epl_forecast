import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

FEATURE_GROUPS = {
    "calendar": ["weekday", "month", "is_weekend", "is_holiday_period", "days_into_season"],
    "context": ["is_derby"],
    "form": ["h_ppg5", "a_ppg5", "h_gd5", "a_gd5", "rest_days_h", "rest_days_a"],
    "table": ["h_played", "a_played", "h_season_ppg", "a_season_ppg", "h_pos", "a_pos",
              "h_prev_ppg", "a_prev_ppg"],
    "attendance_history": ["att_hist_n", "att_last1", "att_mean3", "att_mean10", "att_median_all",
                           "att_cap_proxy", "att_days_since_hist"],
    "opponent_pull": ["away_pull"],
    "club": ["home_team_id"],
    "news": ["h_news_count", "a_news_count", "h_news_sent", "a_news_sent"],
}
CATEGORICAL = {"home_team_id"}
SELECTED_PATH = Path(__file__).with_name("selected_features.json")
TEST_SEASON = 2022
LAST_TRAIN_SEASON = 2018


def load_dataset(conn: Connection) -> pd.DataFrame:
    df = pd.read_sql(text(
        "SELECT m.id AS match_id, m.season, m.match_date, m.status, m.attendance, "
        "m.attendance_status, f.features FROM matches m JOIN match_features f ON f.match_id = m.id"
    ), conn)
    features = pd.json_normalize(df.pop("features")).astype(float)
    df = pd.concat([df, features], axis=1)
    df["baseline"] = df["att_mean10"].fillna(df["att_median_all"])
    return df


def trainable(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["attendance_status"] == "ok") & df["baseline"].notna()].sort_values("match_id")


def constant_features(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [c for c in columns if df[c].nunique(dropna=True) <= 1]


def selected_features(data: pd.DataFrame) -> list[str]:
    if SELECTED_PATH.exists():
        return json.loads(SELECTED_PATH.read_text())["features"]
    columns = [c for cols in FEATURE_GROUPS.values() for c in cols]
    constant = set(constant_features(data, columns))
    return [c for c in columns if c not in constant]


def split_columns(features: list[str]) -> tuple[list[str], list[str]]:
    return ([f for f in features if f not in CATEGORICAL],
            [f for f in features if f in CATEGORICAL])


def data_hash(data: pd.DataFrame, features: list[str]) -> str:
    columns = ["match_id", "attendance", "baseline", *features]
    hashed = pd.util.hash_pandas_object(data[columns].round(6), index=False)
    return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()
