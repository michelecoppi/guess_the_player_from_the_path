"""Le regole di una partita, provate dove vivono: services/game.py.

E' il modulo su cui poggiano **tutte e due** le facce del gioco, la chat e la mini app.
Prima queste regole stavano dentro handlers/guess_handler.py, quindi si potevano provare
solo passando per un finto messaggio Telegram: erano coperte, ma di rimbalzo.

Qui si prova la cosa vera - punti, tentativi, indizi, contatori - senza nessuna interfaccia
di mezzo, cosi' che un domani una terza faccia del gioco parta gia' con le regole giuste.
"""
import pytest

from services import game
from services.daily_challenge import MAX_ATTEMPTS

DAY = "2026-09-08"
CHALLENGE = {"day": DAY, "difficulty": "hard", "correct_answers": ["messi", "lionel messi"], "player_id": "messi"}


@pytest.fixture
def firebase(monkeypatch):
    calls = {"outcomes": [], "history": [], "registered": [], "leagues": [], "hints": []}
    state = {
        "attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 0},
        "first_free": True,
        "hint": None,
        "archive_attempt": {"ok": True, "attempts_used": 1, "attempts_left": 2},
        "challenge": CHALLENGE,
    }

    def claim(day):
        if state["first_free"]:
            state["first_free"] = False
            return True
        return False

    def register(user_id, points, bonus, day, monthly=True, attempts=None):
        calls["registered"].append({"points": points, "bonus": bonus, "attempts": attempts})
        return {"points_awarded": points, "streak_bonus": 0, "current_streak": 3}

    def take_hint(user_id, day, max_hints, max_attempts):
        calls["hints"].append({"max_hints": max_hints, "max_attempts": max_attempts})
        return state["hint"] or {"ok": True, "index": 1, "hints_used": 1}

    fs = game.firebase_service
    monkeypatch.setattr(fs, "begin_guess_attempt", lambda uid, day, mx: state["attempt"])
    monkeypatch.setattr(fs, "claim_daily_first_correct", claim)
    monkeypatch.setattr(fs, "register_correct_guess", register)
    monkeypatch.setattr(fs, "register_daily_outcome", lambda day, solved: calls["outcomes"].append((day, solved)))
    monkeypatch.setattr(
        fs, "record_daily_history",
        lambda uid, day, solved, attempts, hints=0: calls["history"].append(
            {"day": day, "solved": solved, "attempts": attempts, "hints": hints}
        ),
    )
    monkeypatch.setattr(fs, "add_points_to_leagues", lambda uid, codes, points, name=None: calls["leagues"].append(points))
    monkeypatch.setattr(fs, "take_daily_hint", take_hint)
    monkeypatch.setattr(fs, "begin_archive_attempt", lambda uid, day, mx: state["archive_attempt"])
    monkeypatch.setattr(fs, "register_archive_solved", lambda uid, day, attempts: calls.setdefault("archive", []).append(attempts))
    monkeypatch.setattr(fs, "get_daily_path", lambda day: state["challenge"])
    monkeypatch.setattr(fs, "get_display_name_for_day", lambda day: "Lionel Messi")
    monkeypatch.setattr(game, "get_today_challenge", lambda: state["challenge"])
    return type("Backend", (), {"calls": calls, "state": state})


def play(answer="messi", user=None):
    return game.play_daily(42, user or {}, answer, first_name="Anna", day_iso=DAY)


# ---------------------------------------------------------------------------
# Punti
# ---------------------------------------------------------------------------

def test_a_correct_answer_pays_the_difficulty_plus_the_first_bonus(firebase):
    result = play()
    assert result["status"] == "correct"
    assert result["points_awarded"] == 4       # hard (3) + bonus del primo (1)
    assert result["bonus"] == 1


def test_the_first_bonus_goes_to_one_person_only(firebase):
    assert play()["bonus"] == 1
    assert play()["bonus"] == 0


def test_the_hints_are_taken_off_the_points_but_not_off_the_bonus(firebase):
    """Il bonus del primo e' un premio a parte: non si sconta con gli indizi."""
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 2}
    result = play()
    assert result["points_awarded"] == 2       # (3 - 2 indizi) = 1, piu' il bonus


def test_the_points_never_go_below_one(firebase):
    firebase.state["challenge"] = dict(CHALLENGE, difficulty="easy")
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 2}
    firebase.state["first_free"] = False
    assert play()["points_awarded"] == 1       # easy vale 1: due indizi non lo portano a -1


def test_the_hints_cost_nothing_if_you_do_not_guess(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 2}
    result = play("maldini")
    assert result["status"] == "wrong"
    assert firebase.calls["registered"] == []


