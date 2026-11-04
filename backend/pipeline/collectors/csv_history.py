import hashlib
import logging

import pandas as pd

from db.session import SessionLocal
from pipeline import quality, settings
from pipeline.http import get
from pipeline.journal import ingest_run
from pipeline.teams import TeamRegistry, seed_teams
from pipeline.upsert import upsert_matches

log = logging.getLogger(__name__)
SOURCE = "csv_history"
API_OWNED = frozenset({
    "match_date", "kickoff_utc", "matchday", "status", "home_goals", "away_goals",
    "football_data_id",
})
REQUIRED = {
    "Season", "Year", "Month", "Day", "Time", "Round", "HomeTeam", "AwayTeam",
    "HomeGoal", "AwayGoal", "Attendance", "Referee", "HomeStadium", "IsDerby",
}


def ensure_file():
    path = settings.CSV_PATH
    if not path.exists():
        log.info("Скачиваю CSV: %s", settings.CSV_URL)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(get(settings.CSV_URL).content)
        tmp.replace(path)
    return path


def optional_int(value):
    return None if pd.isna(value) else int(value)


def optional_str(value):
    return None if pd.isna(value) else str(value)


def build_rows(df: pd.DataFrame, registry: TeamRegistry) -> tuple[list[dict], int]:
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"в CSV нет колонок: {sorted(missing)}")

    dates = pd.to_datetime(
        {"year": df["Year"], "month": df["Month"], "day": df["Day"]}, errors="coerce"
    )
    kickoff = (
        pd.to_datetime(dates.dt.strftime("%Y-%m-%d") + " " + df["Time"].astype(str), errors="coerce")
        .dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT")
        .dt.tz_convert("UTC")
    )

    rows, rejected = [], 0
    for i, rec in enumerate(df.to_dict("records")):
        season_code = str(rec["Season"])
        if pd.isna(dates.iloc[i]) or not season_code.isdigit() or pd.isna(rec["Attendance"]):
            rejected += 1
            continue
        k = kickoff.iloc[i]
        rows.append({
            "season": 2000 + int(season_code[:2]),
            "match_date": dates.iloc[i].date(),
            "kickoff_utc": None if pd.isna(k) else k.to_pydatetime(),
            "matchday": optional_int(rec["Round"]),
            "home_team_id": registry.resolve(rec["HomeTeam"]),
            "away_team_id": registry.resolve(rec["AwayTeam"]),
            "status": "FINISHED",
            "home_goals": optional_int(rec["HomeGoal"]),
            "away_goals": optional_int(rec["AwayGoal"]),
            "attendance": optional_int(rec["Attendance"]),
            "stadium": optional_str(rec["HomeStadium"]),
            "referee": optional_str(rec["Referee"]),
            "is_derby": {"Yes": True, "No": False}.get(rec["IsDerby"]),
            "football_data_id": None,
            "source": SOURCE,
        })
    return rows, rejected


def run() -> None:
    path = ensure_file()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    with ingest_run(SOURCE, {"file": path.name, "sha256": sha256, "url": settings.CSV_URL}) as (run_id, stats):
        df = pd.read_csv(path, dtype={"Season": str})
        stats.fetched = len(df)
        with SessionLocal.begin() as session:
            seed_teams(session)
            registry = TeamRegistry(session)
            rows, stats.rejected = build_rows(df, registry)
            stats.inserted, stats.updated, stats.skipped = upsert_matches(
                session, rows, prefer_existing=API_OWNED)
        with SessionLocal.begin() as session:
            quality.check_matches(session, run_id)
        log.info("csv_history: получено %d, вставлено %d, обновлено %d, без изменений %d, отклонено %d",
                 stats.fetched, stats.inserted, stats.updated, stats.skipped, stats.rejected)
