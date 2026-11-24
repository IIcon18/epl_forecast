from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from db.models import IngestRun
from db.session import SessionLocal


@dataclass
class RunStats:
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    watermark: datetime | None = None
    params: dict = field(default_factory=dict)


@contextmanager
def ingest_run(source: str, params: dict | None = None):
    with SessionLocal.begin() as session:
        run = IngestRun(source=source, params=params or {})
        session.add(run)
        session.flush()
        run_id = run.id
    stats = RunStats(params=dict(params or {}))
    try:
        yield run_id, stats
    except Exception as exc:
        _finish(run_id, stats, "failed", f"{type(exc).__name__}: {exc}"[:2000])
        raise
    _finish(run_id, stats, "partial" if stats.rejected else "success", None)


def _finish(run_id: int, stats: RunStats, status: str, error: str | None) -> None:
    with SessionLocal.begin() as session:
        run = session.get(IngestRun, run_id)
        run.finished_at = datetime.now(timezone.utc)
        run.status = status
        run.error = error
        run.rows_fetched = stats.fetched
        run.rows_inserted = stats.inserted
        run.rows_updated = stats.updated
        run.rows_skipped = stats.skipped
        run.rows_rejected = stats.rejected
        run.watermark = stats.watermark
        run.params = stats.params


def last_success_params(source: str) -> dict:
    with SessionLocal() as session:
        params = session.scalar(
            select(IngestRun.params)
            .where(IngestRun.source == source, IngestRun.status.in_(["success", "partial"]))
            .order_by(IngestRun.started_at.desc())
            .limit(1)
        )
    return params or {}
