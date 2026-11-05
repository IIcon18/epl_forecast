from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

import numpy as np
import pandas as pd

FEATURE_VERSION = "v2"
FORM_WINDOW = 5
ATTENDANCE_WINDOW = 10
NEWS_WINDOW_DAYS = 7

FEATURE_COLUMNS = [
    "home_team_id", "weekday", "month", "is_weekend", "is_holiday_period", "days_into_season",
    "is_derby", "h_played", "a_played", "h_ppg5", "a_ppg5", "h_gd5", "a_gd5",
    "h_season_ppg", "a_season_ppg", "h_pos", "a_pos", "h_prev_ppg", "a_prev_ppg",
    "rest_days_h", "rest_days_a",
    "att_hist_n", "att_last1", "att_mean3", "att_mean10", "att_median_all", "att_cap_proxy",
    "att_days_since_hist", "away_pull",
    "h_news_count", "a_news_count", "h_news_sent", "a_news_sent",
]
META_COLUMNS = ["match_id", "season", "match_date", "status", "attendance", "attendance_status"]


@dataclass
class TeamState:
    results: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    points: int = 0
    played: int = 0
    gf: int = 0
    ga: int = 0
    prev_ppg: float | None = None
    last_date: date | None = None
    last_stadium: str | None = None
    away_ratios: deque = field(default_factory=lambda: deque(maxlen=ATTENDANCE_WINDOW))


def _nan_mean(values) -> float:
    values = list(values)
    return mean(values) if values else np.nan


def _news_index(news: pd.DataFrame | None) -> dict[int, tuple[list, list]]:
    if news is None or news.empty:
        return {}
    index = {}
    for team_id, group in news.sort_values("published_at").groupby("team_id"):
        times = [t.date() for t in pd.to_datetime(group["published_at"], utc=True)]
        index[int(team_id)] = (times, group["compound"].tolist())
    return index


def _news_window(index: dict, team_id: int, day: date) -> tuple[int, float]:
    times, scores = index.get(team_id, ([], []))
    lo = bisect_left(times, day - timedelta(days=NEWS_WINDOW_DAYS))
    hi = bisect_left(times, day)
    window = scores[lo:hi]
    return len(window), (mean(window) if window else np.nan)


def _table_positions(teams: dict[int, TeamState]) -> dict[int, int]:
    ranked = sorted(
        (t for t in teams if teams[t].played > 0),
        key=lambda t: (-teams[t].points, -(teams[t].gf - teams[t].ga), -teams[t].gf, t),
    )
    return {t: i + 1 for i, t in enumerate(ranked)}


def _team_features(prefix: str, state: TeamState, day: date, position: int | None) -> dict:
    return {
        f"{prefix}_played": state.played,
        f"{prefix}_ppg5": _nan_mean(p for p, _ in state.results),
        f"{prefix}_gd5": _nan_mean(gd for _, gd in state.results),
        f"{prefix}_season_ppg": state.points / state.played if state.played else np.nan,
        f"{prefix}_pos": position if position else np.nan,
        f"{prefix}_prev_ppg": state.prev_ppg if state.prev_ppg is not None else np.nan,
        f"rest_days_{prefix}": (day - state.last_date).days if state.last_date else np.nan,
    }


