"""Recap mensile (#245) su un Firestore vero: le chiavi per mese ("2026-08") nei percorsi puntati."""
import pytest

from services import firebase_service, monthly_closure, monthly_recap

pytestmark = pytest.mark.usefixtures("emulator_db")


def test_the_monthly_reset_keeps_the_closed_month_points():
    firebase_service.save_user(1, "Anna")
    ref = firebase_service.user_ref(1)
    ref.update({"monthly_points": 110, "monthly_earned": {"2026-08": 100, "2026-09": 10}})

    monthly_closure.reset_user(ref, {"closed_month": "2026-08", "new_month": "2026-09"})

    user = firebase_service.get_user_data(1)
    assert user["monthly_totals"] == {"2026-08": 100}
    assert user["monthly_points"] == 10


def test_a_recap_is_cached_under_its_month():
    firebase_service.save_user(1, "Anna")
    for n in range(1, 10):
        firebase_service.history_ref(1, f"2026-08-{n:02d}").set(
            {"day": f"2026-08-{n:02d}", "solved": True, "attempts": 1, "hints": 0, "first": False})
    firebase_service.db.collection("monthly_closures").document("2026-08").set({"points_distribution": [1, 2, 3]})

    recap = monthly_recap.recap_for(1, firebase_service.get_user_data(1), "2026-08", today="2026-09-03")

    assert recap["available"] is True and recap["played"] == 9
    assert firebase_service.get_user_data(1)["recaps"]["2026-08"] == recap
