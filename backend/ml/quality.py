import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS

POINTS_PER_GAME = ["h_ppg5", "a_ppg5", "h_season_ppg", "a_season_ppg", "h_prev_ppg", "a_prev_ppg"]
MAX_MISSING_HISTORY = 0.2
MIN_FORECAST_READY = 0.9


def out_of_range(frame: pd.DataFrame, column: str, low: float, high: float) -> int:
    values = frame[column].dropna()
    return int(((values < low) | (values > high)).sum())


def check_features(frame: pd.DataFrame, matches_count: int) -> list[dict]:
    checks = []

    def add(name: str, severity: str, passed: bool, **details):
        checks.append({"name": name, "severity": severity, "passed": bool(passed), "details": details})

    duplicates = int(frame["match_id"].duplicated().sum())
    add("features_one_row_per_match", "error", len(frame) == matches_count and duplicates == 0,
        rows=len(frame), matches=matches_count, duplicates=duplicates)

    numeric = frame[FEATURE_COLUMNS].astype(float)
    infinite = int(np.isinf(numeric.to_numpy()).sum())
    add("features_have_no_infinite_values", "error", infinite == 0, violations=infinite)

    calendar = {"weekday": (0, 6), "month": (1, 12), "is_weekend": (0, 1), "is_holiday_period": (0, 1)}
    bad_calendar = {c: out_of_range(frame, c, *bounds) for c, bounds in calendar.items()}
    add("calendar_features_in_range", "error", not any(bad_calendar.values()), violations=bad_calendar)

    bad_positions = {c: out_of_range(frame, c, 1, 20) for c in ("h_pos", "a_pos")}
    add("table_position_in_1_20", "error", not any(bad_positions.values()), violations=bad_positions)

    bad_points = {c: out_of_range(frame, c, 0, 3) for c in POINTS_PER_GAME}
    add("points_per_game_in_0_3", "error", not any(bad_points.values()), violations=bad_points)

    trusted = frame[(frame["attendance_status"] == "ok") & (frame["season"] > frame["season"].min())]
    share = trusted.groupby("season")["att_mean10"].apply(lambda s: float(s.isna().mean()))
    worst = float(share.max()) if len(share) else 0.0
    add("trusted_matches_have_attendance_history", "warn", worst <= MAX_MISSING_HISTORY,
        worst_season=int(share.idxmax()) if len(share) else None, worst_share=round(worst, 4),
        limit=MAX_MISSING_HISTORY, note="без истории остаются матчи новичков лиги")

    upcoming = frame[frame["status"].isin(["TIMED", "SCHEDULED"])]
    ready = float(upcoming["att_mean10"].notna().mean()) if len(upcoming) else 1.0
    add("upcoming_matches_ready_for_forecast", "warn", ready >= MIN_FORECAST_READY,
        ready_share=round(ready, 4), upcoming=len(upcoming))
    return checks
