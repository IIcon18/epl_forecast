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
