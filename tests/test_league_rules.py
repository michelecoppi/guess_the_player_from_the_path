"""Le regole delle leghe, provate dove vivono: services/leagues.py.

Da questa tranche una lega si crea, si entra e si esce da due posti (la chat e la mini app).
I limiti devono essere gli stessi in entrambi, ed e' proprio questo che i test qui
garantiscono: la regola sta in un posto solo, quindi non ci sono due versioni da tenere
allineate.
"""
import pytest

from services import leagues


@pytest.fixture
def firebase(monkeypatch):
    state = {"taken": set(), "join": "ok", "leagues": {"ABC23X": {"code": "ABC23X", "name": "Amici del bar"}}}
    calls = {"created": [], "joined": [], "left": []}

    def create_league(code, name, owner_id, owner_name):
        calls["created"].append({"code": code, "name": name})
        if code in state["taken"]:
            return False
        state["taken"].add(code)
        return True

    monkeypatch.setattr(leagues.firebase_service, "create_league", create_league)
    monkeypatch.setattr(
        leagues.firebase_service, "join_league",
        lambda code, uid, name, mx: calls["joined"].append((code, mx)) or state["join"],
    )
    monkeypatch.setattr(leagues.firebase_service, "get_league", lambda code: state["leagues"].get(code))
    monkeypatch.setattr(
        leagues.firebase_service, "leave_league",
        lambda code, uid: bool(calls["left"].append(code)) or True,
    )
    return type("Backend", (), {"state": state, "calls": calls})


# ---------------------------------------------------------------------------
# Il codice
# ---------------------------------------------------------------------------

def test_the_code_avoids_the_characters_that_get_confused_when_dictated():
    for _ in range(50):
        code = leagues.generate_code()
        assert len(code) == leagues.CODE_LENGTH
        assert not set(code) & set("O0I1")


def test_the_code_is_read_in_any_case_and_with_spaces_around():
    assert leagues.normalize_code("  abc23x ") == "ABC23X"
    assert leagues.normalize_code(None) == ""


# ---------------------------------------------------------------------------
# Creare
# ---------------------------------------------------------------------------

def test_creating_a_league_returns_its_code(firebase):
    status, code = leagues.create(42, {}, "Amici del bar", "Anna")
    assert status == "ok"
    assert len(code) == leagues.CODE_LENGTH


def test_a_taken_code_is_retried(firebase):
    """Lo spazio dei codici e' enorme, ma una collisione non deve far fallire la creazione."""
    original = leagues.generate_code
    codes = iter(["AAAAAA", "AAAAAA", "BBBBBB"])
    leagues.generate_code = lambda: next(codes)
    try:
        firebase.state["taken"].add("AAAAAA")
        status, code = leagues.create(42, {}, "Amici", "Anna")
    finally:
        leagues.generate_code = original

    assert (status, code) == ("ok", "BBBBBB")


@pytest.mark.parametrize("name,expected", [
    ("", "no_name"),
    ("   ", "no_name"),
    ("x" * (leagues.MAX_NAME_LENGTH + 1), "name_too_long"),
])
def test_a_bad_name_is_refused_before_writing_anything(firebase, name, expected):
    status, code = leagues.create(42, {}, name, "Anna")
    assert (status, code) == (expected, None)
    assert firebase.calls["created"] == []


def test_nobody_goes_over_the_league_limit(firebase):
    user = {"leagues": ["A"] * leagues.MAX_LEAGUES_PER_USER}
    assert leagues.create(42, user, "Un'altra", "Anna") == ("limit", None)
    assert leagues.join(42, user, "ABC23X", "Anna") == ("limit", None)
    assert firebase.calls["created"] == []
    assert firebase.calls["joined"] == []


# ---------------------------------------------------------------------------
# Entrare e uscire
# ---------------------------------------------------------------------------

def test_joining_returns_the_league(firebase):
    status, league = leagues.join(42, {}, "abc23x", "Anna")
    assert status == "ok"
    assert league["name"] == "Amici del bar"
    assert firebase.calls["joined"] == [("ABC23X", leagues.MAX_MEMBERS)]


@pytest.mark.parametrize("reason", ["not_found", "already_member", "full"])
def test_a_refused_join_carries_its_reason(firebase, reason):
    firebase.state["join"] = reason
    assert leagues.join(42, {}, "ABC23X", "Anna") == (reason, None)


def test_joining_without_a_code_writes_nothing(firebase):
    assert leagues.join(42, {}, "  ", "Anna") == ("no_code", None)
    assert firebase.calls["joined"] == []


def test_leaving_returns_the_league_you_left(firebase):
    status, league = leagues.leave(42, "abc23x")
    assert status == "ok"
    assert league["name"] == "Amici del bar"
    assert firebase.calls["left"] == ["ABC23X"]


def test_leaving_a_league_that_does_not_exist(firebase):
    assert leagues.leave(42, "ZZZZZZ") == ("not_found", None)
    assert firebase.calls["left"] == []


def test_leaving_a_league_you_are_not_in(firebase, monkeypatch):
    monkeypatch.setattr(leagues.firebase_service, "leave_league", lambda code, uid: False)
    status, league = leagues.leave(42, "ABC23X")
    assert status == "not_member"
    assert league["name"] == "Amici del bar"
