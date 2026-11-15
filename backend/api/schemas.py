from datetime import datetime

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
