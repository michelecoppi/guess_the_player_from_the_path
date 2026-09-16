"""Difficolta' prevista contro osservata (#21): le regole del confronto, senza Firestore."""
import pytest
from firebase_admin import firestore

from services import difficulty_calibration as calibration
from services.difficulty import model_fingerprint, predict_difficulty
from services.player_pool import get_player_by_id, load_config


def _config(**settings):
    config = dict(load_config())
    config["difficulty_calibration"] = dict(calibration.DEFAULT_SETTINGS, **settings)
    return config


# ---------------------------------------------------------------------------
# Osservato
# ---------------------------------------------------------------------------

def test_too_few_players_give_no_observed_score():
    observed = calibration.observed_difficulty({"players_count": 4, "solved_count": 1}, config=_config(min_players=5))
    assert observed["enough_data"] is False
    assert observed["score"] is None
    assert observed["completion_rate"] == 25.0


def test_everyone_solving_at_the_first_attempt_is_zero_and_nobody_solving_is_hundred():
    config = _config(min_players=5)
    easiest = {"players_count": 10, "solved_count": 10, "solved_attempts_total": 10}
    hardest = {"players_count": 10, "solved_count": 0}
    assert calibration.observed_difficulty(easiest, config=config)["score"] == 0.0
    assert calibration.observed_difficulty(hardest, config=config)["score"] == 100.0


def test_observed_score_blends_failures_and_attempts_with_the_configured_weights():
    doc = {"players_count": 20, "solved_count": 10, "solved_attempts_total": 20, "solved_hints_total": 5}
    config = _config(min_players=5, failure_weight=0.5, attempts_weight=0.5)
    observed = calibration.observed_difficulty(doc, config=config, max_attempts=3)
    # fallimento 0.5, tentativi medi 2 su 3 -> (2-1)/(3-1) = 0.5
    assert observed["score"] == 50.0
    assert observed["avg_attempts"] == 2.0
    assert observed["avg_hints"] == 0.5


def test_days_before_the_attempt_counters_use_the_completion_rate_only():
    doc = {"players_count": 20, "solved_count": 15}
    observed = calibration.observed_difficulty(doc, config=_config(min_players=5))
    assert observed["avg_attempts"] is None
    assert observed["score"] == 25.0


def test_solved_count_never_exceeds_players():
    observed = calibration.observed_difficulty({"players_count": 10, "solved_count": 12}, config=_config(min_players=5))
    assert observed["solved"] == 10
    assert observed["completion_rate"] == 100.0


# ---------------------------------------------------------------------------
# Previsto
# ---------------------------------------------------------------------------

def test_the_photographed_prediction_wins_over_the_recomputed_one():
    player = get_player_by_id("jankto")
    doc = {"difficulty_prediction": {"score": 12.5, "band": "easy", "model": "vecchia"}}
    predicted = calibration.predicted_difficulty(doc, player=player)
    assert predicted == {"score": 12.5, "band": "easy", "model": "vecchia", "source": calibration.SOURCE_SNAPSHOT}


def test_without_a_snapshot_the_prediction_is_recomputed_and_marked():
    player = get_player_by_id("jankto")
    predicted = calibration.predicted_difficulty({}, player=player)
    assert predicted["source"] == calibration.SOURCE_RECOMPUTED
    assert predicted["score"] == predict_difficulty(player)["score"]
    assert calibration.predicted_difficulty({}, player=None) is None


# ---------------------------------------------------------------------------
# Correlazione e report
# ---------------------------------------------------------------------------

def test_spearman_measures_rank_agreement():
    assert calibration.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert calibration.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert calibration.spearman([1, 2], [1, 2]) is None
    assert calibration.spearman([1, 2, 3], [5, 5, 5]) is None


PLAYERS = {
    "a": {"id": "a", "full_name": "A", "popularity": 5,
          "career": [{"team": "X", "country": "Italia", "league": "Serie A", "start_year": 2000, "end_year": 2015}]},
    "b": {"id": "b", "full_name": "B", "popularity": 4,
          "career": [{"team": "X", "country": "Italia", "league": "Serie A", "start_year": 2005, "end_year": None}]},
    "c": {"id": "c", "full_name": "C", "popularity": 2,
          "career": [{"team": "Y", "country": "Qatar", "league": "Qatar Stars League",
                      "start_year": 1990, "end_year": 2001}]},
}


def _day(day, player_id, predicted_score, band, solved, players=20, model="m1"):
    return {
        "day": day, "player_id": player_id, "difficulty": band,
        "difficulty_prediction": {"score": predicted_score, "band": band, "model": model},
        "players_count": players, "solved_count": solved, "solved_attempts_total": solved * 2,
    }


