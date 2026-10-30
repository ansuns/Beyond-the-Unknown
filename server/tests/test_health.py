from fastapi.testclient import TestClient

from app.main import app


def test_liveness_is_available_without_external_services() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
