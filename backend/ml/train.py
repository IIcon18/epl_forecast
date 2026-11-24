import argparse
import logging
from dataclasses import dataclass

import joblib
import pandas as pd
from sqlalchemy import update

from db.models import ModelVersion
from db.session import SessionLocal, engine
from ml import registry
from ml.dataset import (
    FIRST_FORECAST_SEASON,
    TEST_SEASON,
    data_hash,
    load_dataset,
    selected_features,
    trainable,
)
from ml.estimators import DEFAULT_PARAMS, MODEL_NAMES, SEED
from ml.features import FEATURE_VERSION
from ml.validation import (
    cv_summary,
    fit_model,
    holdout,
    metrics,
    predict_with,
    walk_forward,
)

log = logging.getLogger(__name__)
MODELS_DIR = registry.MODELS_DIR


EXTRA_CONFIGURATIONS = {
    "ridge": [{"alpha": 30.0}, {"alpha": 1000.0}],
    "hgb": [{"max_depth": 1}, {"max_depth": 3}, {"min_samples_leaf": 80}],
}


@dataclass
class Trial:
    model_name: str
    params: dict
    predictions: pd.DataFrame
    scores: dict

    @property
    def mae(self) -> float:
        return self.scores["mae"]


def print_table(title: str, results: dict[str, dict]) -> None:
    log.info("%s", title)
    log.info("%-7s %6s %6s %6s %7s %14s %10s", "модель", "MAE", "MedAE", "RMSE", "MAPE,%", "ошибка,% вмест", "в 5%,%")
    for name, m in results.items():
        log.info("%-7s %6.0f %6.0f %6.0f %7.2f %14.2f %10.1f", name, m["mae"], m["medae"], m["rmse"],
                 m["mape"], m["mae_pct_capacity"], m["within_5pct_capacity"])


def run(*, tune: bool = False) -> None:
    with engine.connect() as conn:
        df = load_dataset(conn)
    data = trainable(df)
    features = selected_features(data)
    dataset_hash = data_hash(data, features)
    log.info("обучаемых матчей %d, признаков %d, хеш данных %s", len(data), len(features), dataset_hash[:12])

    trials: list[Trial] = []
    best_by_model: dict[str, Trial] = {}
    for name in MODEL_NAMES:
        configurations = [{}]
        if tune:
            configurations.extend(EXTRA_CONFIGURATIONS.get(name, []))
        model_trials = []
        for overrides in configurations:
            params = {**DEFAULT_PARAMS.get(name, {}), **overrides}
            predictions = walk_forward(data, name, features, params)
            trial = Trial(name, params, predictions, cv_summary(predictions))
            model_trials.append(trial)
            log.info("CV %s %s: MAE %.2f", name, params, trial.mae)
        trials.extend(model_trials)
        best_by_model[name] = min(model_trials, key=lambda trial: trial.mae)

    winner = min(
        (trial for name, trial in best_by_model.items() if name != "naive"),
        key=lambda trial: trial.mae,
    )
    log.info("лучшая ML-модель на скользящей проверке: %s %s", winner.model_name, winner.params)

    test_frames = {
        name: holdout(data, name, features, trial.params)
        for name, trial in best_by_model.items()
    }
    test_metrics = {name: metrics(frame) for name, frame in test_frames.items()}
    print_table(
        "Скользящая проверка 2010–2018 (среднее по сезонам)",
        {name: trial.scores for name, trial in best_by_model.items()},
    )
    print_table(f"Тест {TEST_SEASON}/{TEST_SEASON % 100 + 1}", test_metrics)

    best = winner.model_name
    final_metrics = {
        "cv": winner.scores,
        "test": test_metrics[best],
        "naive_test": test_metrics["naive"],
    }
    final_train = data[data["season"] <= TEST_SEASON]
    final_model = fit_model(final_train, best, features, winner.params)
    train_seasons = sorted(int(s) for s in final_train["season"].unique())
    forecast = df[(df["season"] >= FIRST_FORECAST_SEASON) & df["baseline"].notna()].copy()
    forecast["pred"] = predict_with(final_model, forecast, features)

    with SessionLocal.begin() as session:
        for trial in trials:
            registry.log_experiment(
                session, kind="cv", model_name=trial.model_name, params=trial.params,
                features=features, metrics=trial.scores, data_hash=dataset_hash,
            )
        for name in MODEL_NAMES:
            registry.log_experiment(session, kind="test", model_name=name, params=best_by_model[name].params, features=features,
                                    metrics=test_metrics[name], data_hash=dataset_hash)
        experiment_id = registry.log_experiment(
            session, kind="final", model_name=best, params=winner.params, features=features,
            metrics=final_metrics,
            data_hash=dataset_hash, note=f"обучение на сезонах {train_seasons}")
        session.execute(update(ModelVersion).where(ModelVersion.status == "production")
                        .values(status="archived"))
        version = ModelVersion(
            experiment_id=experiment_id, model_name=best, train_seasons=train_seasons, status="production",
            artifact_path="", metrics=registry.clean(final_metrics))
        session.add(version)
        session.flush()

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        artifact = MODELS_DIR / f"{best}_v{version.id}.joblib"
        joblib.dump({"model": final_model, "features": features, "feature_version": FEATURE_VERSION,
                     "name": best, "seed": SEED, "train_seasons": train_seasons}, artifact)
        version.artifact_path = artifact.name

        rows = (registry.prediction_rows(winner.predictions, version.id, "backtest")
                + registry.prediction_rows(test_frames[best], version.id, "backtest")
                + registry.prediction_rows(forecast, version.id, "forecast"))
        registry.save_predictions(session, rows)
        log.info("версия модели %d (%s) в эксплуатации, прогнозов записано %d, из них на будущие матчи %d",
                 version.id, best, len(rows), int((forecast["status"].isin(["TIMED", "SCHEDULED"])).sum()))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Обучение и сравнение моделей посещаемости")
    parser.add_argument("--tune", action="store_true", help="проверить дополнительные гиперпараметры Ridge и HGB")
    run(tune=parser.parse_args().tune)
