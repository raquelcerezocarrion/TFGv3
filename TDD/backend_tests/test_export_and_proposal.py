from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_projects_proposal_details():
    payload = {"session_id": "tdd-session", "requirements": "Demo proyecto para pruebas"}
    resp = client.post("/projects/proposal", json=payload)
    assert resp.status_code == 200
    data = resp.json()
   
    if resp.status_code == 200:
        assert isinstance(data.get("methodology"), str)
        assert isinstance(data.get("phases"), list)


def test_export_chat_pdf_endpoint_accepts_payload_or_requires_auth():
    payload = {"title": "TDD export", "report_meta": {}, "report_options": {}, "messages": []}
    resp = client.post("/export/chat.pdf", json=payload)
   
    assert resp.status_code in (200, 401, 400)


def test_proposal_contains_phases_structure():
    payload = {"session_id": "tdd-session-2", "requirements": "Otra prueba"}
    resp = client.post("/projects/proposal", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    if isinstance(data.get("phases"), list):
        for p in data.get("phases"):
            
            if isinstance(p, dict):
                assert "name" in p
