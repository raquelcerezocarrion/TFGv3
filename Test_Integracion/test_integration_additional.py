import time
import uuid

def random_email():
    return f"itest+{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"


def test_register_duplicate_and_login_failure(client):
    email = random_email()
    password = "secret123"

    # First registration should succeed
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Dup Test"})
    assert r.status_code == 200

    # Duplicate registration should return 400
    r2 = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Dup Test"})
    assert r2.status_code == 400

    # Login with wrong password should return 401
    r3 = client.post("/auth/login", json={"email": email, "password": "badpass"})
    assert r3.status_code == 401


def test_user_me_requires_auth_and_returns_user(client):
    # Without auth header -> 401
    r = client.get("/user/me")
    assert r.status_code == 401

    # Create user and get token
    email = random_email()
    password = "secret123"
    rreg = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Me Test"})
    assert rreg.status_code == 200
    token = rreg.json().get("access_token")
    assert token

    headers = {"Authorization": f"Bearer {token}"}
    rme = client.get("/user/me", headers=headers)
    assert rme.status_code == 200
    data = rme.json()
    assert data.get("email") == email


def test_projects_proposal_minimal_payload(client):
    # This endpoint does not require auth; provide minimal valid payload
    payload = {"session_id": f"itest-{int(time.time())}", "requirements": "Crear una API simple para pruebas"}
    r = client.post("/projects/proposal", json=payload)
    assert r.status_code == 200
    body = r.json()
    # response_model: methodology, team, phases, budget, risks, explanation
    for k in ("methodology", "team", "phases", "budget", "risks", "explanation"):
        assert k in body


def test_projects_recommend_basic(client):
    # POST /projects/recommend expects {query, top_k}
    payload = {"query": "desarrollo de API REST", "top_k": 3}
    r = client.post("/projects/recommend", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_export_chat_pdf_returns_pdf(client):
    # export endpoint expects messages; no auth required
    payload = {
        "title": "Export Test",
        "messages": [
            {"role": "assistant", "content": "Metodología: breve explicación. Equipo: 2 devs."}
        ]
    }
    r = client.post("/export/chat.pdf", json=payload)
    assert r.status_code == 200
    # StreamingResponse should set content-type to application/pdf
    ct = r.headers.get("content-type", "")
    assert "application/pdf" in ct
    # body should not be empty
    assert r.content and len(r.content) > 0


def test_employee_creation_validation_error(client):
    # register user to get token
    import time, uuid
    email = f"itest-val-{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Val Test"})
    assert r.status_code == 200
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # availability_pct must be between 0 and 100; sending 200 -> 422
    bad_payload = {"name": "Bad Emp", "role": "Dev", "skills": "Python", "availability_pct": 200}
    r2 = client.post("/user/employees", headers=headers, json=bad_payload)
    assert r2.status_code == 422


def test_convert_chat_block_to_proposal_and_get_phases(client):
    # Register and create a saved chat containing an assistant block that looks like a proposal
    import time, uuid
    email = f"itest-prop-{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"
    password = "secret123"
    rreg = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Prop Test"})
    assert rreg.status_code == 200
    token = rreg.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Build a saved chat content: assistant block starting with 'Metodología' and contains 'Equipo'
    assistant_block = {
        "role": "assistant",
        "content": "Metodología: Scrum\nEquipo: 2 devs\nFases: Descubrimiento, Desarrollo\nPresupuesto: 10000 €",
        "ts": str(int(time.time()))
    }
    chat_payload = {"title": "Chat for proposal", "content": [assistant_block]}
    # The saved chat endpoint expects content as JSON string or text; backend expects JSON string in stored chats
    import json
    rchat = client.post("/user/chats", headers=headers, json={"title": chat_payload["title"], "content": json.dumps(chat_payload["content"])})
    assert rchat.status_code == 200
    chat = rchat.json()
    chat_id = chat["id"]

    # Convert chat block to proposal
    rconv = client.post(f"/projects/from_chat/{chat_id}/to_proposal", json={"content": assistant_block["content"], "requirements": "Importada desde chat"})
    assert rconv.status_code == 200
    conv_body = rconv.json()
    proposal_id = conv_body.get("proposal_id")
    assert proposal_id

    # Now request phases for that proposal
    rph = client.get(f"/projects/{proposal_id}/phases")
    assert rph.status_code == 200
    phases = rph.json()
    assert isinstance(phases, list) and len(phases) > 0