def build_features(matches: pd.DataFrame, news: pd.DataFrame | None = None,
                   history_delay: str = "season") -> pd.DataFrame:
    """Признаки матча считаются только по данным, известным до его начала.

    Матчи обрабатываются по датам: сначала признаки всех матчей дня, затем обновление состояния.
    history_delay: "match" добавляет посещаемость в историю сразу, "season" после конца сезона.
    """
    matches = matches.sort_values(["match_date", "match_id"]).reset_index(drop=True)
    season_start = matches.groupby("season")["match_date"].min().to_dict()
    news_index = _news_index(news)

    teams: dict[int, TeamState] = defaultdict(TeamState)
    stadium_history: dict[str, list[tuple[date, int]]] = defaultdict(list)
    derby_pairs: set[frozenset] = set()
    rows: dict[int, dict] = {}
    deferred: list[tuple] = []
    current_season = None

    def apply_attendance(update: tuple) -> None:
        stadium, day, attendance, away_id, ratio = update
        stadium_history[stadium].append((day, attendance))
        if ratio is not None:
            teams[away_id].away_ratios.append(ratio)

    for day, games in matches.groupby("match_date", sort=True):
        season = int(games["season"].iloc[0])
        if season != current_season:
            for update in deferred:
                apply_attendance(update)
            deferred.clear()
            for state in teams.values():
                state.prev_ppg = state.points / state.played if state.played else None
                state.points = state.played = state.gf = state.ga = 0
            current_season = season
        positions = _table_positions(teams)

        for g in games.itertuples():
            home, away = teams[g.home_team_id], teams[g.away_team_id]
            stadium = g.stadium if isinstance(g.stadium, str) else home.last_stadium
            history = stadium_history.get(stadium, []) if stadium else []
            values = [a for _, a in history]
            pair = frozenset((g.home_team_id, g.away_team_id))
            derby = g.is_derby if g.is_derby is not None and not pd.isna(g.is_derby) else None
            h_news, a_news = (_news_window(news_index, t, day) for t in (g.home_team_id, g.away_team_id))
            rows[g.match_id] = {
                "match_id": g.match_id,
                "home_team_id": g.home_team_id,
                "weekday": day.weekday(),
                "month": day.month,
                "is_weekend": int(day.weekday() >= 5),
                "is_holiday_period": int((day.month == 12 and day.day >= 20) or (day.month == 1 and day.day <= 3)),
                "days_into_season": (day - season_start[season]).days,
                "is_derby": float(derby) if derby is not None else float(pair in derby_pairs),
                **_team_features("h", home, day, positions.get(g.home_team_id)),
                **_team_features("a", away, day, positions.get(g.away_team_id)),
                "att_hist_n": len(values),
                "att_last1": values[-1] if values else np.nan,
                "att_mean3": _nan_mean(values[-3:]),
                "att_mean10": _nan_mean(values[-ATTENDANCE_WINDOW:]),
                "att_median_all": median(values) if values else np.nan,
                "att_cap_proxy": max(values) if values else np.nan,
                "att_days_since_hist": (day - history[-1][0]).days if history else np.nan,
                "away_pull": _nan_mean(away.away_ratios),
                "h_news_count": h_news[0], "a_news_count": a_news[0],
                "h_news_sent": h_news[1], "a_news_sent": a_news[1],
            }

        for g in games.itertuples():
            if g.is_derby is not None and not pd.isna(g.is_derby) and g.is_derby:
                derby_pairs.add(frozenset((g.home_team_id, g.away_team_id)))
            home, away = teams[g.home_team_id], teams[g.away_team_id]
            if isinstance(g.stadium, str):
                home.last_stadium = g.stadium
            if pd.isna(g.home_goals) or pd.isna(g.away_goals):
                continue
            for state, scored, conceded in ((home, g.home_goals, g.away_goals),
                                            (away, g.away_goals, g.home_goals)):
                points = 3 if scored > conceded else 1 if scored == conceded else 0
                state.results.append((points, scored - conceded))
                state.points += points
                state.played += 1
                state.gf += scored
                state.ga += conceded
                state.last_date = day
            stadium = home.last_stadium
            if stadium and g.attendance_status == "ok":
                cap = rows[g.match_id]["att_cap_proxy"]
                ratio = g.attendance / cap if not pd.isna(cap) and cap > 0 else None
                update = (stadium, day, int(g.attendance), g.away_team_id, ratio)
                if history_delay == "match":
                    apply_attendance(update)
                else:
                    deferred.append(update)

    result = pd.DataFrame.from_dict(rows, orient="index")[["match_id", *FEATURE_COLUMNS]]
    meta = matches[META_COLUMNS].set_index("match_id")
    return result.merge(meta, left_on="match_id", right_index=True).reset_index(drop=True)
