"""Scelta di una sfida passata: la sorgente comune di allenamento e partite di gruppo.

Le due cose che questo file protegge: che non si peschi **mai** dal futuro (sarebbe lo
spoiler che tutta la modalita' esiste per evitare) e che pescare costi una lettura, non
trecento.
"""
import random

import pytest

from services import past_challenges
from services.past_challenges import is_playable, past_days_span, pick_past_challenge, random_past_day

TODAY = "2026-09-08"
EPOCH = "2025-06-08"


@pytest.fixture(autouse=True)
def epoch(monkeypatch):
    monkeypatch.setattr(past_challenges, "load_config", lambda: {"game_epoch": EPOCH})


def playable(day):
    return {
        "day": day,
        "career_path": [{"team": "Milan", "start_year": 2000, "end_year": 2005}],
        "correct_answers": ["maldini"],
        "player_id": "maldini",
        "difficulty": "medium",
    }


def test_the_span_stops_at_yesterday():
    """Il giorno di oggi non e' materiale d'archivio: e' la sfida in gioco."""
    assert past_days_span(TODAY) == (EPOCH, "2026-09-07")


def test_a_brand_new_game_has_no_past():
    assert past_days_span(EPOCH) is None
    assert random_past_day(EPOCH) is None


@pytest.mark.parametrize("seed", range(20))
def test_the_random_day_is_always_in_the_past(seed):
    day = random_past_day(TODAY, rng=random.Random(seed))
    assert EPOCH <= day <= "2026-09-07"


def test_a_challenge_without_the_career_path_is_not_playable():
    """Sono i documenti pre-migrazione: l'archivio ne incontra pochi, qui si pesca in un
    anno intero."""
    assert not is_playable({"day": "2025-07-01", "correct_answers": ["x"]})
    assert not is_playable({"day": "2025-07-01", "career_path": [{}]})
    assert not is_playable(None)
    assert is_playable(playable("2025-07-01"))


def test_picking_costs_one_read_when_the_day_is_there(monkeypatch):
    reads = []

    def get_daily_path(day):
        reads.append(day)
        return playable(day)

    monkeypatch.setattr(past_challenges.firebase_service, "get_daily_path", get_daily_path)

    day, challenge = pick_past_challenge(today=TODAY, rng=random.Random(1))

    assert len(reads) == 1
    assert challenge["day"] == day


def test_empty_and_broken_days_are_skipped(monkeypatch):
    """Un giorno vuoto (il bot non c'era ancora, o la pulizia ha tolto il documento) o
    inservibile non deve diventare una sfida senza immagine."""
    good_day = "2026-01-01"

    def get_daily_path(day):
        if day == good_day:
            return playable(day)
        if day.endswith("15"):
            return {"day": day}  # documento inservibile
        return None

    monkeypatch.setattr(past_challenges.firebase_service, "get_daily_path", get_daily_path)
    monkeypatch.setattr(past_challenges, "random_past_day", lambda today=None, rng=None: next(days))
    days = iter(["2025-12-15", "2025-11-03", good_day])

    day, challenge = pick_past_challenge(today=TODAY)

    assert day == good_day
    assert challenge["career_path"]


def test_the_day_asked_to_skip_is_not_proposed(monkeypatch):
    """Serve a non riproporre subito la sfida appena giocata."""
    monkeypatch.setattr(past_challenges.firebase_service, "get_daily_path", lambda day: playable(day))
    monkeypatch.setattr(past_challenges, "random_past_day", lambda today=None, rng=None: next(days))
    days = iter(["2025-12-15", "2026-02-02"])

    day, _ = pick_past_challenge(exclude_days=["2025-12-15"], today=TODAY)

    assert day == "2026-02-02"


def test_after_too_many_empty_days_it_falls_back_to_one_query(monkeypatch):
    """Con un gioco giovane (poche date scritte in un intervallo grande) la scelta a caso
    sbaglierebbe sempre: senza il ripiego l'allenamento direbbe "nessuna sfida" pur
    avendone."""
    monkeypatch.setattr(past_challenges.firebase_service, "get_daily_path", lambda day: None)
    monkeypatch.setattr(
        past_challenges.firebase_service, "get_past_daily_paths",
        lambda limit: [{"day": "2026-08-01"}, playable("2026-08-02")],
    )

    day, challenge = pick_past_challenge(today=TODAY, rng=random.Random(3))

    assert day == "2026-08-02"  # l'altro non e' giocabile
    assert challenge["correct_answers"] == ["maldini"]


def test_when_there_is_nothing_at_all_it_says_so(monkeypatch):
    monkeypatch.setattr(past_challenges.firebase_service, "get_daily_path", lambda day: None)
    monkeypatch.setattr(past_challenges.firebase_service, "get_past_daily_paths", lambda limit: [])

    assert pick_past_challenge(today=TODAY) == (None, None)