def _report(docs, **settings):
    return calibration.build_report(docs, config=_config(**settings), player_lookup=PLAYERS.get)


def test_a_formula_that_orders_days_like_players_do_has_no_mismatches():
    docs = [
        _day("2026-01-01", "a", 10, "easy", solved=18),
        _day("2026-01-02", "b", 40, "medium", solved=12),
        _day("2026-01-03", "c", 90, "impossible", solved=2),
    ]
    report = _report(docs, min_players=10)
    assert report["comparable_days"] == 3
    assert report["spearman"] == 1.0
    assert report["bands_in_order"] is True
    assert report["mismatches"] == []
    assert [row["verdict"] for row in report["rows"]] == [calibration.VERDICT_IN_LINE] * 3


def test_a_day_played_much_harder_than_predicted_is_flagged():
    docs = [
        _day("2026-01-01", "a", 5, "easy", solved=0),  # prevista la piu' facile, nessuno l'ha indovinata
        _day("2026-01-02", "b", 40, "medium", solved=12),
        _day("2026-01-03", "c", 90, "impossible", solved=6),
    ]
    report = _report(docs, min_players=10, mismatch_tolerance=25)
    flagged = {row["day"]: row["verdict"] for row in report["mismatches"]}
    assert flagged["2026-01-01"] == calibration.VERDICT_HARDER
    assert report["mismatches"][0]["day"] == "2026-01-01"  # lo scarto piu' grande per primo
    assert report["bands_in_order"] is False


def test_days_with_too_few_players_stay_in_the_list_but_out_of_the_comparison():
    docs = [
        _day("2026-01-01", "a", 10, "easy", solved=18),
        _day("2026-01-02", "b", 40, "medium", solved=1, players=3),
    ]
    report = _report(docs, min_players=10)
    assert report["days"] == 2
    assert report["comparable_days"] == 1
    assert report["rows"][1]["verdict"] is None


def test_the_report_counts_predictions_per_tuning_and_signals_per_group():
    docs = [
        _day("2026-01-01", "a", 10, "easy", solved=18, model="vecchia"),
        _day("2026-01-02", "b", 40, "medium", solved=12, model="nuova"),
        _day("2026-01-03", "c", 90, "impossible", solved=2, model="nuova"),
        {"day": "2026-01-04", "player_id": "sparito", "players_count": 30, "solved_count": 3},
    ]
    report = _report(docs, min_players=10)
    assert report["models"] == {"vecchia": 1, "nuova": 2}
    assert report["snapshot_days"] == 3
    assert report["current_model"] == model_fingerprint(_config())
    # un giocatore rimosso dal dataset, senza foto della previsione, non e' confrontabile
    assert report["rows"][3]["predicted"] is None
    assert {entry["group"] for entry in report["by_signal"]["fine carriera"]} == {
        "6-15 anni fa", "in attività", "> 15 anni fa",
    }
    assert {entry["group"] for entry in report["by_signal"]["campionati"]} == {"solo top 5", "poco noti (> 0.5)"}


def test_load_report_reads_only_closed_days(monkeypatch):
    calls = []
    monkeypatch.setattr(
        calibration.firebase_service, "get_daily_paths_range",
        lambda start, end, limit=180: calls.append((start, end, limit)) or [],
    )
    report = calibration.load_report(30, today="2026-03-31")
    assert calls == [("2026-03-01", "2026-03-30", 30)]
    assert report["days"] == 0 and report["spearman"] is None


# ---------------------------------------------------------------------------
# Contatori su Firestore
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("solved, kwargs, expected", [
    (None, {}, {"players_count": 1}),
    (True, {"attempts": 2, "hints": 1}, {"solved_count": 1, "solved_attempts_total": 2, "solved_hints_total": 1}),
    (True, {"attempts": 3, "hints": 0}, {"solved_count": 1, "solved_attempts_total": 3, "solved_hints_total": 0}),
    (True, {}, {"solved_count": 1}),
])
def test_register_daily_outcome_increments_the_observed_counters(monkeypatch, solved, kwargs, expected):
    from services import firebase_service
    from services.repos import challenges

    written = {}

    class Ref:
        def update(self, fields):
            written.update(fields)

    monkeypatch.setattr(firebase_service, "daily_path_ref", lambda day: Ref())
    challenges.register_daily_outcome("2026-01-01", solved=solved, **kwargs)
    assert set(written) == set(expected)
    for field, value in expected.items():
        assert isinstance(written[field], firestore.Increment)
        assert written[field].value == value
