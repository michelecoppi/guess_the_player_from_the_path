"""Il materiale di allenamento e dei round di gruppo.

L'invariante da non rompere mai e' una sola: **niente di quello che si vede allenandosi
puo' arrivare come sfida del giorno**. Se salta, chi si allena si prende il bonus del primo
sapendo gia' la risposta.
"""
import random

import pytest

from services import practice_content
from services.player_pool import get_all_players, get_practice_players, is_practice_only, reload_dataset
from services.practice_content import DAY_PREFIX, POOL_PREFIX, from_daily, from_player, load, pick

PLAYER = {
    "id": "maldini",
    "full_name": "Paolo Maldini",
    "aliases": ["maldini"],
    "nationality": "Italia",
    "position": "Difensore",
    "birth_year": 1968,
    "popularity": 5,
    "career": [{"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009}],
}
DAILY = {
    "day": "2026-09-07",
    "player_id": "deligt",
    "correct_answers": ["de ligt", "matthijs de ligt"],
    "career_path": [{"team": "Ajax", "start_year": 2016, "end_year": 2019}],
    "difficulty": "hard",
}


# ---------------------------------------------------------------------------
# L'invariante
# ---------------------------------------------------------------------------

def test_the_two_pools_never_overlap():
    """Sul dataset vero: un giocatore o alimenta il gioco, o l'allenamento."""
    reload_dataset()
    game = {p["id"] for p in get_all_players()}
    practice = {p["id"] for p in get_practice_players()}

    assert game and practice
    assert game & practice == set()


def test_the_reserved_slice_is_marked_in_the_dataset():
    """Non calcolata a runtime: se la regola cambiasse, un giocatore passerebbe da una parte
    all'altra e chi si e' allenato su di lui avrebbe la risposta gia' pronta."""
    assert all(is_practice_only(player) for player in get_practice_players())


def test_every_difficulty_is_represented_in_training():
    """Una fetta tutta di un colore renderebbe l'allenamento inutile come esercizio."""
    from services.difficulty import DIFFICULTY_ORDER, group_players_by_difficulty

    groups = group_players_by_difficulty(get_practice_players())

    assert all(groups.get(level) for level in DIFFICULTY_ORDER)


# ---------------------------------------------------------------------------
# La forma comune
# ---------------------------------------------------------------------------

def test_a_reserved_player_becomes_a_challenge():
    challenge = from_player(PLAYER)

    assert challenge["key"] == "pool:maldini"
    assert challenge["answer"] == "Paolo Maldini"
    assert "maldini" in challenge["correct_answers"]
    assert challenge["career_path"] == PLAYER["career"]
    assert challenge["day"] is None


def test_a_past_day_becomes_the_same_kind_of_challenge():
    challenge = from_daily("2026-09-07", DAILY)

    assert challenge["key"] == "day:2026-09-07"
    assert challenge["day"] == "2026-09-07"
    assert challenge["career_path"] == DAILY["career_path"]


def test_the_name_to_reveal_survives_a_player_removed_from_the_dataset():
    """Senza la scheda si ripiega sugli alias, preferendo nome e cognome: e' quello che si
    mostra a tentativi finiti, e "de ligt" e' meglio di "?"."""
    challenge = from_daily("2026-09-07", dict(DAILY, player_id="sparito"))

    assert challenge["answer"] == "Matthijs De Ligt"


# ---------------------------------------------------------------------------
# La scelta
# ---------------------------------------------------------------------------

@pytest.fixture
def sources(monkeypatch):
    monkeypatch.setattr(practice_content, "get_practice_players", lambda: [PLAYER])
    monkeypatch.setattr(
        practice_content, "pick_past_challenge",
        lambda exclude_days=(), rng=None: ("2026-09-07", DAILY),
    )
    monkeypatch.setattr(practice_content, "load_config", lambda: {"practice_past_challenge_ratio": 0.25})


class _Rng:
    """Un generatore che dice sempre lo stesso numero: serve a scegliere la sorgente."""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value

    def choice(self, items):
        return items[0]


def test_most_of_the_time_it_serves_the_reserved_pool(sources):
    """Il pool e' la sorgente principale perche' e' gratis (nessuna lettura) e c'e' sempre."""
    challenge = pick(rng=_Rng(0.9))

    assert challenge["key"].startswith(POOL_PREFIX)


def test_every_so_often_it_serves_a_real_past_challenge(sources):
    challenge = pick(rng=_Rng(0.1))

    assert challenge["key"].startswith(DAY_PREFIX)


def test_with_no_past_challenges_it_falls_back_to_the_pool(sources, monkeypatch):
    """E' il caso di oggi: il gioco ha appena ricominciato a scrivere sfide."""
    monkeypatch.setattr(practice_content, "pick_past_challenge", lambda exclude_days=(), rng=None: (None, None))

    challenge = pick(rng=_Rng(0.1))

    assert challenge["key"].startswith(POOL_PREFIX)


def test_the_challenge_just_played_is_not_served_again(sources, monkeypatch):
    monkeypatch.setattr(practice_content, "get_practice_players", lambda: [PLAYER, dict(PLAYER, id="baresi")])

    challenge = pick(exclude_keys=["pool:maldini"], rng=_Rng(0.9))

    assert challenge["key"] == "pool:baresi"


def test_with_a_single_reserved_player_it_repeats_rather_than_refusing(sources):
    challenge = pick(exclude_keys=["pool:maldini"], rng=_Rng(0.9))

    assert challenge["key"] == "pool:maldini"


def test_an_empty_pool_and_no_past_means_nothing_to_serve(sources, monkeypatch):
    monkeypatch.setattr(practice_content, "get_practice_players", lambda: [])
    monkeypatch.setattr(practice_content, "pick_past_challenge", lambda exclude_days=(), rng=None: (None, None))

    assert pick(rng=random.Random(1)) is None


# ---------------------------------------------------------------------------
# Riprendere una partita
# ---------------------------------------------------------------------------

def test_a_pool_session_is_resumed_without_touching_the_database(monkeypatch):
    """La scheda e' nel file dentro il container: riprendere non costa nessuna lettura."""
    monkeypatch.setattr(practice_content, "get_player_by_id", lambda pid: PLAYER if pid == "maldini" else None)
    monkeypatch.setattr(
        practice_content.firebase_service, "get_daily_path",
        lambda day: pytest.fail("una sfida del pool non deve leggere Firestore"),
    )

    assert load("pool:maldini")["answer"] == "Paolo Maldini"


def test_a_past_session_is_resumed_with_one_read(monkeypatch):
    reads = []
    monkeypatch.setattr(
        practice_content.firebase_service, "get_daily_path",
        lambda day: reads.append(day) or DAILY,
    )

    challenge = load("day:2026-09-07")

    assert reads == ["2026-09-07"]
    assert challenge["key"] == "day:2026-09-07"


@pytest.mark.parametrize("key", [None, "", "boh", "pool:nessuno"])
def test_a_key_that_leads_nowhere_is_not_a_crash(key, monkeypatch):
    monkeypatch.setattr(practice_content, "get_player_by_id", lambda pid: None)
    assert load(key) is None


def test_the_headline_players_stay_in_the_real_game():
    """I nomi da copertina (popolarita' 5) non si riservano: sono quelli che fanno venire
    voglia di rispondere a chi apre il bot la prima volta, e riservarli li toglierebbe per
    sempre dalla sfida del giorno."""
    assert [p["full_name"] for p in get_practice_players() if p.get("popularity", 3) >= 5] == []
