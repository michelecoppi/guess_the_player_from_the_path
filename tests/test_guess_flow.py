"""Flusso di /guess dopo il passaggio a tentativi transazionali e reset "pigro"."""
import asyncio
from types import SimpleNamespace

import pytest

from handlers import guess_handler


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.chat = SimpleNamespace(type="private")
        self.replies = []
        self.markups = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))


def make_update(text, user_id=42):
    message = FakeMessage(text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, first_name="Anna"),
        message=message,
        effective_message=message,
    )
    return update, message


CHALLENGE = {"correct_answers": ["messi", "lionel messi"], "difficulty": "medium", "career_path": [{}, {}]}


@pytest.fixture
def firebase(monkeypatch):
    """Sostituto in memoria delle sole funzioni Firestore usate da /guess."""
    calls = {"registered": [], "claims": 0, "attempts": []}

    state = {
        "attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 0},
        "first_free": True,
        # `None` = utente non ancora registrato, cioe' il caso dei test gia' scritti.
        "user": None,
    }

    def begin_guess_attempt(user_id, day, max_attempts):
        calls["attempts"].append((user_id, day, max_attempts))
        return state["attempt"]

    def claim_daily_first_correct(day):
        calls["claims"] += 1
        if state["first_free"]:
            state["first_free"] = False
            return True
        return False

    def register_correct_guess(user_id, points, bonus, day, monthly=True, attempts=None):
        calls["registered"].append({
            "user_id": user_id, "points": points, "bonus": bonus, "day": day, "attempts": attempts,
        })

    monkeypatch.setattr(guess_handler.firebase_service, "begin_guess_attempt", begin_guess_attempt)
    monkeypatch.setattr(guess_handler.firebase_service, "claim_daily_first_correct", claim_daily_first_correct)
    monkeypatch.setattr(guess_handler.firebase_service, "register_correct_guess", register_correct_guess)
    monkeypatch.setattr(guess_handler.firebase_service, "get_user_data", lambda uid: state["user"])
    monkeypatch.setattr(
        guess_handler.firebase_service, "register_daily_outcome",
        lambda day, solved: calls.setdefault("outcomes", []).append((day, solved)),
    )
    monkeypatch.setattr(
        guess_handler.firebase_service, "record_daily_history",
        lambda uid, day, solved, attempts, hints=0: calls.setdefault("history", []).append(
            {"day": day, "solved": solved, "attempts": attempts, "hints": hints}
        ),
    )
    monkeypatch.setattr(
        guess_handler.firebase_service, "add_points_to_leagues",
        lambda uid, codes, points, name=None: calls.setdefault("leagues", []).append((codes, points)),
    )
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: CHALLENGE)
    return SimpleNamespace(calls=calls, state=state)


def test_correct_answer_awards_points_plus_first_bonus(firebase):
    update, message = make_update("/guess Messi")
    asyncio.run(guess_handler.guess(update, None))

    registered = firebase.calls["registered"][0]
    assert registered["bonus"] == 1
    assert registered["points"] == 3  # medium (2) + bonus (1)
    assert "Corretto" in message.replies[0]


def test_only_the_first_correct_user_gets_the_bonus(firebase):
    update, _ = make_update("/guess messi", user_id=1)
    asyncio.run(guess_handler.guess(update, None))
    update, message = make_update("/guess messi", user_id=2)
    asyncio.run(guess_handler.guess(update, None))

    assert [r["bonus"] for r in firebase.calls["registered"]] == [1, 0]
    assert [r["points"] for r in firebase.calls["registered"]] == [3, 2]
    assert "Bonus" not in message.replies[0]


def test_wrong_answer_reports_remaining_attempts(firebase):
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"] == []
    assert "Tentativi rimasti: 2" in message.replies[0]


