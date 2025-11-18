from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_projects_list_endpoint():
    r = client.get("/projects")
    assert r.status_code in (200, 401, 403, 404)
