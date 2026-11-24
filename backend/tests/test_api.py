import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.main import app
from db.session import engine

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    DB_AVAILABLE = True
except SQLAlchemyError:
    DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not DB_AVAILABLE, reason="PostgreSQL недоступен")
client = TestClient(app)


def test_health_reports_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_current_model_has_metrics_for_both_validations():
    response = client.get("/api/model")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "production"
    assert {"cv", "test", "naive_test"} <= set(body["metrics"])


def test_seasons_mark_untrusted_attendance():
    seasons = {row["season"]: row for row in client.get("/api/seasons").json()}
    assert seasons[2022]["ok"] > 300
    assert seasons[2024]["ok"] == 0 and seasons[2024]["suspect"] > 0


def test_matches_filter_by_season_and_team():
    teams = client.get("/api/teams", params={"season": 2022}).json()
    arsenal = next(t["id"] for t in teams if t["name"] == "Arsenal")
    page = client.get("/api/matches", params={"season": 2022, "team_id": arsenal, "limit": 100}).json()
    assert page["total"] == 38 == len(page["items"])
    assert all("Arsenal" in (m["home_team"], m["away_team"]) for m in page["items"])
    assert all(m["season"] == 2022 for m in page["items"])


def test_upcoming_matches_have_forecast_but_no_fact():
    page = client.get("/api/matches", params={"when": "upcoming", "limit": 500}).json()
    assert page["total"] > 0
    assert all(m["attendance"] is None and m["predicted"] is not None for m in page["items"])


def test_matches_rejects_oversized_page():
    assert client.get("/api/matches", params={"limit": 10_000}).status_code == 422


def test_quality_has_overall_row_computed_on_trusted_matches_only():
    rows = client.get("/api/quality").json()
    overall = rows[-1]
    assert overall["season"] is None
    assert overall["matches"] == sum(r["matches"] for r in rows[:-1])
    assert {r["season"] for r in rows[:-1]}.isdisjoint({2019, 2020, 2021, 2023, 2024, 2025})
