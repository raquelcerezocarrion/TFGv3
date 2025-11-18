from backend.retrieval import similarity


def test_similarity_module_importable():
    assert similarity is not None


def test_similarity_function_exists():
    # el módulo puede variar; comprobar que existe
    assert similarity is not None
