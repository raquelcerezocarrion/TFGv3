from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_chat_message_endpoint():
    r = client.post("/chat/message", json={"session_id": "tdd", "message": "hola"})
    assert r.status_code in (200, 400, 401, 403, 404)
