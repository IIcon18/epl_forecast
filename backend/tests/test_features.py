from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from ml.features import FEATURE_COLUMNS, build_features

TEAMS = [1, 2, 3, 4, 5, 6]
OUTCOME_COLUMNS = ["home_goals", "away_goals", "attendance"]


def round_robin(teams):
    rounds, rotating = [], list(teams)
    for _ in range(len(teams) - 1):
        rounds.append([(rotating[i], rotating[-1 - i]) for i in range(len(teams) // 2)])
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    return rounds


def make_matches(seasons=(2000, 2001, 2002), unplayed=6):
    rng = np.random.default_rng(0)
    rows, match_id = [], 1
    for season in seasons:
        first_half = round_robin(TEAMS)
        second_half = [[(away, home) for home, away in rnd] for rnd in first_half]
        for k, rnd in enumerate(first_half + second_half):
            day = date(season, 8, 10) + timedelta(days=7 * k)
            for home, away in rnd:
                rows.append({
                    "match_id": match_id, "season": season, "match_date": day,
                    "home_team_id": home, "away_team_id": away, "status": "FINISHED",
                    "home_goals": int(rng.integers(0, 4)), "away_goals": int(rng.integers(0, 4)),
                    "attendance": int(20000 + 5000 * home + rng.integers(-2000, 2000)),
                    "attendance_status": "ok" if rng.random() > 0.2 else "suspect",
                    "stadium": f"Stadium {home}", "is_derby": None,
                })
                match_id += 1
    frame = pd.DataFrame(rows)
    return hide_outcomes(frame, frame.index >= len(frame) - unplayed)


def hide_outcomes(frame, mask):
    frame = frame.copy()
    frame.loc[mask, OUTCOME_COLUMNS] = np.nan
    frame.loc[mask, "status"] = "TIMED"
    frame.loc[mask, "attendance_status"] = "missing"
    return frame


def features_of(frame, match_id):
    return frame.set_index("match_id").loc[match_id, FEATURE_COLUMNS].astype(float)


MATCH_IDS = [1, 7, 20, 31, 45, 60, 75, 85, 90]
MODES = ["match", "season"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("match_id", MATCH_IDS)
def test_features_do_not_depend_on_the_future(match_id, mode):
    matches = make_matches()
    day = matches.loc[matches["match_id"] == match_id, "match_date"].iloc[0]
    known = matches[matches["match_date"] <= day]
    known = hide_outcomes(known, known["match_date"] == day)
    pd.testing.assert_series_equal(
        features_of(build_features(matches, history_delay=mode), match_id),
        features_of(build_features(known, history_delay=mode), match_id),
        check_names=False,
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("match_id", MATCH_IDS)
def test_features_do_not_depend_on_own_outcome(match_id, mode):
    matches = make_matches()
    changed = matches.copy()
    changed.loc[changed["match_id"] == match_id, OUTCOME_COLUMNS] = [9, 0, 99999]
    pd.testing.assert_series_equal(
        features_of(build_features(matches, history_delay=mode), match_id),
        features_of(build_features(changed, history_delay=mode), match_id),
        check_names=False,
    )


@pytest.mark.parametrize("mode", MODES)
def test_suspect_attendance_never_enters_features(mode):
    matches = make_matches()
    matches.loc[matches["attendance_status"] == "suspect", "attendance"] = 10**9
    frame = build_features(matches, history_delay=mode)
    attendance_features = [c for c in FEATURE_COLUMNS if c.startswith("att_")]
    assert frame[attendance_features].max().max() < 10**8


def test_season_mode_freezes_attendance_history_within_a_season():
    matches = make_matches()
    frame = build_features(matches, history_delay="season")
    in_second_season = frame[frame["season"] == 2001]
    assert (in_second_season.groupby("home_team_id")["att_last1"].nunique() == 1).all()
    assert (in_second_season.groupby("home_team_id")["att_hist_n"].nunique() == 1).all()


def test_match_mode_updates_history_during_a_season():
    matches = make_matches()
    frame = build_features(matches, history_delay="match")
    in_second_season = frame[frame["season"] == 2001]
    assert (in_second_season.groupby("home_team_id")["att_hist_n"].nunique() > 1).all()


def test_news_of_match_day_and_later_is_ignored():
    matches = make_matches()
    row = matches[matches["match_id"] == 40].iloc[0]
    day = datetime.combine(row["match_date"], datetime.min.time(), tzinfo=timezone.utc)
    news = pd.DataFrame({
        "team_id": [row["home_team_id"]] * 3,
        "published_at": [day - timedelta(days=2), day + timedelta(hours=12), day + timedelta(days=1)],
        "compound": [0.5, -0.9, -0.9],
    })
    features = features_of(build_features(matches, news), 40)
    assert features["h_news_count"] == 1
    assert features["h_news_sent"] == 0.5


def test_build_is_deterministic():
    matches = make_matches()
    pd.testing.assert_frame_equal(build_features(matches), build_features(matches))


def test_features_exclude_outcome_columns():
    assert set(FEATURE_COLUMNS).isdisjoint({"attendance", "home_goals", "away_goals", "status"})
    assert set(FEATURE_COLUMNS) <= set(build_features(make_matches()).columns)
