from datetime import date, datetime

from pydantic import BaseModel


class Health(BaseModel):
    status: str


class ModelInfo(BaseModel):
    id: int
    model_name: str
    status: str
    trained_at: datetime
    train_seasons: list[int]
    metrics: dict


class SeasonInfo(BaseModel):
    season: int
    matches: int
    ok: int
    suspect: int
    fanless: int
    missing: int


class TeamInfo(BaseModel):
    id: int
    name: str


class MatchRow(BaseModel):
    id: int
    match_date: date
    season: int
    status: str
    home_team: str
    away_team: str
    stadium: str | None
    attendance: int | None
    attendance_status: str | None
    predicted: int | None
    naive: int | None
    prediction_kind: str | None


class MatchesPage(BaseModel):
    total: int
    items: list[MatchRow]


class QualityRow(BaseModel):
    season: int | None
    matches: int
    mae_model: float
    mae_naive: float
    gain_pct: float
