from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.data import router as data_router
from api.deps import get_session
from api.schemas import Health, ModelInfo
from db.models import ModelVersion

app = FastAPI(title="Прогноз посещаемости матчей АПЛ")
app.include_router(data_router)


@app.get("/health", response_model=Health)
def health(session: Session = Depends(get_session)) -> Health:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="база данных недоступна")
    return Health(status="ok")


@app.get("/api/model", response_model=ModelInfo)
def current_model(session: Session = Depends(get_session)) -> ModelVersion:
    version = session.scalar(
        select(ModelVersion).where(ModelVersion.status == "production")
        .order_by(ModelVersion.id.desc()).limit(1)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="рабочая модель ещё не обучена")
    return version
