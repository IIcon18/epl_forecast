from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
RATIO_CLIP = (0.3, 1.6)
TRAIN_RATIO_RANGE = (0.75, 1.3)
MODEL_NAMES = ["naive", "ridge", "hgb", "rf"]
DEFAULT_PARAMS = {
    "ridge": {"alpha": 300.0},
    "hgb": {"loss": "absolute_error", "learning_rate": 0.03, "max_iter": 200, "max_depth": 2,
            "min_samples_leaf": 40},
    "rf": {"n_estimators": 300, "min_samples_leaf": 20, "max_features": 0.33, "n_jobs": -1},
}


def make_model(name: str, numeric: list[str], categorical: list[str],
               params: dict | None = None) -> Pipeline:
    params = {**DEFAULT_PARAMS[name], **(params or {})}
    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical))
    estimator = {
        "ridge": lambda: Ridge(**params),
        "hgb": lambda: HistGradientBoostingRegressor(random_state=SEED, **params),
        "rf": lambda: RandomForestRegressor(random_state=SEED, **params),
    }[name]()
    return Pipeline([("prep", ColumnTransformer(transformers)), ("model", estimator)])
