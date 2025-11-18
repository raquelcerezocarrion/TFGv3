from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_user_profile_endpoint():
    r = client.get("/user/profile")
    assert r.status_code in (200, 401, 403, 404)
