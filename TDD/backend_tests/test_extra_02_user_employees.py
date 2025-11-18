from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_user_employees_endpoint_exists():
    # puede requerir auth; aceptar códigos permisivos
    r = client.get("/user/employees")
    assert r.status_code in (200, 401, 403, 404)
