import time
import uuid

def random_email():
    return f"itest+{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"


def test_register_duplicate_and_login_failure(client):
    email = random_email()
    password = "secret123"

    # El primer registro debe tener éxito
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Dup Test"})
    assert r.status_code == 200

    # El registro duplicado debe devolver 400
    r2 = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Dup Test"})
    assert r2.status_code == 400

    # Login con contraseña incorrecta debe devolver 401
    r3 = client.post("/auth/login", json={"email": email, "password": "badpass"})
    assert r3.status_code == 401


def test_user_me_requires_auth_and_returns_user(client):
    # Sin cabecera de autenticación -> 401
    r = client.get("/user/me")
    assert r.status_code == 401

    # Crear usuario y obtener token
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
    # Este endpoint no requiere auth; proporcionar payload mínimo válido
    payload = {"session_id": f"itest-{int(time.time())}", "requirements": "Crear una API simple para pruebas"}
    r = client.post("/projects/proposal", json=payload)
    assert r.status_code == 200
    body = r.json()
    # response_model: methodology, team, phases, budget, risks, explanation
    for k in ("methodology", "team", "phases", "budget", "risks", "explanation"):
        assert k in body


def test_projects_recommend_basic(client):
    # POST /projects/recommend espera {query, top_k}
    payload = {"query": "desarrollo de API REST", "top_k": 3}
    r = client.post("/projects/recommend", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
