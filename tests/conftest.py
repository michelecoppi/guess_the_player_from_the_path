"""Unit tests must never fall through to the configured production database."""
import pytest

from services import firebase_service


@pytest.fixture(autouse=True)
def no_live_firestore(monkeypatch):
    def forbidden(self):
        raise AssertionError("Live Firestore access in unit test: provide a fake repository/client")
    monkeypatch.setattr(firebase_service._LazyFirestoreClient, "_ensure", forbidden)
