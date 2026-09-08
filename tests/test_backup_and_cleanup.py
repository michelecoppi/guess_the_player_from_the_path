"""Backup ricorrente e pulizia di `daily_path`.

Sono le due cose che girano da sole su dati veri e cancellano roba: la parte che decide
cosa sparisce e' una funzione pura apposta per poterla provare qui, senza Firestore.
"""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from scripts.backup_firestore import export, export_document, jsonable, write_dump
from scripts.cleanup_daily_paths import classify

TODAY = "2026-09-08"
CUTOFF = "2025-09-08"  # un anno prima


def valid(day):
    return {"day": day, "career_path": [{"team": "Milan"}], "correct_answers": ["maldini"]}


# ---------------------------------------------------------------------------
# Pulizia
# ---------------------------------------------------------------------------

def test_a_recent_challenge_is_kept():
    assert classify("2026-06-01", valid("2026-06-01"), CUTOFF, TODAY) == "keep"


def test_a_challenge_older_than_the_window_goes_away():
    assert classify("2024-03-01", valid("2024-03-01"), CUTOFF, TODAY) == "old"


def test_todays_challenge_is_never_touched():
    """E' la sfida in gioco: nemmeno se il documento fosse malmesso."""
    assert classify(TODAY, {"day": TODAY}, CUTOFF, TODAY) == "keep"


def test_the_generated_buffer_is_never_touched():
    assert classify("2026-09-10", valid("2026-09-10"), CUTOFF, TODAY) == "keep"


def test_a_document_with_a_pre_migration_id_is_legacy():
    """`08-09-25` invece di `2025-09-08`: nessuna query per intervallo lo trova, e
    l'archivio non lo sa aprire."""
    assert classify("08-09-25", {"current_day": "08/09/25"}, CUTOFF, TODAY) == "legacy"


def test_a_recent_document_without_the_career_path_is_legacy():
    data = {"day": "2026-06-01", "correct_answers": ["maldini"]}
    assert classify("2026-06-01", data, CUTOFF, TODAY) == "legacy"


def test_a_recent_document_without_accepted_answers_is_legacy():
    data = {"day": "2026-06-01", "career_path": [{"team": "Milan"}]}
    assert classify("2026-06-01", data, CUTOFF, TODAY) == "legacy"


def test_an_old_document_is_old_even_if_it_is_also_broken():
    """Meglio "vecchio": si cancella con la pulizia normale, senza chiedere --drop-legacy."""
    assert classify("2020-01-01", {"day": "2020-01-01"}, CUTOFF, TODAY) == "old"


def test_a_challenge_kept_only_as_an_image_is_still_playable():
    """Gli eventi `career` e le sfide vecchie salvano `image_url` invece del percorso."""
    data = {"day": "2026-06-01", "image_url": "file_id", "correct_answers": ["maldini"]}
    assert classify("2026-06-01", data, CUTOFF, TODAY) == "keep"


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

class FakeDoc:
    def __init__(self, doc_id, data, subcollections=None):
        self.id = doc_id
        self._data = data
        self.reference = SimpleNamespace(collections=lambda: subcollections or [])

    def to_dict(self):
        return self._data


class FakeCollection:
    def __init__(self, name, docs):
        self.id = name
        self._docs = docs

    def stream(self):
        return iter(self._docs)


def test_the_backup_follows_subcollections():
    """I partecipanti a un evento e i membri di una lega stanno in sotto-collezioni: un
    export che si ferma al primo livello sarebbe un backup finto."""
    participants = FakeCollection("participants", [FakeDoc("42", {"points": 7})])
    event = FakeDoc("giramondo", {"name": "Giramondo"}, subcollections=[participants])

    exported = export_document(event)

    assert exported["_data"]["name"] == "Giramondo"
    assert exported["_subcollections"]["participants"]["42"]["_data"]["points"] == 7


def test_the_backup_covers_every_collection_asked_for():
    db = SimpleNamespace(collection=lambda name: FakeCollection(name, [FakeDoc("1", {"a": 1})]))

    dump = export(db, collections=("users", "daily_path"))

    assert sorted(dump) == ["daily_path", "users"]
    assert dump["users"]["1"]["_data"] == {"a": 1}


def test_firestore_types_survive_the_json():
    """Le date arrivano come datetime e i riferimenti come oggetti: senza conversione il
    backup fallirebbe a meta' export, cioe' esattamente quando serve."""
    converted = jsonable({"quando": datetime(2026, 9, 8, 12, 0), "ref": object(), "n": [1, None]})

    assert converted["quando"] == "2026-09-08T12:00:00"
    assert isinstance(converted["ref"], str)
    assert converted["n"] == [1, None]


def test_the_dump_is_written_as_readable_json(tmp_path):
    path = write_dump({"users": {"1": {"_data": {"first_name": "Anna"}}}}, str(tmp_path))

    with open(path, encoding="utf-8") as f:
        assert json.load(f)["users"]["1"]["_data"]["first_name"] == "Anna"


@pytest.mark.parametrize("day", ["2026-09-07", "2025-09-09"])
def test_the_window_boundary_keeps_the_last_year(day):
    assert classify(day, valid(day), CUTOFF, TODAY) == "keep"
