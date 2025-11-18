def test_projects_proposal_structure(client):
    payload = {"session_id": "test-session", "requirements": "Crear una app de ejemplo"}
    resp = client.post("/projects/proposal", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Basic expected keys
    assert "methodology" in data
    assert "phases" in data and isinstance(data["phases"], list)
    assert "team" in data and isinstance(data["team"], list)
    assert "budget" in data and isinstance(data["budget"], dict)
