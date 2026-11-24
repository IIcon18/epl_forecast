from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from api.deps import get_session
from api.schemas import MatchesPage, MatchRow, QualityRow, SeasonInfo, TeamInfo
from db.models import Match, ModelVersion, Prediction, Team

router = APIRouter(prefix="/api")

UPCOMING = ("TIMED", "SCHEDULED")


def production_version_id(session: Session) -> int | None:
    return session.scalar(
        select(ModelVersion.id).where(ModelVersion.status == "production")
        .order_by(ModelVersion.id.desc()).limit(1)
    )


@router.get("/seasons", response_model=list[SeasonInfo])
def seasons(session: Session = Depends(get_session)):
    def count(status: str):
        return func.count(case((Match.attendance_status == status, 1)))

    rows = session.execute(
        select(Match.season, func.count().label("matches"), count("ok").label("ok"),
               count("suspect").label("suspect"), count("fanless").label("fanless"),
               count("missing").label("missing"))
        .group_by(Match.season).order_by(Match.season.desc())
    )
    return [SeasonInfo(**row._mapping) for row in rows]


@router.get("/teams", response_model=list[TeamInfo])
def teams(season: int | None = None, session: Session = Depends(get_session)):
    query = select(Team.id, Team.name).order_by(Team.name)
    if season is not None:
        in_season = select(Match.home_team_id).where(Match.season == season).union(
            select(Match.away_team_id).where(Match.season == season))
        query = query.where(Team.id.in_(in_season))
    else:
        query = query.where(Team.id.in_(select(Match.home_team_id).where(Match.season >= 2000)))
    return [TeamInfo(**row._mapping) for row in session.execute(query)]


@router.get("/matches", response_model=MatchesPage)
def matches(
    season: int | None = None,
    team_id: int | None = None,
    when: Literal["all", "played", "upcoming"] = "all",
    attendance_status: Literal["ok", "suspect", "fanless", "missing"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    home, away = aliased(Team), aliased(Team)
    version_id = production_version_id(session)
    join_prediction = and_(Prediction.match_id == Match.id, Prediction.model_version_id == version_id)

    filters = []
    if season is not None:
        filters.append(Match.season == season)
    if team_id is not None:
        filters.append(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if when == "upcoming":
        filters.append(Match.status.in_(UPCOMING))
    elif when == "played":
        filters.append(Match.status == "FINISHED")
    if attendance_status is not None:
        filters.append(Match.attendance_status == attendance_status)
    if date_from is not None:
        filters.append(Match.match_date >= date_from)
    if date_to is not None:
        filters.append(Match.match_date <= date_to)

    total = session.scalar(select(func.count()).select_from(Match).where(*filters))
    rows = session.execute(
        select(Match.id, Match.match_date, Match.season, Match.status,
               home.name.label("home_team"), away.name.label("away_team"), Match.stadium,
               Match.attendance, Match.attendance_status, Prediction.predicted,
               Prediction.baseline.label("naive"), Prediction.kind.label("prediction_kind"))
        .join(home, home.id == Match.home_team_id).join(away, away.id == Match.away_team_id)
        .outerjoin(Prediction, join_prediction).where(*filters)
        .order_by(Match.match_date, Match.id).limit(limit).offset(offset)
    )
    return MatchesPage(total=total, items=[MatchRow(**row._mapping) for row in rows])


@router.get("/quality", response_model=list[QualityRow])
def quality(session: Session = Depends(get_session)):
    """Ошибка рабочей модели и наивного прогноза на матчах с достоверной посещаемостью вне обучения."""
    version_id = production_version_id(session)
    model_error = func.abs(Prediction.predicted - Match.attendance)
    naive_error = func.abs(Prediction.baseline - Match.attendance)
    rows = session.execute(
        select(Match.season, func.count().label("matches"),
               func.avg(model_error).label("mae_model"), func.avg(naive_error).label("mae_naive"))
        .join(Prediction, Prediction.match_id == Match.id)
        .where(Prediction.model_version_id == version_id, Prediction.kind == "backtest",
               Match.attendance_status == "ok", Prediction.baseline.is_not(None))
        .group_by(Match.season).order_by(Match.season)
    ).all()

    def row(season, matches, mae_model, mae_naive):
        return QualityRow(season=season, matches=matches, mae_model=round(float(mae_model), 1),
                          mae_naive=round(float(mae_naive), 1),
                          gain_pct=round((1 - float(mae_model) / float(mae_naive)) * 100, 2))

    result = [row(*r) for r in rows]
    if rows:
        total = sum(r.matches for r in rows)
        weighted_model = sum(r.matches * float(r.mae_model) for r in rows) / total
        weighted_naive = sum(r.matches * float(r.mae_naive) for r in rows) / total
        result.append(row(None, total, weighted_model, weighted_naive))
    return result
