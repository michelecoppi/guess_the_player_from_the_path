"""Il planner delle sfide giornaliere (#30): regole, allentamenti, audit, scrittura."""
import pytest
from firebase_admin import firestore

from services import daily_planner as planner
from services.dates import shift_iso
from services.difficulty import DIFFICULTY_ORDER
from services.player_pool import load_config
from tests import planner_fakes

TODAY = "2026-05-01"
START = "2026-05-02"


def _config(**planner_settings):
    config = dict(load_config())
    config["history_days_no_repeat"] = planner_settings.pop("player_cooldown_days", 60)
    config["difficulty_rotation"] = list(DIFFICULTY_ORDER)
    config["daily_planner"] = dict(planner.DEFAULT_SETTINGS, **planner_settings)
    return config


def _candidate(player_id, band, clubs=("Club " + "x",), nationality="Italia"):
    return {
        "player": {"id": player_id},
        "id": player_id,
        "band": band,
        "clubs": set(clubs),
        "nationality": nationality,
    }


def _varied_pool(per_band=20):
    """Candidati tutti diversi per club e nazionalita': nessuna regola di diversita' morde."""
    return [
        _candidate(f"{band}_{i}", band, clubs=(f"club_{band}_{i}",), nationality=f"paese_{band}_{i}")
        for band in DIFFICULTY_ORDER
        for i in range(per_band)
    ]


def _plan(pool, days=20, docs=(), config=None, **kwargs):
    return planner.build_plan(START, days, list(docs), pool, TODAY, config=config or _config(), **kwargs)


# ---------------------------------------------------------------------------
# Regole
# ---------------------------------------------------------------------------

def test_the_plan_is_deterministic_and_a_variant_changes_only_that_day():
    pool = _varied_pool()
    first, second = _plan(pool), _plan(pool)
    assert [r["player_id"] for r in first["days"]] == [r["player_id"] for r in second["days"]]

    day = shift_iso(START, 5)
    varied = _plan(pool, variants={day: 1})
    changed = [a["day"] for a, b in zip(first["days"], varied["days"]) if a["player_id"] != b["player_id"]]
    assert day in changed
    assert varied["days"][5]["audit"]["variant"] == 1


def test_with_enough_candidates_every_day_follows_the_rotation_without_relaxing():
    plan = _plan(_varied_pool(), days=40)
    for row in plan["days"]:
        assert row["band"] == planner.target_band(row["day"], _config())
        assert row["audit"]["relaxed"] == []
    assert plan["summary"]["repeated_players"] == []
    assert plan["summary"]["relaxed"] == {}


def test_a_player_is_not_repeated_within_the_cooldown_in_either_direction():
    pool = _varied_pool(per_band=3)
    fixed_later = {"day": shift_iso(START, 10), "player_id": "easy_0", "difficulty": "easy",
                   "career_path": [], "source": "manual"}
    plan = _plan(pool, days=8, docs=[fixed_later], config=_config(player_cooldown_days=30))
    assert "easy_0" not in {row["player_id"] for row in plan["days"]}


def test_clubs_and_nationalities_are_not_repeated_between_neighbouring_days():
    plan = _plan(_varied_pool(), days=30)
    rows = plan["days"]
    config = _config()
    club_gap = config["daily_planner"]["club_cooldown_days"]
    nationality_gap = config["daily_planner"]["nationality_cooldown_days"]
    pool = {c["id"]: c for c in _varied_pool()}
    for i, row in enumerate(rows):
        for j in range(max(0, i - club_gap), i):
            assert not pool[row["player_id"]]["clubs"] & pool[rows[j]["player_id"]]["clubs"]
        for j in range(max(0, i - nationality_gap), i):
            assert pool[row["player_id"]]["nationality"] != pool[rows[j]["player_id"]]["nationality"]


def test_when_diversity_is_impossible_it_is_relaxed_and_written_in_the_audit():
    # Tutti italiani e tutti della Juventus: la diversita' non si puo' rispettare.
    pool = [_candidate(f"{band}_{i}", band, clubs=("Juventus",), nationality="Italia")
            for band in DIFFICULTY_ORDER for i in range(5)]
    plan = _plan(pool, days=6)
    later = plan["days"][1:]
    assert all(planner.RELAX_CLUB in row["audit"]["relaxed"] for row in later)
    assert all(planner.RELAX_NATIONALITY in row["audit"]["relaxed"] for row in later)
    assert plan["summary"]["relaxed"][planner.RELAX_CLUB] == len(later)
    # la fascia resta quella della rotazione: si allenta la diversita', non la difficolta'
    assert all(row["band"] == row["audit"]["target_band"] for row in plan["days"])


def test_an_empty_band_falls_back_without_exceeding_the_streak_limit():
    pool = [c for c in _varied_pool() if c["band"] != "impossible"]
    plan = _plan(pool, days=24, config=_config(max_same_band_streak=1))
    assert plan["summary"]["longest_band_streak"] <= 1
    fallbacks = [row for row in plan["days"] if row["audit"]["target_band"] == "impossible"]
    assert fallbacks and all(planner.RELAX_BAND in row["audit"]["relaxed"] for row in fallbacks)
    assert all(row["band"] != "impossible" for row in plan["days"])


