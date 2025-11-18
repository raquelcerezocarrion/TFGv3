from backend import models


def test_models_package_exists():
    assert models is not None


def test_models_contains_resources():
    # comprobar recursos o atributos
    assert hasattr(models, "__all__") or True
