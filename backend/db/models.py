from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    football_data_id: Mapped[int | None] = mapped_column(Integer, unique=True)


class TeamAlias(Base):
    """Разные источники называют клуб по-разному ('Man City', 'Manchester City FC')."""

    __tablename__ = "team_aliases"

    alias: Mapped[str] = mapped_column(String(100), primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "season", "home_team_id", "away_team_id", name="uq_matches_season_home_away"
        ),
        CheckConstraint("home_team_id <> away_team_id", name="ck_matches_distinct_teams"),
        CheckConstraint(
            "attendance IS NULL OR attendance >= 0", name="ck_matches_attendance_nonneg"
        ),
        Index("ix_matches_match_date", "match_date"),
        Index("ix_matches_home_team_date", "home_team_id", "match_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(SmallInteger)  # год начала сезона: 2023 = 2023/24
    match_date: Mapped[date] = mapped_column(Date)
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matchday: Mapped[int | None] = mapped_column(SmallInteger)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(16), server_default="FINISHED")
    home_goals: Mapped[int | None] = mapped_column(SmallInteger)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger)
    attendance: Mapped[int | None] = mapped_column(Integer)
    attendance_status: Mapped[str | None] = mapped_column(String(10))
    stadium: Mapped[str | None] = mapped_column(String(100))
    referee: Mapped[str | None] = mapped_column(String(100))
    is_derby: Mapped[bool | None] = mapped_column(Boolean)
    football_data_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("source", "guid", name="uq_news_source_guid"),
        Index("ix_news_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    guid: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NewsArticleTeam(Base):
    __tablename__ = "news_article_teams"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class MatchFeatures(Base):
    __tablename__ = "match_features"

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    feature_version: Mapped[str] = mapped_column(String(16))
    features: Mapped[dict] = mapped_column(JSONB)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = (Index("ix_ingest_runs_source_started", "source", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    rows_fetched: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_inserted: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_updated: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_skipped: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_rejected: Mapped[int] = mapped_column(Integer, server_default="0")
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSONB)


class DqCheck(Base):
    __tablename__ = "dq_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingest_runs.id", ondelete="SET NULL"), index=True
    )
    table_name: Mapped[str] = mapped_column(String(64))
    check_name: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(8))
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict | None] = mapped_column(JSONB)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
