import numpy as np
import pandas as pd

from ml.dataset import split_columns
from ml.estimators import RATIO_CLIP, TRAIN_RATIO_RANGE, make_model

KEEP = ["match_id", "season", "attendance", "baseline", "att_cap_proxy"]


def fit_model(train: pd.DataFrame, name: str, features: list[str], params: dict | None = None):
    """Модель предсказывает отношение посещаемости к наивному прогнозу; аномальные матчи из обучения исключаются."""
    numeric, categorical = split_columns(features)
    ratio = train["attendance"] / train["baseline"]
    typical = ratio.between(*TRAIN_RATIO_RANGE)
    model = make_model(name, numeric, categorical, params)
    return model.fit(train.loc[typical, features], ratio[typical])


def predict_with(model, frame: pd.DataFrame, features: list[str]):
    return frame["baseline"].to_numpy() * np.clip(model.predict(frame[features]), *RATIO_CLIP)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, name: str, features: list[str],
                params: dict | None = None):
    if name == "naive":
        return test["baseline"].to_numpy()
    return predict_with(fit_model(train, name, features, params), test, features)


def walk_forward(data: pd.DataFrame, name: str, features: list[str], params: dict | None = None,
                 test_seasons=range(2010, 2019)) -> pd.DataFrame:
    """Скользящая проверка: каждый сезон прогнозируется моделью, обученной только на прошлых."""
    parts = []
    for season in test_seasons:
        train, test = data[data["season"] < season], data[data["season"] == season]
        if train.empty or test.empty:
            continue
        parts.append(test[KEEP].assign(pred=fit_predict(train, test, name, features, params)))
    return pd.concat(parts, ignore_index=True)


def metrics(frame: pd.DataFrame) -> dict:
    error = (frame["pred"] - frame["attendance"]).abs()
    cap = frame["att_cap_proxy"]
    has_cap = cap > 0
    share = error[has_cap] / cap[has_cap]
    return {
        "mae": float(error.mean()),
        "rmse": float(np.sqrt(((frame["pred"] - frame["attendance"]) ** 2).mean())),
        "medae": float(error.median()),
        "mape": float((error / frame["attendance"]).mean() * 100),
        "mae_pct_capacity": float(share.mean() * 100),
        "within_5pct_capacity": float((share <= 0.05).mean() * 100),
        "n": int(len(frame)),
    }


def cv_summary(frame: pd.DataFrame) -> dict:
    per_season = [metrics(group) for _, group in frame.groupby("season")]
    keys = [k for k in per_season[0] if k != "n"]
    summary = {k: float(np.mean([m[k] for m in per_season])) for k in keys}
    summary["n"] = int(len(frame))
    summary["folds"] = len(per_season)
    return summary
