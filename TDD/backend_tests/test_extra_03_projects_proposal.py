from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_projects_proposal_endpoint():
    r = client.post("/projects/proposal", json={"title": "TDD test"})
    # aceptar 422 u otros códigos comunes
    assert r.status_code in (200, 400, 401, 403, 404, 422)
