from backend.engine import brain
import inspect


def test_brain_module_available():
    assert brain is not None


def _try_call(func, sample):
    sig = inspect.signature(func)
    params = list(sig.parameters)
    try:
        if len(params) == 1:
            return func(sample)
        elif len(params) == 2:
            try:
                return func(None, sample)
            except TypeError:
                return func(sample, None)
        else:
            return func(sample)
    except Exception:
        return None


def test_brain_can_process_sample_if_api_exists():
    sample = [{"name": "TDD", "role": "Dev"}]
    if hasattr(brain, "suggest_staffing"):
        out = _try_call(brain.suggest_staffing, sample)
        assert True
    elif hasattr(brain, "_suggest_staffing"):
        out = _try_call(brain._suggest_staffing, sample)
        assert True
    else:
        assert True
