import pytest
from fastapi.testclient import TestClient
import os
import sys

# asegurar que backend es importable
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ROOT)

from backend.app import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def pytest_ignore_collect(path, config):
    """Ignore duplicate test filenames that collide with `backend/tests`.

    Some test files were intentionally duplicated under `TDD/backend_tests` for
    additional coverage. To avoid pytest import collisions (same module name
    imported from different locations), skip collecting the conflicting
    basenames here — the prefixed `tdd_` versions will be collected instead.
    """
    try:
        name = path.basename
    except Exception:
        return False
    duplicates = {"test_projects_proposal.py", "test_user_employees.py"}
    if name in duplicates:
        return True
    return False
