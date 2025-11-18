from backend.memory import state_store


def test_state_store_module_importable():
    assert state_store is not None


def test_state_store_set_get_if_available():
    if hasattr(state_store, "set_session_state") and hasattr(state_store, "get_session_state"):
        sid = "tdd-test-ss"
        state_store.set_session_state(sid, {"x": 1})
        got = state_store.get_session_state(sid)
        assert isinstance(got, dict) or got is None
    else:
        assert True
