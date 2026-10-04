"""The API under test against a throwaway SQLite database and storage directories.

The settings are read at import time, so they are set before ``app`` is imported.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="memoir-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/memoir.db"
os.environ["AUDIO_STORAGE_DIR"] = f"{_TMP}/audio"
os.environ["DOCUMENT_STORAGE_DIR"] = f"{_TMP}/documents"
os.environ["COMPREFACE_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
