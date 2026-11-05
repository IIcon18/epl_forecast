import json
import logging
import warnings

import pandas as pd

from db.session import engine
from ml.dataset import (
    FEATURE_GROUPS,
    SELECTED_PATH,
    constant_features,
    load_dataset,
    trainable,
)
from ml.validation import cv_summary, walk_forward

log = logging.getLogger(__name__)
TOLERANCE = 0.005
TEST_SEASONS = range(2012, 2019)


def cv_mae(data: pd.DataFrame, groups: dict[str, list[str]], active: list[str]) -> float:
    features = [f for g in active for f in groups[g]]
    return cv_summary(walk_forward(data, "hgb", features, test_seasons=TEST_SEASONS))["mae"]


def run() -> None:
    warnings.filterwarnings("ignore")
    with engine.connect() as conn:
        data = trainable(load_dataset(conn))
    all_columns = [c for cols in FEATURE_GROUPS.values() for c in cols]
    constant = set(constant_features(data, all_columns))
    groups = {g: [f for f in cols if f not in constant] for g, cols in FEATURE_GROUPS.items()}
    groups = {g: cols for g, cols in groups.items() if cols}

    active = list(groups)
    current = cv_mae(data, groups, active)
    report = {"constant_excluded": sorted(constant), "start_mae": current, "steps": []}
    log.info("все группы: CV MAE %.0f", current)
    while len(active) > 1:
        scores = {g: cv_mae(data, groups, [a for a in active if a != g]) for g in active}
        worst, score = min(scores.items(), key=lambda kv: kv[1])
        report["steps"].append({"scores_without_group": scores, "removed": None})
        if score > current * (1 + TOLERANCE):
            log.info("группу убирать нельзя: лучший вариант %s даёт %.0f (было %.0f)", worst, score, current)
            break
        report["steps"][-1]["removed"] = worst
        log.info("убираю группу %-20s CV MAE %.0f -> %.0f", worst, current, score)
        active.remove(worst)
        current = score

    selected = [f for g in active for f in groups[g]]
    report.update(groups=active, features=selected, final_mae=current)
    SELECTED_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    log.info("итоговые группы: %s; признаков %d; CV MAE %.0f", active, len(selected), current)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run()
