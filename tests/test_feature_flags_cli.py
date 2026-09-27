"""The operator CLI for feature flags (#51): validation, preview, confirmation, privacy."""
import copy

import pytest
from firebase_admin import firestore

from scripts import feature_flags as cli
from services import feature_flags as ff
from services.repos import feature_flags as repo


class Store:
    """In-memory `admin_settings/feature_flags` applying the same plan as the repository."""

    def __init__(self, raw=None):
        self.raw = copy.deepcopy(raw)
        self.writes = 0

    def load(self):
        return copy.deepcopy(self.raw)

    def update(self, flag, change, *, actor, expected_revision=None, replace_invalid_document=False):
        mode, payload, result = repo.plan_update(self.raw, flag, change, expected_revision=expected_revision,
                                                 replace_invalid_document=replace_invalid_document)
        if mode == "set":
            self.raw = copy.deepcopy(payload)
        else:
            for key, value in payload.items():
                if key.startswith("flags."):
                    flags = self.raw.setdefault("flags", {})
                    if value is firestore.DELETE_FIELD:
                        flags.pop(key.split(".", 1)[1], None)
                    else:
                        flags[key.split(".", 1)[1]] = value
                else:
                    self.raw[key] = value
        self.raw["updated_by"] = repo.clean_actor(actor)
        self.writes += 1
        return result


def run(argv, store, confirm=lambda: True):
    lines = []
    code = cli.main(argv, load=store.load, update=store.update, confirm=confirm, out=lines.append)
    return code, "\n".join(lines)


def test_list_shows_defaults_when_no_document_exists():
    code, output = run(["list"], Store())
    assert code == 0
    assert "missing (all defaults)" in output
    for flag in ff.Flag:
        assert flag.value in output


def test_disable_previews_confirms_and_writes():
    store = Store()
    code, output = run(["disable", "shop", "--actor", "incident-42"], store)
    assert code == 0 and store.writes == 1
    assert "before: no stored rule (repository default: on)" in output
    assert "after:  enabled=OFF" in output
    assert store.raw["flags"]["shop"]["enabled"] is False
    assert store.raw["updated_by"] == "incident-42"


def test_declining_the_confirmation_writes_nothing():
    store = Store()
    code, output = run(["disable", "shop"], store, confirm=lambda: False)
    assert code == cli.EXIT_ABORTED and store.writes == 0 and store.raw is None
    assert "nothing written" in output


def test_a_non_interactive_run_without_yes_writes_nothing(monkeypatch):
    store = Store()
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    lines = []
    code = cli.main(["disable", "arena"], load=store.load, update=store.update, out=lines.append)
    assert code == cli.EXIT_ABORTED and store.writes == 0
    code = cli.main(["disable", "arena", "--yes"], load=store.load, update=store.update, out=lines.append)
    assert code == 0 and store.raw["flags"]["arena"]["enabled"] is False


@pytest.mark.parametrize("argv", [
    ["disable", "shopp"],
    ["rollout", "arena", "150"],
    ["rollout", "arena", "-1"],
    ["allow", "arena", "--user", "abc"],
    ["deny", "arena", "--group", "12a"],
])
def test_invalid_input_is_refused_before_reading_or_writing(argv):
    store = Store()
    store.load = lambda: pytest.fail("must not even read")  # type: ignore[method-assign]
    code, _ = run(argv, store)
    assert code == cli.EXIT_ABORTED and store.writes == 0


def test_targeting_moves_an_id_between_allow_and_deny_and_never_prints_it():
    store = Store()
    code, output = run(["deny", "arena", "--user", "555000111"], store)
    assert code == 0 and store.raw["flags"]["arena"]["deny_users"] == ["555000111"]
    code, output2 = run(["allow", "arena", "--user", "555000111"], store)
    assert store.raw["flags"]["arena"]["allow_users"] == ["555000111"]
    assert store.raw["flags"]["arena"]["deny_users"] == []
    code, output3 = run(["untarget", "arena", "--user", "555000111"], store)
    assert store.raw["flags"]["arena"]["allow_users"] == []
    code, listing = run(["list"], store)
    code, shown = run(["show", "arena"], store)
    for text in (output, output2, output3, listing, shown):
        assert "555000111" not in text


def test_show_targets_is_an_explicit_opt_in():
    store = Store({"schema_version": 1, "revision": 3,
                   "flags": {"leaderboard": {"deny_groups": ["-1001"], "rollout_percentage": 40}}})
    _, hidden = run(["show", "leaderboard"], store)
    _, revealed = run(["show", "leaderboard", "--show-targets"], store)
    assert "-1001" not in hidden and "rollout=40%" in hidden
    assert "deny_groups: -1001" in revealed


def test_rollout_and_reset():
    store = Store()
    run(["rollout", "events_v2", "25"], store)
    assert store.raw["flags"]["events_v2"]["rollout_percentage"] == 25
    code, output = run(["reset", "events_v2"], store)
    assert code == 0 and "events_v2" not in store.raw["flags"] and store.raw["revision"] == 2


def test_a_stale_expected_revision_is_refused():
    store = Store({"schema_version": 1, "revision": 5, "flags": {}})
    code, output = run(["disable", "hints", "--expected-revision", "4"], store)
    assert code == cli.EXIT_ERROR and "revision changed" in output and store.writes == 0


def test_an_invalid_document_is_reported_and_only_replaced_on_request():
    store = Store({"schema_version": 3, "flags": {"shop": {"enabled": False}}})
    code, output = run(["list"], store)
    assert code == cli.EXIT_ERROR and "INVALID" in output
    code, output = run(["disable", "shop"], store)
    assert code == cli.EXIT_ERROR and store.writes == 0
    code, output = run(["disable", "shop", "--replace-invalid-document"], store)
    assert code == 0 and store.raw["schema_version"] == 1 and store.raw["flags"]["shop"]["enabled"] is False


def test_the_cli_reports_when_someone_changed_the_document_meanwhile():
    store = Store({"schema_version": 1, "revision": 1, "flags": {}})

    def confirm():
        store.update(ff.Flag.ARENA, lambda rule: ff.change_rollout(rule, 10), actor="other")
        return True

    code, output = run(["disable", "shop"], store, confirm=confirm)
    assert code == 0 and "changed meanwhile" in output
    assert store.raw["flags"]["arena"]["rollout_percentage"] == 10
    assert store.raw["flags"]["shop"]["enabled"] is False and store.raw["revision"] == 3
