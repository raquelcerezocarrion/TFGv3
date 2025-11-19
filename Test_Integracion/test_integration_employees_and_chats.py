import time
import uuid

def random_email():
    return f"itest+{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"


def test_user_employee_crud_and_chats_flow(client):
    # 1) Register a fresh user
    email = random_email()
    password = "secret123"
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "IT Test"})
    assert r.status_code == 200
    token = r.json().get("access_token")
    assert token

    headers = {"Authorization": f"Bearer {token}"}

    # 2) Initially list employees (should be empty list)
    r = client.get("/user/employees", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 3) Create an employee
    emp_payload = {"name": "Test Emp", "role": "Backend", "skills": "Python,FastAPI", "seniority": "Senior", "availability_pct": 100}
    r = client.post("/user/employees", headers=headers, json=emp_payload)
    assert r.status_code == 200
    emp = r.json()
    assert emp.get("id")
    emp_id = emp["id"]

    # 4) Get the employee by id
    r = client.get(f"/user/employees/{emp_id}", headers=headers)
    assert r.status_code == 200
    got = r.json()
    assert got["name"] == emp_payload["name"]

    # 5) Update the employee
    r = client.put(f"/user/employees/{emp_id}", headers=headers, json={"name": "Updated Emp", "availability_pct": 80})
    assert r.status_code == 200
    updated = r.json()
    assert updated["name"] == "Updated Emp"
    assert updated["availability_pct"] == 80

    # 6) Delete the employee
    r = client.delete(f"/user/employees/{emp_id}", headers=headers)
    assert r.status_code == 200

    # 7) Ensure employee not found afterwards
    r = client.get(f"/user/employees/{emp_id}", headers=headers)
    assert r.status_code == 404

    # --- Chats CRUD (saved chats) ---
    # 8) Create a saved chat
    chat_payload = {"title": "IT Test Chat", "content": "[]"}
    r = client.post("/user/chats", headers=headers, json=chat_payload)
    assert r.status_code == 200
    chat = r.json()
    chat_id = chat["id"]

    # 9) Get chat
    r = client.get(f"/user/chats/{chat_id}", headers=headers)
    assert r.status_code == 200

    # 10) Update chat title
    r = client.put(f"/user/chats/{chat_id}", headers=headers, json={"title": "Updated Title"})
    assert r.status_code == 200
    assert r.json()["title"] == "Updated Title"

    # 11) Continue chat (session id generation)
    r = client.post(f"/user/chats/{chat_id}/continue", headers=headers)
    assert r.status_code == 200
    assert "session_id" in r.json()

    # 12) Delete chat
    r = client.delete(f"/user/chats/{chat_id}", headers=headers)
    assert r.status_code == 200

    # 13) Ensure chat gone
    r = client.get(f"/user/chats/{chat_id}", headers=headers)
    assert r.status_code == 404
