"""Striscia di giorni consecutivi e card del risultato."""
import pytest

from services.share import CORRECT, HINT, UNUSED, WRONG, result_squares, share_text
from services.streak import next_streak, next_threshold, streak_bonus


def test_a_first_correct_answer_starts_the_streak():
    assert next_streak(None, "2026-09-08", 0) == 1


def test_answering_the_day_after_continues_the_streak():
    assert next_streak("2026-09-07", "2026-09-08", 4) == 5


def test_skipping_a_day_restarts_from_one():
    assert next_streak("2026-09-06", "2026-09-08", 12) == 1


def test_answering_twice_the_same_day_does_not_count_twice():
    assert next_streak("2026-09-08", "2026-09-08", 3) == 3


def test_a_legacy_date_in_the_old_format_is_understood():
    """I documenti scritti prima della migrazione hanno le date in gg/mm/aa: la striscia
    non deve azzerarsi solo per il formato."""
    assert next_streak("07/09/26", "2026-09-08", 2) == 3


@pytest.mark.parametrize("streak,expected", [(0, 0), (2, 0), (3, 1), (6, 1), (7, 2), (29, 2), (30, 3), (500, 3)])
def test_the_streak_bonus_grows_by_steps_and_is_capped(streak, expected):
    assert streak_bonus(streak) == expected


def test_next_threshold_tells_what_is_missing():
    assert next_threshold(1) == 3
    assert next_threshold(5) == 7
    assert next_threshold(30) is None


def test_squares_show_how_many_attempts_it_took():
    assert result_squares(1, 3) == CORRECT + UNUSED * 2
    assert result_squares(2, 3) == WRONG + CORRECT + UNUSED
    assert result_squares(3, 3) == WRONG * 2 + CORRECT


def test_squares_of_a_failed_day():
    assert result_squares(3, 3, solved=False) == WRONG * 3


def test_the_shared_text_never_contains_the_answer():
    text = share_text("it", 142, attempts_used=2, max_attempts=3, solved=True, streak=5)
    assert "142" in text
    assert "2/3" in text
    assert CORRECT in text
    assert "messi" not in text.lower()


def test_the_streak_appears_only_when_there_is_one():
    assert "🔥" not in share_text("en", 1, 1, 3, streak=1)
    assert "🔥" in share_text("en", 1, 1, 3, streak=4)


def test_the_hints_appear_as_lightbulbs():
    """Serve a distinguere due "1/3" identici: uno dei due si e' fatto aiutare."""
    assert HINT not in share_text("it", 1, 1, 3)
    assert share_text("it", 1, 1, 3, hints=1).count(HINT) == 1
    assert share_text("it", 1, 1, 3, hints=2).count(HINT) == 2


def test_the_hints_never_leak_the_answer_either():
    text = share_text("it", 142, 3, 3, solved=False, hints=2)
    assert "X/3" in text
    assert "messi" not in text.lower()
    assert "Argentina" not in text


def test_the_percentage_of_solvers_stays_out_of_the_shared_card():
    """E' un'informazione sulla **difficolta' di oggi**, e la card la legge anche chi non ha
    ancora giocato: dirla li' sarebbe mezzo spoiler."""
    assert "%" not in share_text("it", 142, 1, 3, hints=1, streak=3)


# ---------------------------------------------------------------------------
# Link invito e frase d'invito (#150)
# ---------------------------------------------------------------------------

INVITE = "https://t.me/guess_the_player_bot?start=ref_7_0123456789abcdef0123"


def test_the_last_line_invites_with_the_sharer_link():
    text = share_text("it", 214, 2, 3, link=INVITE)

    assert text.splitlines()[-1] == f"Riesci a fare meglio? 👉 {INVITE}"


@pytest.mark.parametrize("lang, invite", [("es", "¿Puedes hacerlo mejor?"), ("en", "Can you do better?")])
def test_the_invite_line_is_translated(lang, invite):
    assert share_text(lang, 214, 2, 3, link=INVITE).splitlines()[-1] == f"{invite} 👉 {INVITE}"


def test_without_an_invite_link_the_bot_link_is_used(monkeypatch):
    from services import share

    monkeypatch.setattr(share, "BOT_USERNAME", "guess_the_player_bot")
    assert share_text("it", 214, 2, 3).splitlines()[-1] == "Riesci a fare meglio? 👉 https://t.me/guess_the_player_bot"


def test_without_any_link_there_is_no_invite_line(monkeypatch):
    from services import share

    monkeypatch.setattr(share, "BOT_USERNAME", "")
    assert share_text("it", 214, 2, 3) == "⚽ Guess the Player #214\n🟥🟩⬜ 2/3"
    assert share.share_url("x") is None


def test_the_share_button_points_at_the_invite_link():
    from urllib.parse import parse_qs, urlparse

    from services import share

    query = parse_qs(urlparse(share.share_url("testo", INVITE)).query)
    assert query["url"] == [INVITE]
    assert query["text"] == ["testo"]
