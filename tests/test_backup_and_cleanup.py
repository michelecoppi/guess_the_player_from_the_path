"""Backup ricorrente e pulizia di `daily_path`.

Sono le due cose che girano da sole su dati veri e cancellano roba: la parte che decide
cosa sparisce e' una funzione pura apposta per poterla provare qui, senza Firestore.
"""
import json
from datetime import datetime, timezone

import pytest

from scripts.cleanup_daily_paths import classify, save_copy
from services.firestore_backup import codec

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
# Copia prima della cancellazione
# ---------------------------------------------------------------------------
# Il backup vero e proprio (export, formato, restore) e' provato in tests/test_backup_format.py,
# tests/test_backup_restore_safety.py e, su un Firestore vero, tests/test_backup_restore_emulator.py.

def test_the_copy_before_deleting_keeps_timestamps_typed(tmp_path):
    """La copia usa la stessa codifica del backup: una data resta una data, non testo."""
    stamp = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    path = save_copy([("2024-03-01", {"day": "2024-03-01", "generated_at": stamp}, None)], str(tmp_path), "old")

    with open(path, encoding="utf-8") as f:
        saved = json.load(f)["2024-03-01"]
    assert codec.decode_fields(saved, "daily_path/*")["generated_at"] == stamp


@pytest.mark.parametrize("day", ["2026-09-07", "2025-09-09"])
def test_the_window_boundary_keeps_the_last_year(day):
    assert classify(day, valid(day), CUTOFF, TODAY) == "keep"