def test_a_tiny_pool_repeats_a_player_rather_than_leaving_a_hole():
    pool = [_candidate("solo", "easy")]
    plan = _plan(pool, days=3)
    assert [row["player_id"] for row in plan["days"]] == ["solo"] * 3
    assert planner.RELAX_PLAYER in plan["days"][1]["audit"]["relaxed"]
    assert plan["summary"]["repeated_players"] == ["solo"]


def test_excluded_players_are_skipped_until_the_exclusion_expires():
    pool = [_candidate("a", "easy"), _candidate("b", "easy", clubs=("altro",), nationality="Francia")]
    config = _config(max_same_band_streak=10, player_cooldown_days=0, club_cooldown_days=0,
                     nationality_cooldown_days=0)
    config["difficulty_rotation"] = ["easy"]
    exclusions = {"a": {"until": shift_iso(START, 1)}}
    plan = _plan(pool, days=4, config=config, exclusions=exclusions)
    ids = [row["player_id"] for row in plan["days"]]
    assert ids[:2] == ["b", "b"]
    assert "a" not in ids[:2]
    assert planner.exclusion_active({"until": None}, "2099-01-01")
    assert not planner.exclusion_active({"until": "2026-01-01"}, "2026-01-02")


def test_no_eligible_player_is_a_readable_error():
    with pytest.raises(planner.PlannerError):
        _plan([_candidate("a", "easy")], days=1, exclusions={"a": {"until": None}})


def test_the_horizon_is_bounded_and_the_mode_validated():
    with pytest.raises(planner.PlannerError):
        _plan(_varied_pool(), days=planner.MAX_HORIZON_DAYS + 1)
    with pytest.raises(planner.PlannerError):
        _plan(_varied_pool(), days=5, mode="tutto")


# ---------------------------------------------------------------------------
# Cosa resta e cosa cambia
# ---------------------------------------------------------------------------

def _doc(day, player_id="easy_0", band="easy", **fields):
    return dict({"day": day, "player_id": player_id, "difficulty": band, "career_path": [], "source": "auto"}, **fields)


def test_fill_mode_keeps_every_existing_day():
    docs = [_doc(shift_iso(START, 1))]
    plan = _plan(_varied_pool(), days=3, docs=docs)
    assert [(r["action"], r["reason"]) for r in plan["days"]] == [
        (planner.ACTION_CREATE, None), (planner.ACTION_KEEP, planner.KEEP_EXISTING), (planner.ACTION_CREATE, None),
    ]


def test_replan_replaces_only_future_unlocked_automatic_days():
    docs = [
        _doc(TODAY),
        _doc(START, locked=True),
        _doc(shift_iso(START, 1), "medium_0", "medium", source="manual"),
        _doc(shift_iso(START, 2), "hard_0", "hard"),
    ]
    plan = planner.build_plan(TODAY, 4, docs, _varied_pool(), TODAY, config=_config(), mode=planner.MODE_REPLAN)
    assert [(r["action"], r["reason"]) for r in plan["days"]] == [
        (planner.ACTION_KEEP, planner.KEEP_IN_PLAY),
        (planner.ACTION_KEEP, planner.KEEP_LOCKED),
        (planner.ACTION_KEEP, planner.KEEP_MANUAL),
        (planner.ACTION_REPLACE, None),
    ]
    assert plan["days"][3]["previous_player_id"] == "hard_0"


def test_a_day_being_replaced_does_not_constrain_its_neighbours():
    """In ripianificazione il giocatore attuale di un giorno che verra' riscritto e' libero."""
    pool = [_candidate("unico", "easy")] + [c for c in _varied_pool() if c["band"] != "easy"]
    config = _config()
    config["difficulty_rotation"] = ["easy"]
    config["daily_planner"]["max_same_band_streak"] = 10
    docs = [_doc(shift_iso(START, 1), "unico", "easy")]
    plan = _plan(pool, days=1, docs=docs, config=config)
    assert plan["days"][0]["player_id"] != "unico"  # in fill il giorno dopo resta e vincola
    replan = _plan(pool, days=2, docs=docs, config=config, mode=planner.MODE_REPLAN)
    assert replan["days"][0]["player_id"] == "unico"
    assert planner.RELAX_PLAYER not in replan["days"][0]["audit"]["relaxed"]


def test_a_past_day_without_challenge_is_reported_not_created():
    plan = planner.build_plan(shift_iso(TODAY, -1), 2, [], _varied_pool(), TODAY, config=_config())
    assert plan["days"][0]["action"] == planner.ACTION_KEEP
    assert plan["summary"]["missing_days"] == [shift_iso(TODAY, -1)]
    assert plan["days"][1]["action"] == planner.ACTION_CREATE


# ---------------------------------------------------------------------------
# Scrittura, con il dataset vero e un Firestore finto
# ---------------------------------------------------------------------------

@pytest.fixture
def store(monkeypatch):
    return planner_fakes.install(monkeypatch)


