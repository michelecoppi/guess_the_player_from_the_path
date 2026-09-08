"""Tolleranza ai refusi: deve perdonare l'errore di battitura senza mai accettare un
calciatore per un altro."""
import pytest

from services.matching import find_match, looks_like_an_answer, normalize

ANSWERS = ["ibrahimovic", "zlatan ibrahimovic"]


@pytest.mark.parametrize("written", ["Ibrahimovic", "IBRAHIMOVIC", "  ibrahimovic  ", "Ibrahimović", "ibra-himovic"])
def test_exact_answers_survive_case_accents_and_punctuation(written):
    match = find_match(written, ANSWERS)
    assert match is not None
    assert match["typo"] is False


@pytest.mark.parametrize("written", ["ibrahimovich", "ibrahimovick", "ibrahimovc"])
def test_typos_are_accepted_and_flagged(written):
    match = find_match(written, ANSWERS)
    assert match is not None
    assert match["typo"] is True


@pytest.mark.parametrize("answers,written", [
    (["ronaldo"], "ronaldinho"),
    (["messi"], "mertens"),
    (["thiago silva"], "thiago motta"),
    (["morata"], "moratti"),
    (["xavi"], "xabi"),
    (["kane"], "kante"),
])
def test_a_different_player_is_never_accepted_as_a_typo(answers, written):
    assert find_match(written, answers) is None


def test_short_answers_only_match_exactly():
    """Su un nome corto un carattere di differenza e' un altro nome, non un refuso."""
    assert find_match("pele", ["pele"])["typo"] is False
    assert find_match("pale", ["pele"]) is None


def test_empty_and_missing_input():
    assert find_match("", ANSWERS) is None
    assert find_match("   ", ANSWERS) is None
    assert find_match("messi", []) is None


def test_normalize_collapses_spacing_and_symbols():
    assert normalize("  Van   Dijk!! ") == "van dijk"


@pytest.mark.parametrize("text", ["Messi", "zlatan ibrahimovic", "van der sar", "Kaka"])
def test_plausible_answers_are_treated_as_guesses(text):
    assert looks_like_an_answer(text) is True


@pytest.mark.parametrize("text", [
    "",
    "https://example.com/qualcosa",
    "riga uno\nriga due",
    "/start",
    "questa e' una frase molto lunga che non e' certo il nome di un calciatore",
    "questo messaggio ha decisamente troppe parole per essere un nome",
])
def test_messages_that_are_not_answers_do_not_consume_an_attempt(text):
    assert looks_like_an_answer(text) is False


@pytest.mark.parametrize("text", ["ciao", "Grazie!", "  ok  ", "gracias", "thank you"])
def test_greetings_have_the_shape_of_a_surname_but_are_not_a_guess(text):
    """Chi scrive "ciao" ha la forma di un cognome ma non sta rispondendo: non deve
    perderci uno dei tre tentativi."""
    assert looks_like_an_answer(text) is False