def test_the_points_reach_the_private_leagues(firebase):
    play(user={"leagues": ["ABC123"]})
    assert firebase.calls["leagues"] == [4]


# ---------------------------------------------------------------------------
# Tentativi
# ---------------------------------------------------------------------------

def test_a_refused_attempt_carries_its_reason(firebase):
    firebase.state["attempt"] = {"ok": False, "reason": "already_guessed"}
    assert play() == {"status": "refused", "reason": "already_guessed", "attempts_used": MAX_ATTEMPTS, "hints_used": 0}


def test_a_typo_is_accepted_and_signalled(firebase):
    result = play("messsi")
    assert result["status"] == "correct"
    assert result["typo"] is True


def test_a_wrong_answer_carries_the_comparison(firebase):
    result = play("Del Piero")
    assert result["status"] == "wrong"
    assert result["comparison"]["name"] == "Alessandro Del Piero"
    # Mai la soluzione: solo il confronto con quello che ha scritto l'utente.
    assert "messi" not in str(result["comparison"]).lower()


def test_a_name_outside_the_dataset_has_no_comparison(firebase):
    assert play("Tizio Caio")["comparison"] is None


def test_without_a_challenge_nothing_happens(firebase):
    firebase.state["challenge"] = None
    assert game.play_daily(42, {}, "messi", day_iso=DAY) == {"status": "no_challenge"}
    assert firebase.calls["outcomes"] == []


# ---------------------------------------------------------------------------
# Contatori
# ---------------------------------------------------------------------------

def test_the_first_attempt_counts_the_player_and_the_correct_one_counts_the_solve(firebase):
    play()
    assert firebase.calls["outcomes"] == [(DAY, False), (DAY, True)]


def test_a_later_attempt_does_not_count_the_player_twice(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 0}
    play("maldini")
    assert firebase.calls["outcomes"] == []


def test_the_day_is_recorded_only_when_it_closes(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 1, "attempts_left": 2, "hints_used": 0}
    play("maldini")
    assert firebase.calls["history"] == []

    firebase.state["attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0, "hints_used": 1}
    play("maldini")
    assert firebase.calls["history"] == [{"day": DAY, "solved": False, "attempts": 3, "hints": 1}]


def test_the_attempt_count_reaches_the_distribution(firebase):
    firebase.state["attempt"] = {"ok": True, "attempts_used": 2, "attempts_left": 1, "hints_used": 0}
    play()
    assert firebase.calls["registered"][0]["attempts"] == 2


# ---------------------------------------------------------------------------
# Indizi
# ---------------------------------------------------------------------------

def test_a_hint_says_what_it_leaves_you(firebase):
    result = game.take_hint(42, "it", day_iso=DAY)
    assert result["status"] == "ok"
    assert "Argentina" in result["text"]
    assert (result["full_points"], result["points"]) == (3, 2)


def test_the_maximum_offered_follows_the_player_card(firebase):
    game.take_hint(42, "it", day_iso=DAY)
    assert firebase.calls["hints"][0] == {"max_hints": 2, "max_attempts": MAX_ATTEMPTS}


def test_a_challenge_without_a_player_gives_no_hints_and_costs_nothing(firebase):
    firebase.state["challenge"] = dict(CHALLENGE, player_id=None)
    assert game.take_hint(42, "it", day_iso=DAY) == {"status": "unavailable"}
    assert firebase.calls["hints"] == []


def test_a_refused_hint_carries_its_reason(firebase):
    firebase.state["hint"] = {"ok": False, "reason": "needs_attempt"}
    assert game.take_hint(42, "it", day_iso=DAY)["reason"] == "needs_attempt"


# ---------------------------------------------------------------------------
# Archivio
# ---------------------------------------------------------------------------

def test_an_archive_day_gives_no_points(firebase):
    result = game.play_archive(42, "2026-09-01", "messi", 3)
    assert result["status"] == "correct"
    assert firebase.calls["registered"] == []
    assert "points_awarded" not in result


def test_the_last_archive_attempt_reveals_the_answer(firebase):
    """A differenza della sfida di oggi, qui la risposta si puo' dire: e' gia' passata."""
    firebase.state["archive_attempt"] = {"ok": True, "attempts_used": 3, "attempts_left": 0}
    result = game.play_archive(42, "2026-09-01", "maldini", 3)
    assert result["answer"] == "Lionel Messi"


def test_an_archive_attempt_still_gets_the_comparison(firebase):
    result = game.play_archive(42, "2026-09-01", "Del Piero", 3)
    assert result["comparison"]["name"] == "Alessandro Del Piero"
