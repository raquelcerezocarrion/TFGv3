from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_root_returns_something():
    r = client.get("/")
    # aceptar códigos comunes (OK, redirect, not found)
    assert r.status_code in (200, 301, 302, 307, 308, 404)
