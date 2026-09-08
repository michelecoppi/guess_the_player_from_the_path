"""Confronto mostrato dopo un tentativo sbagliato.

Le due cose da non sbagliare mai: non deve uscire nessun confronto quando non si puo'
fare (sfida vecchia senza `player_id`, nome non nel dataset), e non deve **mai** dire quale
squadra ha in comune con la soluzione - quelle sono gia' nell'immagine, e il confronto
esiste proprio per aggiungere le informazioni che l'immagine non da'.
"""
import pytest

from services import guess_feedback
from services.guess_feedback import build_comparison, compare_players, comparison_text

RONALDO = {
    "id": "ronaldo",
    "full_name": "Ronaldo Nazario",
    "aliases": ["ronaldo", "ronaldo nazario"],
    "nationality": "Brasile",
    "position": "Attaccante",
    "birth_year": 1976,
}
DEL_PIERO = {
    "id": "del_piero",
    "full_name": "Alessandro Del Piero",
    "aliases": ["del piero", "alessandro del piero"],
    "nationality": "Italia",
    "position": "Attaccante",
    "birth_year": 1974,
}
BUFFON = {
    "id": "buffon",
    "full_name": "Gianluigi Buffon",
    "aliases": ["buffon", "gianluigi buffon"],
    "nationality": "Italia",
    "position": "Portiere",
    "birth_year": 1978,
}


@pytest.fixture
def dataset(monkeypatch):
    """Un dataset finto di tre schede, cosi' il test non cambia di significato quando
    qualcuno aggiunge un calciatore a data/players.json."""
    players = {p["id"]: p for p in (RONALDO, DEL_PIERO, BUFFON)}

    def find_player_by_answer(text):
        normalized = text.strip().lower()
        for player in players.values():
            if normalized in player["aliases"] or normalized == player["full_name"].lower():
                return player
        return None

    monkeypatch.setattr(guess_feedback, "get_player_by_id", players.get)
    monkeypatch.setattr(guess_feedback, "find_player_by_answer", find_player_by_answer)
    return players


def test_the_comparison_covers_nationality_position_and_age():
    clues = dict(compare_players(DEL_PIERO, RONALDO))

    assert "feedback.nationality_diff" in clues
    assert "feedback.position_same" in clues
    # Ronaldo (1976) e' nato dopo Del Piero (1974): la freccia guarda in giu'.
    assert clues["feedback.birth_after"] == {"year": 1974}


def test_two_players_of_the_same_country_and_role():
    clues = dict(compare_players(BUFFON, BUFFON))

    assert "feedback.nationality_same" in clues
    assert "feedback.position_same" in clues
    assert clues["feedback.birth_same"] == {"year": 1978}


def test_the_comparison_never_mentions_teams():
    """Le squadre sono gia' tutte nell'immagine: ripeterle non sarebbe un indizio, e
    rischierebbe di dire quante tappe ha la soluzione."""
    keys = [key for key, _ in compare_players(DEL_PIERO, RONALDO)]

    assert not any("team" in key or "club" in key for key in keys)


def test_a_name_outside_the_dataset_gets_no_comparison(dataset):
    assert build_comparison("un nome inventato", "ronaldo") is None


def test_a_challenge_without_player_id_gets_no_comparison(dataset):
    """Le sfide generate prima della revisione del database non hanno `player_id`: senza,
    non c'e' niente da confrontare e il messaggio resta quello di prima."""
    assert build_comparison("Del Piero", None) is None


def test_a_player_that_left_the_dataset_gets_no_comparison(dataset):
    assert build_comparison("Del Piero", "scheda_rimossa") is None


def test_guessing_the_solution_itself_gets_no_comparison(dataset):
    """Capita solo se qualcuno ha corretto a mano le risposte accettate: tre spunte verdi
    sotto un "sbagliato" confonderebbero e basta."""
    assert build_comparison("Ronaldo", "ronaldo") is None


def test_the_rendered_block_names_the_player_the_bot_understood(dataset):
    """Con la tolleranza ai refusi il bot puo' aver capito un altro calciatore: il nome in
    testa al blocco e' l'unico modo che ha l'utente di accorgersene."""
    text = comparison_text("it", build_comparison("Del Piero", "ronaldo"))

    assert "Alessandro Del Piero" in text
    assert "Ronaldo" not in text  # mai la soluzione


def test_no_comparison_renders_as_nothing_at_all():
    assert comparison_text("it", None) == ""


def test_the_real_dataset_resolves_a_name_with_a_typo():
    """Sul dataset vero: chi scrive "Ibrahimovich" merita il confronto come chi lo scrive
    giusto, esattamente come per le risposte accettate."""
    from services.player_pool import find_player_by_answer

    player = find_player_by_answer("ibrahimovich")

    assert player is not None
    assert "Ibrahimovic" in player["full_name"]
