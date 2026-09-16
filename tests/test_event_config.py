"""Schema dei template evento (#31): il file vero e' valido, e ogni errore tipico e' rifiutato
con un messaggio che dice quale campo correggere."""
import copy
from datetime import date

import pytest

from services import event_config
from services.event_generator import load_payload, load_templates


def _valid(**overrides):
    template = {
        "id": "prova_evento",
        "name": "Prova",
        "description": "Un evento di prova.",
        "name_i18n": {"es": "Prueba", "en": "Test"},
        "description_i18n": {"es": "Un evento de prueba.", "en": "A test event."},
        "type": "path",
        "category": "test",
        "difficulty": "medium",
        "duration_days": 4,
        "filters": {"min_teams": 3},
        "rules": {"attempts": 4},
        "rewards": {"points_per_day": 2, "first_correct_bonus": 0, "podium_trophies": 1},
        "schedule": {"mode": "rotation", "start_weekdays": ["sat"], "window": {"from": "12-01", "to": "01-15"}},
    }
    template.update(overrides)
    return template


def _errors(template):
    return event_config.validate_template(template)


def test_the_repository_templates_are_all_valid():
    payload = load_payload()
    assert event_config.validate_payload(payload) == {}
    assert len(load_templates()) == len(payload["templates"])


def test_a_complete_template_is_valid():
    assert _errors(_valid()) == []


@pytest.mark.parametrize("change, fragment", [
    ({"filters": {"min_team": 6}}, "filters.min_team: filtro sconosciuto"),
    ({"filters": {"min_teams": 0}}, "filters.min_teams"),
    ({"filters": {"max_popularity": 7}}, "filters.max_popularity"),
    ({"filters": {"nationality_in": []}}, "filters.nationality_in"),
    ({"filters": {"leagues_only_top": False}}, "filters.leagues_only_top"),
    ({"filters": {"min_teams": 6, "max_teams": 2}}, "nessun candidato"),
    ({"rules": {"attempts": 0}}, "rules.attempts"),
    ({"rules": {"tries": 3}}, "rules.tries: regola sconosciuta"),
    ({"rules": {"min_correct_ratio": 0.5}}, "rules.min_correct_ratio: vale solo"),
    ({"rewards": {"points_per_day": 50}}, "rewards.points_per_day"),
    ({"rewards": {"podium_trophies": 5}}, "rewards.podium_trophies"),
    ({"rewards": {"xp": 100}}, "rewards.xp: premio sconosciuto"),
    ({"schedule": {"mode": "sometimes"}}, "schedule.mode"),
    ({"schedule": {"mode": "fixed"}}, "schedule.start"),
    ({"schedule": {"mode": "fixed", "start": "01/06/26"}}, "schedule.start"),
    ({"schedule": {"mode": "manual"}}, "schedule.reason"),
    ({"schedule": {"mode": "rotation", "start": "2026-06-01"}}, "schedule.start: non previsto"),
    ({"schedule": {"mode": "rotation", "start_weekdays": ["venerdi"]}}, "schedule.start_weekdays"),
    ({"schedule": {"mode": "rotation", "window": {"from": "13-01", "to": "01-01"}}}, "schedule.window"),
    ({"type": "quiz"}, "type:"),
    ({"difficulty": "extreme"}, "difficulty:"),
    ({"duration_days": 60}, "duration_days"),
    ({"id": "Con Spazi"}, "id:"),
    ({"name": " "}, "name: obbligatorio"),
    ({"name_i18n": {"es": "Prueba"}}, "name_i18n.en: traduzione mancante"),
    ({"colore": "rosso"}, "colore: campo sconosciuto"),
])
def test_typical_mistakes_are_rejected_with_the_field_path(change, fragment):
    errors = _errors(_valid(**change))
    assert any(fragment in error for error in errors), errors


def test_a_missing_schedule_is_an_error_not_a_silent_rotation():
    template = _valid()
    del template["schedule"]
    assert any("schedule: obbligatorio" in error for error in _errors(template))


