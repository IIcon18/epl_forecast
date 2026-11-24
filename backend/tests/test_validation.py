import numpy as np
import pandas as pd
import pytest

import ml.validation as validation
from ml.dataset import FEATURE_GROUPS
from ml.features import FEATURE_COLUMNS
from ml.validation import fit_model, metrics, predict_with, walk_forward


def make_data(seasons=range(2000, 2008), per_season=40):
    rng = np.random.default_rng(1)
    rows = []
    for season in seasons:
        for i in range(per_season):
            baseline = 30000 + 100 * i
            rows.append({"match_id": len(rows), "season": season, "baseline": baseline,
                         "attendance": baseline * rng.normal(1.0, 0.03), "att_cap_proxy": 40000,
                         "weekday": i % 7, "h_pos": 1 + i % 20})
    return pd.DataFrame(rows)


def test_walk_forward_trains_only_on_the_past(monkeypatch):
    seen = []
    original = validation.fit_predict

    def spy(train, test, *args, **kwargs):
        seen.append((train["season"].max(), test["season"].min(), test["season"].max()))
        return original(train, test, *args, **kwargs)

    monkeypatch.setattr(validation, "fit_predict", spy)
    walk_forward(make_data(), "ridge", ["weekday", "h_pos"], test_seasons=range(2003, 2008))
    assert len(seen) == 5
    assert all(last_train < first_test == last_test for last_train, first_test, last_test in seen)


def test_anomalous_matches_do_not_influence_training():
    data = make_data()
    data["attendance"] = data["baseline"]
    data.loc[0, "attendance"] = data.loc[0, "baseline"] * 3
    model = fit_model(data, "ridge", ["weekday", "h_pos"])
    ratio = predict_with(model, data, ["weekday", "h_pos"]) / data["baseline"]
    assert np.allclose(ratio, 1.0, atol=1e-6)


def test_metrics_on_a_known_example():
    frame = pd.DataFrame({"attendance": [100, 200, 400], "pred": [110, 180, 400],
                          "att_cap_proxy": [200, 200, 400]})
    result = metrics(frame)
    assert result["mae"] == pytest.approx(10.0)
    assert result["medae"] == pytest.approx(10.0)
    assert result["mape"] == pytest.approx((10 / 100 + 20 / 200 + 0) / 3 * 100)
    assert result["within_5pct_capacity"] == pytest.approx(200 / 3)


def test_feature_groups_cover_all_features_exactly_once():
    grouped = [c for columns in FEATURE_GROUPS.values() for c in columns]
    assert sorted(grouped) == sorted(FEATURE_COLUMNS)
