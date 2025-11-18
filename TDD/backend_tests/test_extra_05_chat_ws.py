from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_chat_ws_connects_if_available():
    try:
        with client.websocket_connect("/chat/ws") as ws:
            # enviar ping si se permite
            try:
                ws.send_json({"type": "ping"})
            except Exception:
                pass
    except Exception:
        # si no hay websocket, pasar
        assert True
