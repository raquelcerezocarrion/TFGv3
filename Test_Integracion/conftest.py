import pytest
from fastapi.testclient import TestClient
import os
import sys

# Asegurarse de que el paquete backend sea importable
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from backend.app import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
