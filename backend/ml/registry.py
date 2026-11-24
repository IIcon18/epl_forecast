import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Experiment, Prediction
from ml.estimators import SEED
from ml.features import FEATURE_VERSION

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parents[2] / "models"))
CHUNK = 1000


def clean(value):
    return json.loads(json.dumps(value, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def log_experiment(session: Session, *, kind: str, model_name: str, params: dict, features: list[str],
                   metrics: dict, data_hash: str, note: str | None = None) -> int:
    experiment = Experiment(
        kind=kind, model_name=model_name, params=clean(params), features=clean(features),
        feature_version=FEATURE_VERSION, data_hash=data_hash, seed=SEED,
        metrics=clean(metrics), note=note,
    )
    session.add(experiment)
    session.flush()
    return experiment.id


def prediction_rows(frame: pd.DataFrame, version_id: int, kind: str) -> list[dict]:
    return [
        {"model_version_id": version_id, "match_id": int(r.match_id), "kind": kind,
         "predicted": int(round(r.pred)), "baseline": int(round(r.baseline))}
        for r in frame.itertuples()
    ]


def save_predictions(session: Session, rows: list[dict]) -> None:
    for start in range(0, len(rows), CHUNK):
        stmt = insert(Prediction).values(rows[start:start + CHUNK])
        session.execute(stmt.on_conflict_do_update(
            index_elements=["model_version_id", "match_id"],
            set_={"kind": stmt.excluded.kind, "predicted": stmt.excluded.predicted,
                  "baseline": stmt.excluded.baseline}))