def test_last_wrong_attempt_says_when_the_answer_will_be_revealed(firebase):
    """Tentativi finiti: non si rivela (la giornata e' aperta per tutti gli altri) ma si dice
    quando e come si scopre la risposta. Prima era solo "riprova domani"."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert "tentativi finiti" in message.replies[0].lower()
    assert "/solution" in message.replies[0]
    assert "Messi" not in message.replies[0]


@pytest.mark.parametrize("reason,expected", [
    ("not_registered", "registrarti"),
    ("already_guessed", "già indovinato"),
    ("no_attempts", "esaurito i tentativi"),
])
def test_refused_attempts_are_explained(firebase, reason, expected):
    firebase.state["attempt"] = {"ok": False, "reason": reason}
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert expected in message.replies[0]
    assert firebase.calls["registered"] == []


def test_empty_guess_does_not_consume_an_attempt(firebase):
    update, message = make_update("/guess   ")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "Devi scrivere" in message.replies[0]


def test_missing_challenge_does_not_consume_an_attempt(firebase, monkeypatch):
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: None)
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "sfida giornaliera" in message.replies[0]


def test_guess_in_a_group_never_touches_the_daily_challenge(firebase, monkeypatch):
    """In un gruppo /guess risponde al round del gruppo, mai alla sfida di oggi: la
    risposta comparirebbe in chiaro davanti a chi non ha ancora giocato."""
    from handlers import group_handler

    monkeypatch.setattr(group_handler.firebase_service, "get_group_round", lambda chat_id: None)
    update, message = make_update("/guess messi")
    update.message.chat = SimpleNamespace(type="group", id=-100123)
    asyncio.run(guess_handler.guess(update, None))

    assert "round" in message.replies[0].lower()
    assert firebase.calls["attempts"] == []


def test_a_plain_message_counts_as_a_guess(firebase):
    """Scrivere il nome senza /guess deve valere come tentativo: era l'attrito principale."""
    update, message = make_update("Messi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["registered"][0]["points"] == 3
    assert "Corretto" in message.replies[0]


def test_a_message_that_is_not_an_answer_does_not_consume_an_attempt(firebase):
    update, message = make_update("https://esempio.it/una-pagina-qualsiasi")
    asyncio.run(guess_handler.free_text_guess(update, None))

    assert firebase.calls["attempts"] == []
    assert "Scrivimi il nome" in message.replies[0]


def test_a_typo_is_accepted_and_signalled(firebase):
    update, message = make_update("/guess messsi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"][0]["points"] == 3
    assert "Corretto" in message.replies[0]
    assert "messsi" in message.replies[0]


def test_another_player_is_still_wrong(firebase):
    update, message = make_update("/guess maldini")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"] == []
    assert "Tentativi rimasti: 2" in message.replies[0]


# ---------------------------------------------------------------------------
# Card condivisibile e confronto dopo un tentativo sbagliato
# ---------------------------------------------------------------------------

@pytest.fixture
def shareable(monkeypatch):
    """Senza BOT_USERNAME non c'e' nessun link da condividere e il bottone non compare:
    nei test lo diamo per configurato, altrimenti si proverebbe il caso sbagliato."""
    from services import share

    monkeypatch.setattr(share, "BOT_USERNAME", "guess_the_player_bot")


def test_a_lost_day_can_be_shared_too(firebase, shareable):
    """Il quadratino "X/3" e' meta' di quello che si incolla in un gruppo, e non puo'
    spoilerare niente: prima il bottone c'era solo per chi indovinava."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert message.markups[0] is not None
    url = message.markups[0].inline_keyboard[0][0].url
    assert "X%2F3" in url  # "X/3", cioe' giornata non risolta


def test_attempts_left_over_do_not_show_the_share_button(firebase, shareable):
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert message.markups[0] is None


def test_a_wrong_guess_is_compared_with_the_solution(firebase, monkeypatch):
    """Il confronto e' la sola cosa che un tentativo sbagliato lascia in mano a chi gioca."""
    monkeypatch.setattr(
        guess_handler, "get_today_challenge",
        lambda: dict(CHALLENGE, player_id="messi"),
    )
    update, message = make_update("/guess Del Piero")
    asyncio.run(guess_handler.guess(update, None))

    reply = message.replies[0]
    assert "Del Piero" in reply           # il nome che il bot ha capito
    assert "Nazionalit\u00e0" in reply
    assert "messi" not in reply.lower()   # mai la soluzione


def test_a_challenge_without_player_id_answers_exactly_like_before(firebase):
    """Le sfide vecchie non hanno `player_id`: il messaggio deve restare quello di prima,
    non un blocco vuoto o un errore."""
    update, message = make_update("/guess Del Piero")
    asyncio.run(guess_handler.guess(update, None))

    assert message.replies[0] == "\u274c Risposta sbagliata, riprova! Tentativi rimasti: 2."


# ---------------------------------------------------------------------------
# Indizi
# ---------------------------------------------------------------------------

def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data] if markup else []


