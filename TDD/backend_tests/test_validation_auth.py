from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_register_invalid_email_requires_valid_format():
    r = client.post("/auth/register", json={"email": "invalid-email", "password": "secret123", "full_name": "X"})
    assert r.status_code == 422


def test_register_short_password_returns_422():
    r = client.post("/auth/register", json={"email": "a@b.com", "password": "123", "full_name": "X"})
    assert r.status_code == 422


def test_login_empty_body_returns_422():
    r = client.post("/auth/login", json={})
    assert r.status_code == 422
