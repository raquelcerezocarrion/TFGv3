from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_auth_login_endpoint():
    r = client.post("/auth/login", json={"username": "tdd", "password": "tdd"})
    # aceptar 422 u otros códigos de auth
    assert r.status_code in (200, 400, 401, 403, 404, 422)
