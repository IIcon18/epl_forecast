import logging
import warnings

import joblib
from sqlalchemy import select

from db.models import ModelVersion
from db.session import SessionLocal, engine
from ml import registry
from ml.dataset import FIRST_FORECAST_SEASON, load_dataset
from ml.validation import predict_with

log = logging.getLogger(__name__)


def run() -> None:
    warnings.filterwarnings("ignore")
    with SessionLocal() as session:
        version = session.scalar(select(ModelVersion).where(ModelVersion.status == "production")
                                 .order_by(ModelVersion.id.desc()).limit(1))
    if version is None:
        raise RuntimeError("рабочая модель не обучена: сначала python -m ml.train")
    artifact = joblib.load(registry.MODELS_DIR / version.artifact_path)

    with engine.connect() as conn:
        df = load_dataset(conn)
    forecast = df[(df["season"] >= FIRST_FORECAST_SEASON) & df["baseline"].notna()].copy()
    forecast["pred"] = predict_with(artifact["model"], forecast, artifact["features"])

    with SessionLocal.begin() as session:
        registry.save_predictions(session, registry.prediction_rows(forecast, version.id, "forecast"))
    upcoming = int(forecast["status"].isin(["TIMED", "SCHEDULED"]).sum())
    log.info("прогноз моделью %s v%d: матчей %d, из них предстоящих %d", version.model_name, version.id,
             len(forecast), upcoming)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
