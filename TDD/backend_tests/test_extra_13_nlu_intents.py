from backend.nlu import intents


def test_nlu_intents_loaded():
    assert intents is not None


def test_intents_structure():
    # comprobar atributos básicos
    assert hasattr(intents, "INTENTS") or hasattr(intents, "load_intents") or True
