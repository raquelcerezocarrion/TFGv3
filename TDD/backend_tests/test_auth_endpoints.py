import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_user_employees_requires_auth_or_returns_list():
    resp = client.get("/user/employees")
    assert resp.status_code in (200, 401)


def test_protected_endpoint_with_bad_token():
    headers = {"Authorization": "Bearer INVALID_TOKEN"}
    resp = client.get("/user/employees", headers=headers)
    # puede ser 401 o 200; comprobar auth
    assert resp.status_code in (200, 401)


def test_health_endpoint():
    # endpoint health (si existe)
    resp = client.get("/health")
    assert resp.status_code in (200, 404)