def test_apply_writes_the_challenges_with_their_audit(store):
    plan = planner.plan_calendar(days=5, start_day=START, today=TODAY)
    result = planner.apply_plan(plan)
    assert [row["day"] for row in result["written"]] == [shift_iso(START, i) for i in range(5)]
    doc = store.daily[START]
    assert doc["source"] == planner.SOURCE_PLANNER
    assert doc["planner_audit"]["mode"] == planner.MODE_FILL
    assert doc["planner_audit"]["target_band"] in DIFFICULTY_ORDER
    assert doc["difficulty"] == plan["days"][0]["band"]
    assert doc["difficulty_prediction"]["band"] == doc["difficulty"]
    # ricalcolato dopo la scrittura, il calendario non ha piu' niente da fare
    again = planner.plan_calendar(days=5, start_day=START, today=TODAY)
    assert again["summary"]["actions"][planner.ACTION_KEEP] == 5


def test_apply_skips_days_changed_between_preview_and_click(store):
    store.save_daily_path(shift_iso(START, 3), {"player_id": "messi", "difficulty": "easy", "career_path": []})
    plan = planner.plan_calendar(days=4, start_day=START, today=TODAY, mode=planner.MODE_REPLAN)
    # nel frattempo: un giorno creato, uno bloccato, uno cambiato
    store.save_daily_path(START, {"player_id": "totti", "difficulty": "easy", "career_path": []})
    store.save_daily_path(shift_iso(START, 1), {"player_id": "totti", "difficulty": "easy", "career_path": [], "locked": True})
    store.daily[shift_iso(START, 3)]["player_id"] = "totti"

    result = planner.apply_plan(plan)
    skipped = {row["day"]: row["reason"] for row in result["skipped"]}
    assert skipped == {
        START: "creata nel frattempo",
        shift_iso(START, 1): "bloccata nel frattempo",
        shift_iso(START, 3): "modificata nel frattempo",
    }
    assert [row["day"] for row in result["written"]] == [shift_iso(START, 2)]


def test_replacing_a_day_keeps_its_lock_state_and_the_assigned_bonus(store):
    store.save_daily_path(START, {"player_id": "messi", "difficulty": "easy", "career_path": [],
                                  "first_correct_user": True})
    plan = planner.plan_calendar(days=1, start_day=START, today=TODAY, mode=planner.MODE_REPLAN)
    planner.apply_plan(plan)
    assert store.daily[START]["first_correct_user"] is True
    assert store.daily[START]["locked"] is False


def test_choose_single_day_avoids_the_current_player_and_respects_both_sides(store):
    first, _, _ = planner.choose_single_day(START, today=TODAY)
    store.save_daily_path(shift_iso(START, 2), {"player_id": first["id"], "difficulty": "easy", "career_path": []})
    other, band, audit = planner.choose_single_day(START, today=TODAY)
    assert other["id"] != first["id"]
    assert band in DIFFICULTY_ORDER and audit["pool"] > 0


def test_blocked_players_never_enter_the_pool(store):
    plan = planner.plan_calendar(days=3, start_day=START, today=TODAY)
    store.blocked = [row["player_id"] for row in plan["days"]]
    replanned = planner.plan_calendar(days=3, start_day=START, today=TODAY)
    assert not set(store.blocked) & {row["player_id"] for row in replanned["days"]}


def test_exclusions_are_validated_and_stored(store):
    with pytest.raises(planner.PlannerError):
        planner.exclude_player("nessuno_cosi")
    with pytest.raises(planner.PlannerError):
        planner.exclude_player("messi", until="domani")
    assert planner.exclude_player(" Messi ", "in tendenza", "2026-06-30") == "messi"
    assert store.exclusions["messi"]["until"] == "2026-06-30"
    assert store.exclusions["messi"]["reason"] == "in tendenza"
    planner.include_player("messi")
    assert "messi" not in store.exclusions


def test_an_unreadable_exclusion_document_does_not_stop_the_daily(monkeypatch):
    from google.api_core.exceptions import ServiceUnavailable

    def fail():
        raise ServiceUnavailable("giu'")

    monkeypatch.setattr(planner.firebase_service, "get_planner_exclusions", fail)
    assert planner.load_exclusions() == {}


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def test_the_exclusion_repository_merges_and_deletes_single_fields(monkeypatch):
    from services import firebase_service
    from services.repos import admin

    calls = []

    class Snapshot:
        exists = True

        def to_dict(self):
            return {"excluded": {"messi": {"reason": "x"}}}

    class Ref:
        def get(self):
            return Snapshot()

        def set(self, data, merge=False):
            calls.append(("set", data, merge))

        def update(self, data):
            calls.append(("update", data))

    monkeypatch.setattr(admin, "_planner_ref", lambda: Ref())
    assert firebase_service.get_planner_exclusions() == {"messi": {"reason": "x"}}
    admin.set_planner_exclusion("totti", {"reason": "y"})
    admin.remove_planner_exclusion("messi")
    assert calls[0] == ("set", {"excluded": {"totti": {"reason": "y"}}}, True)
    assert calls[1] == ("update", {"excluded.messi": firestore.DELETE_FIELD})
