import logging
import os
import warnings
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from db.models import ModelVersion, Prediction
from db.session import SessionLocal, engine
from ml import registry
from ml.dataset import (
    LAST_TRAIN_SEASON,
    TEST_SEASON,
    data_hash,
    load_dataset,
    selected_features,
    trainable,
)
from ml.estimators import DEFAULT_PARAMS, MODEL_NAMES, SEED
from ml.features import FEATURE_VERSION
from ml.validation import (
    KEEP,
    cv_summary,
    fit_model,
    metrics,
    predict_with,
    walk_forward,
)

log = logging.getLogger(__name__)
MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parents[2] / "models"))
FIRST_FORECAST_SEASON = TEST_SEASON + 1
CHUNK = 1000


def print_table(title: str, results: dict[str, dict]) -> None:
    log.info("%s", title)
    log.info("%-7s %6s %6s %6s %7s %14s %10s", "модель", "MAE", "MedAE", "RMSE", "MAPE,%", "ошибка,% вмест", "в 5%,%")
    for name, m in results.items():
        log.info("%-7s %6.0f %6.0f %6.0f %7.2f %14.2f %10.1f", name, m["mae"], m["medae"], m["rmse"],
                 m["mape"], m["mae_pct_capacity"], m["within_5pct_capacity"])


def prediction_rows(frame: pd.DataFrame, version_id: int, kind: str) -> list[dict]:
    return [
        {"model_version_id": version_id, "match_id": int(r.match_id), "kind": kind,
         "predicted": int(round(r.pred)), "baseline": int(round(r.baseline))}
        for r in frame.itertuples()
    ]


def run() -> None:
    warnings.filterwarnings("ignore")
    with engine.connect() as conn:
        df = load_dataset(conn)
    data = trainable(df)
    features = selected_features(data)
    dhash = data_hash(data, features)
    log.info("обучаемых матчей %d, признаков %d, хеш данных %s", len(data), len(features), dhash[:12])

    cv_frames = {name: walk_forward(data, name, features) for name in MODEL_NAMES}
    cv_metrics = {name: cv_summary(frame) for name, frame in cv_frames.items()}
    train = data[data["season"] <= LAST_TRAIN_SEASON]
    test = data[data["season"] == TEST_SEASON]
    models = {name: (None if name == "naive" else fit_model(train, name, features)) for name in MODEL_NAMES}
    test_frames = {
        name: test[KEEP].assign(pred=test["baseline"].to_numpy() if model is None
                                else predict_with(model, test, features))
        for name, model in models.items()
    }
    test_metrics = {name: metrics(frame) for name, frame in test_frames.items()}
    print_table("Скользящая проверка 2010–2018 (среднее по сезонам)", cv_metrics)
    print_table(f"Тест {TEST_SEASON}/{TEST_SEASON % 100 + 1} (история четырёхлетней давности)", test_metrics)

    best = min((n for n in MODEL_NAMES if n != "naive"), key=lambda n: cv_metrics[n]["mae"])
    log.info("лучшая модель по скользящей проверке: %s", best)

    final_train = data[data["season"] <= TEST_SEASON]
    final_model = fit_model(final_train, best, features)
    train_seasons = sorted(int(s) for s in final_train["season"].unique())
    forecast = df[(df["season"] >= FIRST_FORECAST_SEASON) & df["baseline"].notna()].copy()
    forecast["pred"] = predict_with(final_model, forecast, features)

    with SessionLocal.begin() as session:
        for name in MODEL_NAMES:
            params = DEFAULT_PARAMS.get(name, {})
            registry.log_experiment(session, kind="cv", model_name=name, params=params, features=features,
                                    metrics=cv_metrics[name], data_hash=dhash)
            registry.log_experiment(session, kind="test", model_name=name, params=params, features=features,
                                    metrics=test_metrics[name], data_hash=dhash)
        experiment_id = registry.log_experiment(
            session, kind="final", model_name=best, params=DEFAULT_PARAMS[best], features=features,
            metrics={"cv": cv_metrics[best], "test": test_metrics[best], "naive_test": test_metrics["naive"]},
            data_hash=dhash, note=f"обучение на сезонах {train_seasons}")
        session.execute(update(ModelVersion).where(ModelVersion.status == "production")
                        .values(status="archived"))
        version = ModelVersion(
            experiment_id=experiment_id, model_name=best, train_seasons=train_seasons, status="production",
            artifact_path="", metrics=registry.clean({"cv": cv_metrics[best], "test": test_metrics[best],
                                                      "naive_test": test_metrics["naive"]}))
        session.add(version)
        session.flush()

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        artifact = MODELS_DIR / f"{best}_v{version.id}.joblib"
        joblib.dump({"model": final_model, "features": features, "feature_version": FEATURE_VERSION,
                     "name": best, "seed": SEED, "train_seasons": train_seasons}, artifact)
        version.artifact_path = artifact.name

        rows = (prediction_rows(cv_frames[best], version.id, "backtest")
                + prediction_rows(test_frames[best], version.id, "backtest")
                + prediction_rows(forecast, version.id, "forecast"))
        for start in range(0, len(rows), CHUNK):
            stmt = insert(Prediction).values(rows[start:start + CHUNK])
            session.execute(stmt.on_conflict_do_update(
                index_elements=["model_version_id", "match_id"],
                set_={"kind": stmt.excluded.kind, "predicted": stmt.excluded.predicted,
                      "baseline": stmt.excluded.baseline}))
        log.info("версия модели %d (%s) в эксплуатации, прогнозов записано %d, из них на будущие матчи %d",
                 version.id, best, len(rows), int((forecast["status"].isin(["TIMED", "SCHEDULED"])).sum()))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
