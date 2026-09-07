"""Classifica: solo la top 10 viene letta da Firestore, la posizione personale si ottiene
con un conteggio lato server invece di scaricare tutti gli utenti.
"""
from handlers import top_users_handler


def _users(n, start_points=100):
    return [
        {"telegram_id": i, "username": f"Utente{i}", "points": start_points - i, "monthly_points": 50 - i}
        for i in range(1, n + 1)
    ]


def test_top_ten_is_rendered_with_medals_and_highlight():
    message = top_users_handler.format_leaderboard(_users(10), telegram_id=3, view="global")

    assert "🥇 Utente1" in message
    assert "🔟 Utente10" in message
    assert "[TU]" in message
    assert message.count("[TU]") == 1


def test_monthly_view_uses_monthly_points():
    message = top_users_handler.format_leaderboard(_users(3), telegram_id=1, view="monthly")

    assert "Top 10 mensile" in message
    assert "49 punti" in message  # monthly_points di Utente1


def test_user_in_top_ten_does_not_trigger_a_count(monkeypatch):
    calls = []
    monkeypatch.setattr(top_users_handler.firebase_service, "get_top_users", lambda field, limit: _users(10))
    monkeypatch.setattr(top_users_handler.firebase_service, "count_users_ahead",
                        lambda field, value: calls.append((field, value)))
    monkeypatch.setattr(top_users_handler.firebase_service, "get_user_data",
                        lambda uid: (_ for _ in ()).throw(AssertionError("non deve servire")))

    message = top_users_handler._leaderboard_for("global", telegram_id=5)

    assert calls == []
    assert "La tua posizione" not in message


def test_user_outside_top_ten_gets_their_position_from_a_count(monkeypatch):
    monkeypatch.setattr(top_users_handler.firebase_service, "get_top_users", lambda field, limit: _users(10))
    monkeypatch.setattr(top_users_handler.firebase_service, "get_user_data",
                        lambda uid: {"points_totali": 12, "monthly_points": 3})
    monkeypatch.setattr(top_users_handler.firebase_service, "count_users_ahead", lambda field, value: 41)

    message = top_users_handler._leaderboard_for("global", telegram_id=999)

    assert "La tua posizione:</b> 42° - 12 punti" in message


def test_unregistered_user_still_sees_the_leaderboard(monkeypatch):
    monkeypatch.setattr(top_users_handler.firebase_service, "get_top_users", lambda field, limit: _users(3))
    monkeypatch.setattr(top_users_handler.firebase_service, "get_user_data", lambda uid: None)

    message = top_users_handler._leaderboard_for("global", telegram_id=999)

    assert "Utente1" in message
    assert "La tua posizione" not in message
