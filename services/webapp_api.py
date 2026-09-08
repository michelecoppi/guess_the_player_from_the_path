"""Dati mostrati dalla mini app Telegram.

Sta qui e non dentro l'endpoint per la stessa ragione per cui `evaluate_event_guess` sta
fuori dagli handler: cosi' si prova senza tirare su FastAPI e senza Firestore.

Nessuna di queste informazioni e' segreta — sono le stesse di /stats, /top e /lega — ma
l'utente di cui si parla lo decide la firma di initData (services/webapp_auth.py), mai il
client.
"""
from services import firebase_service
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.dates import normalize_day, today_iso
from services.difficulty import points_for_difficulty

MAX_LEAGUES_SHOWN = 5
LEADERBOARD_SIZE = 10


def build_profile(user_id, day_iso=None):
    """Tutto quello che serve alla pagina, in una risposta sola. None se l'utente non
    esiste ancora (non ha mai fatto /start)."""
    user = firebase_service.get_user_data(user_id)
    if not user:
        return None

    day_iso = day_iso or today_iso()

    return {
        "user": _user_summary(user),
        "today": _today_summary(user, day_iso),
        "leaderboard": _leaderboard(user_id),
        "leagues": _leagues(user, user_id),
    }


def _user_summary(user):
    return {
        "name": user.get("first_name", "?"),
        "points": user.get("points_totali", 0),
        "monthly_points": user.get("monthly_points", 0),
        "players_guessed": user.get("players_guessed", 0),
        "bonus_first_guessed": user.get("bonus_first_guessed", 0),
        "streak": user.get("current_streak", 0),
        "best_streak": user.get("best_streak", 0),
        "archive_solved": user.get("archive_solved", 0),
        "trophies": len(user.get("trophies", [])),
    }


def _today_summary(user, day_iso):
    challenge = firebase_service.get_daily_path(day_iso) or {}
    played_today = normalize_day(user.get("last_played_day")) == day_iso
    solved = bool(played_today and user.get("has_guessed_today"))
    attempts_used = user.get("daily_attempts", 0) if played_today else 0

    return {
        "number": challenge_number(day_iso),
        "available": bool(challenge),
        "solved": solved,
        "attempts_used": attempts_used,
        "attempts_left": max(MAX_ATTEMPTS - attempts_used, 0),
        "max_attempts": MAX_ATTEMPTS,
        "difficulty": challenge.get("difficulty"),
        "points": points_for_difficulty(challenge.get("difficulty")) if challenge else 0,
        "bonus_available": bool(challenge) and not challenge.get("first_correct_user", False),
    }


def _leaderboard(user_id):
    top = firebase_service.get_top_users(limit=LEADERBOARD_SIZE)
    return [
        {
            "position": position,
            "name": entry.get("username", "?"),
            "points": entry.get("points", 0),
            "me": entry.get("telegram_id") == user_id,
        }
        for position, entry in enumerate(top, start=1)
    ]


def _leagues(user, user_id):
    leagues = []
    for code in (user.get("leagues") or [])[:MAX_LEAGUES_SHOWN]:
        league = firebase_service.get_league(code)
        if not league:
            continue
        members = firebase_service.get_league_leaderboard(code, limit=20)
        position = next(
            (index for index, member in enumerate(members, start=1) if member.get("telegram_id") == user_id),
            None,
        )
        points = next(
            (member.get("points", 0) for member in members if member.get("telegram_id") == user_id),
            0,
        )
        leagues.append({
            "code": code,
            "name": league.get("name", code),
            "members": league.get("members_count", len(members)),
            "position": position,
            "points": points,
        })
    return leagues
