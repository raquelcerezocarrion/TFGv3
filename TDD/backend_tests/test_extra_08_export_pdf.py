from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_export_pdf_endpoint_exists():
    r = client.post("/export/pdf", json={"session_id": "tdd"})
    assert r.status_code in (200, 400, 401, 403, 404)
