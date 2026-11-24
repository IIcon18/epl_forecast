from sqlalchemy import func, literal_column, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Match

MERGE_COLUMNS = [
    "match_date", "kickoff_utc", "matchday", "status", "home_goals", "away_goals",
    "attendance", "stadium", "referee", "is_derby", "football_data_id",
]
CHUNK = 500


def upsert_matches(session: Session, rows: list[dict],
                   prefer_existing: frozenset[str] = frozenset()) -> tuple[int, int, int]:
    """Возвращает (вставлено, обновлено, без изменений); NULL не затирает сохранённое значение."""
    table = Match.__table__
    inserted = updated = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        stmt = insert(Match).values(chunk)
        merged = {
            c: func.coalesce(table.c[c], stmt.excluded[c]) if c in prefer_existing
            else func.coalesce(stmt.excluded[c], table.c[c])
            for c in MERGE_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["season", "home_team_id", "away_team_id"],
            set_={**merged, "updated_at": func.now()},
            where=or_(*[table.c[c].is_distinct_from(merged[c]) for c in MERGE_COLUMNS]),
        ).returning(literal_column("(xmax = 0)"))
        for (is_insert,) in session.execute(stmt):
            if is_insert:
                inserted += 1
            else:
                updated += 1
    return inserted, updated, len(rows) - inserted - updated
