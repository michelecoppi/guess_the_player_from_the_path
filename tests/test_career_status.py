"""Unit test per `domains.players.career_status.infer_active_status`."""
from domains.players.career_status import infer_active_status


def test_empty_career_defaults_active():
    assert infer_active_status([]) is True
    assert infer_active_status(None) is True


def test_last_stop_without_end_year_is_active():
    career = [
        {"team": "Barcelona", "start_year": 2004, "end_year": 2021},
        {"team": "PSG", "start_year": 2021, "end_year": None},
    ]
    assert infer_active_status(career, current_year=2026) is True


def test_end_year_in_past_is_retired():
    career = [
        {"team": "Roma", "start_year": 2000, "end_year": 2010},
        {"team": "Milan", "start_year": 2010, "end_year": 2017},
    ]
    assert infer_active_status(career, current_year=2026) is False


def test_end_year_in_future_or_current_is_active():
    career = [{"team": "Inter Miami", "start_year": 2023, "end_year": 2026}]
    assert infer_active_status(career, current_year=2026) is True
    assert infer_active_status(career, current_year=2020) is True


def test_unordered_stops_use_max_start_year():
    career = [
        {"team": "A", "start_year": 2010, "end_year": 2015},
        {"team": "C", "start_year": 2020, "end_year": None},
        {"team": "B", "start_year": 2015, "end_year": 2020},
    ]
    assert infer_active_status(career, current_year=2026) is True


def test_stops_missing_start_year_fallback_to_list_order():
    career = [
        {"team": "A", "end_year": 2010},
        {"team": "B", "end_year": 2015},
    ]
    assert infer_active_status(career, current_year=2026) is False


def test_default_current_year_is_injectable():
    career = [{"team": "A", "start_year": 2000, "end_year": 2005}]
    assert infer_active_status(career, current_year=2005) is True
    assert infer_active_status(career, current_year=2006) is False


def test_incomplete_stop_data_does_not_crash():
    career = [{"team": "A"}, {}]
    assert infer_active_status(career, current_year=2026) is True
