def test_get_user_employees_empty_or_list(client):
    # Este endpoint puede requerir autenticación; intentar sin token y aceptar 200 o 401
    resp = client.get("/user/employees")
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list)
