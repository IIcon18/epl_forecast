import argparse
import json
import math

from db.models import Experiment
from db.session import SessionLocal, engine
from ml.dataset import data_hash, load_dataset, trainable
from ml.estimators import SEED
from ml.features import FEATURE_VERSION
from ml.validation import cv_summary, holdout, metrics, walk_forward


def reproduce(experiment_id: int) -> dict:
    with SessionLocal() as session:
        experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ValueError(f"Эксперимент {experiment_id} не найден")
    if experiment.seed != SEED or experiment.feature_version != FEATURE_VERSION:
        raise ValueError("Версия признаков или случайное зерно отличаются от сохранённых")
    if experiment.kind not in {"cv", "test", "final"}:
        raise ValueError(f"Неизвестный тип эксперимента: {experiment.kind}")

    with engine.connect() as conn:
        data = trainable(load_dataset(conn))
    features = experiment.features
    if features is None or not set(features).issubset(data.columns):
        raise ValueError("Сохранённые признаки отсутствуют в текущей витрине")
    if data_hash(data, features) != experiment.data_hash:
        raise ValueError("Хеш данных отличается. Для повтора нужна исходная витрина признаков")

    name, params = experiment.model_name, experiment.params or {}
    actual = {}
    if experiment.kind in {"cv", "final"}:
        actual["cv"] = cv_summary(walk_forward(data, name, features, params))
    if experiment.kind in {"test", "final"}:
        actual["test"] = metrics(holdout(data, name, features, params))
    if experiment.kind == "final":
        actual["naive_test"] = metrics(holdout(data, "naive", features, {}))
        expected = experiment.metrics
    else:
        expected = {experiment.kind: experiment.metrics}

    differences = [
        f"{split}.{key}"
        for split, values in expected.items()
        for key, value in values.items()
        if key not in actual[split]
        or not math.isclose(value, actual[split][key], rel_tol=1e-9, abs_tol=1e-9)
    ]
    return {
        "id": experiment.id, "model": name, "kind": experiment.kind,
        "params": params, "seed": experiment.seed, "data_hash": experiment.data_hash,
        "saved": expected, "recomputed": actual, "differences": differences,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Повтор эксперимента из журнала")
    parser.add_argument("--id", required=True, type=int, help="номер эксперимента в Grafana")
    args = parser.parse_args()
    try:
        result = reproduce(args.id)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["differences"]:
        parser.exit(1, "Пересчитанные метрики отличаются от сохранённых\n")


if __name__ == "__main__":
    main()
