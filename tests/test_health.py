"""Health check endpoint tests."""

from fastapi.testclient import TestClient

from squire.api.app import create_app


def test_health_returns_ok():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