@pytest.fixture
def with_player_id(monkeypatch):
    """Una sfida di cui si sa **chi** era: e' la condizione per avere indizi e confronto."""
    monkeypatch.setattr(guess_handler, "get_today_challenge", lambda: dict(CHALLENGE, player_id="messi"))


def test_a_wrong_answer_offers_a_hint(firebase, with_player_id):
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert _callbacks(message.markups[0]) == ["hint_daily"]


def test_the_hint_is_not_offered_once_they_are_used_up(firebase, with_player_id):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 2}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert _callbacks(message.markups[0]) == []


def test_the_hint_is_not_offered_when_the_attempts_are_over(firebase, with_player_id, shareable):
    """A tentativi finiti un indizio non servirebbe a niente e costerebbe comunque un punto."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 0}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert "hint_daily" not in _callbacks(message.markups[0])


def test_the_hints_are_paid_out_of_the_points(firebase):
    """Gli indizi si scalano solo se si indovina: su una sfida persa non c'era niente da
    togliere."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 2}
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    # medium (2) - 2 indizi = pavimento a 1, piu' il bonus del primo.
    assert firebase.calls["registered"][0]["points"] == 2


def test_without_hints_the_points_do_not_change(firebase):
    update, _ = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"][0]["points"] == 3  # medium (2) + bonus (1)


def test_the_shared_card_shows_the_hints_used(firebase, shareable):
    """Due "1/3" identici non sono la stessa partita se uno dei due si e' fatto aiutare."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 1}
    update, message = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert "%F0%9F%92%A1" in message.markups[0].inline_keyboard[0][0].url  # la lampadina


# ---------------------------------------------------------------------------
# "Avvisami a mezzanotte"
# ---------------------------------------------------------------------------

def test_losing_offers_the_notifications_to_who_has_them_off(firebase, shareable):
    """Il messaggio dice "te lo dico a mezzanotte": a chi le notifiche non le ha, quella
    frase da sola non varrebbe niente."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 0}
    firebase.state["user"] = {"notifications_enabled": False}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert "notify_on" in _callbacks(message.markups[0])


def test_who_already_has_the_notifications_is_not_asked_again(firebase, shareable):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 0}
    firebase.state["user"] = {"notifications_enabled": True}
    update, message = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert "notify_on" not in _callbacks(message.markups[0])


# ---------------------------------------------------------------------------
# Contatori della giornata (la percentuale mostrata a giornata chiusa)
# ---------------------------------------------------------------------------

def test_the_first_attempt_of_the_day_counts_the_player(firebase):
    update, _ = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    day = firebase.calls["attempts"][0][1]
    assert firebase.calls["outcomes"] == [(day, False)]


def test_the_following_attempts_do_not_count_again(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 0}
    update, _ = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls.get("outcomes", []) == []


def test_a_correct_answer_counts_as_solved(firebase):
    update, _ = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert [solved for _, solved in firebase.calls["outcomes"]] == [False, True]


def test_the_day_is_recorded_when_it_closes(firebase):
    """Il calendario della mini app deve poter dire "questa l'hai presa al secondo": dai
    contatori sul documento utente non si ricava, li sovrascrive il giorno dopo."""
    update, _ = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["history"] == [{"day": firebase.calls["attempts"][0][1], "solved": True, "attempts": 1, "hints": 0}]


def test_a_lost_day_is_recorded_too(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 1}
    update, _ = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["history"][0]["solved"] is False
    assert firebase.calls["history"][0]["hints"] == 1


def test_a_day_still_open_is_not_recorded_yet(firebase):
    """Si scrive una volta sola, quando la giornata si chiude: non ad ogni tentativo."""
    update, _ = make_update("/guess ronaldo")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls.get("history", []) == []


def test_the_attempt_count_feeds_the_distribution(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 0}
    update, _ = make_update("/guess messi")
    asyncio.run(guess_handler.guess(update, None))

    assert firebase.calls["registered"][0]["attempts"] == 2
