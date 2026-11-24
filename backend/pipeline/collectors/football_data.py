import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from db.models import Match
from db.session import SessionLocal
from pipeline import quality, settings
from pipeline.http import get
from pipeline.journal import ingest_run, last_success_params
from pipeline.teams import TeamRegistry, seed_teams
from pipeline.upsert import upsert_matches

log = logging.getLogger(__name__)
SOURCE = "football_data"
LONDON = ZoneInfo("Europe/London")


def fetch_season(season: int) -> list[dict]:
    resp = get(
        f"{settings.FOOTBALL_DATA_URL}/competitions/PL/matches",
        headers={"X-Auth-Token": settings.FOOTBALL_DATA_TOKEN},
        params={"season": season},
    )
    if int(resp.headers.get("X-Requests-Available-Minute", 1)) <= 0:
        time.sleep(int(resp.headers.get("X-RequestCounter-Reset", 60)) + 1)
    return resp.json()["matches"]


def to_row(match: dict, registry: TeamRegistry) -> dict | None:
    home, away = match["homeTeam"], match["awayTeam"]
    if not home.get("name") or not away.get("name"):
        return None
    kickoff = datetime.fromisoformat(match["utcDate"])
    full_time = match["score"]["fullTime"]
    return {
        "season": int(match["season"]["startDate"][:4]),
        "match_date": kickoff.astimezone(LONDON).date(),
        "kickoff_utc": kickoff,
        "matchday": match.get("matchday"),
        "home_team_id": registry.resolve(home["name"], home.get("shortName"), home["id"]),
        "away_team_id": registry.resolve(away["name"], away.get("shortName"), away["id"]),
        "status": match["status"],
        "home_goals": full_time["home"],
        "away_goals": full_time["away"],
        "attendance": match.get("attendance"),
        "stadium": match.get("venue"),
        "referee": None,
        "is_derby": None,
        "football_data_id": match["id"],
        "source": SOURCE,
    }


def compare_with_history(session, rows: list[dict]) -> dict[str, dict]:
    """Сверка с матчами, пришедшими из CSV (ещё не видевшими API)."""
    seasons = {r["season"] for r in rows}
    stored = {
        (m.season, m.home_team_id, m.away_team_id): m
        for m in session.scalars(select(Match).where(Match.season.in_(seasons)))
        if m.football_data_id is None
    }
    result = {name: {"compared": 0, "mismatched": 0, "examples": []}
              for name in ("score", "kickoff", "matchday")}
    for r in rows:
        old = stored.get((r["season"], r["home_team_id"], r["away_team_id"]))
        if old is None:
            continue
        pairs = {
            "score": ((old.home_goals, old.away_goals), (r["home_goals"], r["away_goals"])),
            "kickoff": (old.kickoff_utc, r["kickoff_utc"]),
            "matchday": (old.matchday, r["matchday"]),
        }
        for name, (was, now) in pairs.items():
            if was is None or now is None or (isinstance(was, tuple) and None in was + now):
                continue
            result[name]["compared"] += 1
            if was != now:
                result[name]["mismatched"] += 1
                if len(result[name]["examples"]) < 3:
                    result[name]["examples"].append(
                        {"season": r["season"], "csv": str(was), "api": str(now)})
    return result


def run() -> None:
    if not settings.FOOTBALL_DATA_TOKEN:
        raise RuntimeError("FOOTBALL_DATA_TOKEN не задан (см. .env.example)")

    previous = last_success_params(SOURCE).get("watermarks", {})
    watermarks = dict(previous)
    with ingest_run(SOURCE, {"seasons": settings.FOOTBALL_DATA_SEASONS}) as (run_id, stats):
        with SessionLocal.begin() as session:
            seed_teams(session)
            registry = TeamRegistry(session)
            rows = []
            for season in settings.FOOTBALL_DATA_SEASONS:
                matches = fetch_season(season)
                stats.fetched += len(matches)
                mark = previous.get(str(season))
                mark = datetime.fromisoformat(mark) if mark else None
                for match in matches:
                    updated_at = datetime.fromisoformat(match["lastUpdated"])
                    newest = watermarks.get(str(season))
                    if not newest or updated_at > datetime.fromisoformat(newest):
                        watermarks[str(season)] = updated_at.isoformat()
                    if mark and updated_at <= mark:
                        stats.skipped += 1
                        continue
                    row = to_row(match, registry)
                    if row is None:
                        stats.rejected += 1
                    else:
                        rows.append(row)

            comparison = compare_with_history(session, rows)
            inserted, updated, unchanged = upsert_matches(session, rows)
            stats.inserted, stats.updated, stats.skipped = inserted, updated, stats.skipped + unchanged

        stats.watermark = max(datetime.fromisoformat(w) for w in watermarks.values())
        stats.params.update(watermarks=watermarks)
        with SessionLocal.begin() as session:
            for name, details in comparison.items():
                quality.record(session, run_id, "matches", f"csv_{name}_agrees_with_api", "warn",
                               details["mismatched"] == 0, details)
            quality.flag_attendance(session, run_id)
            quality.check_matches(session, run_id)
        log.info("football_data: получено %d, вставлено %d, обновлено %d, без изменений %d, отклонено %d",
                 stats.fetched, stats.inserted, stats.updated, stats.skipped, stats.rejected)
