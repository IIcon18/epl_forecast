import logging
from datetime import datetime, timezone

import feedparser
from sqlalchemy.dialects.postgresql import insert

from db.models import NewsArticle, NewsArticleTeam
from db.session import SessionLocal
from pipeline import quality, settings
from pipeline.http import SourceUnavailable, get
from pipeline.journal import ingest_run
from pipeline.teams import find_mentions, mention_patterns, seed_teams

log = logging.getLogger(__name__)
SOURCE = "bbc_rss"


def parse_entries(content: bytes) -> list[dict]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise SourceUnavailable("лента не читается как RSS")
    entries = []
    for e in feed.entries:
        published = e.get("published_parsed")
        guid = (e.get("id") or e.get("link") or "").split("#")[0]
        if not published or not guid or not e.get("title"):
            entries.append(None)
            continue
        entries.append({
            "source": SOURCE,
            "guid": guid,
            "title": e["title"].strip(),
            "summary": (e.get("summary") or "").strip() or None,
            "url": e.get("link") or guid,
            "published_at": datetime(*published[:6], tzinfo=timezone.utc),
        })
    return entries


def run() -> None:
    with ingest_run(SOURCE, {"url": settings.RSS_URL}) as (run_id, stats):
        entries = parse_entries(get(settings.RSS_URL).content)
        stats.fetched = len(entries)
        valid = [e for e in entries if e]
        stats.rejected = len(entries) - len(valid)
        rows = list({e["guid"]: e for e in reversed(valid)}.values())

        with SessionLocal.begin() as session:
            seed_teams(session)
            patterns = mention_patterns(session, settings.current_season() - 1)
            inserted = session.execute(
                insert(NewsArticle).values(rows)
                .on_conflict_do_nothing(constraint="uq_news_source_guid")
                .returning(NewsArticle.id, NewsArticle.guid)
            ).all() if rows else []
            by_guid = {r["guid"]: r for r in rows}
            links = [
                {"article_id": article_id, "team_id": team_id}
                for article_id, guid in inserted
                for team_id in find_mentions(
                    f"{by_guid[guid]['title']}. {by_guid[guid]['summary'] or ''}", patterns)
            ]
            if links:
                session.execute(
                    insert(NewsArticleTeam).values(links).on_conflict_do_nothing()
                )
            stats.inserted = len(inserted)
            stats.skipped = stats.fetched - stats.rejected - len(inserted)

        if rows:
            stats.watermark = max(r["published_at"] for r in rows)
        with SessionLocal.begin() as session:
            quality.check_news(session, run_id)
        log.info("bbc_rss: получено %d, новых %d, уже были %d, отклонено %d, связей с клубами %d",
                 stats.fetched, stats.inserted, stats.skipped, stats.rejected, len(links))
