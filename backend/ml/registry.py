import json

from sqlalchemy.orm import Session

from db.models import Experiment
from ml.estimators import SEED
from ml.features import FEATURE_VERSION


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