@pytest.mark.parametrize("legacy_field, value", [
    ("weekend_only", True), ("manual_only", True), ("points_per_day", 2), ("min_correct_ratio", 0.5),
])
def test_schema_v1_fields_point_to_their_v2_replacement(legacy_field, value):
    errors = _errors(_valid(**{legacy_field: value}))
    assert any(error.startswith(f"{legacy_field}: campo dello schema v1") for error in errors), errors


def test_v1_pool_filters_under_rules_are_explained():
    errors = _errors(_valid(rules={"min_teams": 6}))
    assert any("I filtri vanno in 'filters'" in error for error in errors)


def test_types_with_manual_content_must_be_manual_and_have_no_filters():
    errors = _errors(_valid(type="father_son"))
    assert any("serve mode 'manual'" in error for error in errors)
    assert any("non pesca dal dataset" in error for error in errors)
    assert _errors(_valid(type="father_son", filters={}, schedule={"mode": "manual", "reason": "foto"})) == []


def test_the_multi_answer_ratio_is_allowed_only_for_career_events():
    assert _errors(_valid(type="career", rules={"min_correct_ratio": 0.6})) == []


def test_the_payload_needs_the_schema_version_and_unique_ids():
    template = _valid()
    problems = event_config.validate_payload({"templates": [template, copy.deepcopy(template)]})
    assert "schema_version" in problems["file"][0]
    assert any("duplicato" in error for error in problems["prova_evento"])
    assert event_config.validate_payload([]) == {"file": ['serve un oggetto con "templates": [...].']}


def test_resolved_fills_the_defaults_that_used_to_be_constants():
    resolved = event_config.resolved({"type": "career", "schedule": {"mode": "rotation"}})
    assert resolved["rules"] == {"attempts": 3, "min_correct_ratio": 0.5}
    assert resolved["rewards"] == {"points_per_day": 1, "first_correct_bonus": 1, "podium_trophies": 3}
    assert "min_correct_ratio" not in event_config.resolved({"type": "path"})["rules"]


def test_events_created_before_the_schema_keep_the_old_behaviour():
    assert event_config.event_rules({})["attempts"] == 3
    assert event_config.event_rewards({"rewards": {"podium_trophies": 1}}) == {
        "points_per_day": 1, "first_correct_bonus": 1, "podium_trophies": 1,
    }


def test_type_registry_replaces_the_hard_coded_branches():
    assert event_config.answers_with_player("path") and event_config.answers_with_player("transfer_guess")
    assert not event_config.answers_with_player("career") and not event_config.answers_with_player("father_son")
    assert event_config.is_multi_answer("career") and not event_config.is_multi_answer("path")
    assert not event_config.uses_dataset("father_son")
    assert not event_config.answers_with_player("sconosciuto")


@pytest.mark.parametrize("window, day, inside", [
    ({"from": "06-01", "to": "07-20"}, date(2026, 6, 15), True),
    ({"from": "06-01", "to": "07-20"}, date(2026, 8, 1), False),
    ({"from": "12-01", "to": "01-15"}, date(2026, 12, 24), True),   # a cavallo d'anno
    ({"from": "12-01", "to": "01-15"}, date(2027, 1, 10), True),
    ({"from": "12-01", "to": "01-15"}, date(2027, 2, 1), False),
    (None, date(2026, 3, 3), True),
])
def test_recurring_windows(window, day, inside):
    assert event_config.in_window(window, day) is inside


def test_rotation_start_respects_weekdays_window_and_mode():
    template = _valid()
    assert event_config.rotation_allows_start(template, date(2026, 12, 5))       # sabato, in finestra
    assert not event_config.rotation_allows_start(template, date(2026, 12, 6))   # domenica
    assert not event_config.rotation_allows_start(template, date(2026, 11, 28))  # sabato, fuori finestra
    assert not event_config.rotation_allows_start(_valid(schedule={"mode": "manual", "reason": "x"}), date(2026, 12, 5))


def test_schedule_labels():
    assert event_config.schedule_label({"schedule": {"mode": "manual", "reason": "foto"}}) == "manuale — foto"
    assert event_config.schedule_label({"schedule": {"mode": "fixed", "start": "2026-06-01"}}) == "data fissa 2026-06-01"
    assert event_config.schedule_label(_valid()) == "rotazione, parte di sat, dal 12-01 al 01-15"
