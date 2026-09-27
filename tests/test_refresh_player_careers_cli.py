"""Test della CLI `scripts/refresh_player_careers.py` (nessuna rete: adapter finto)."""

import json

from domains.players.adapters.base import AdapterResult
from scripts import refresh_player_careers as cli


def _player(pid, name, **extra):
    player = {
        "id": pid,
        "full_name": name,
        "aliases": [name.lower()],
        "active": True,
        "source": "wikipedia",
        "source_id": name,
        "career": [
            {"team": "Roma", "country": "Italia", "league": "Serie A", "start_year": 2020, "end_year": None, "apps": 10},
        ],
    }
    player.update(extra)
    return player


class _Adapter:
    def __init__(self):
        self.calls = []

    def fetch_players(self, identifiers):
        self.calls.append(list(identifiers))
        return {
            identifier: AdapterResult(
                source_name="wikipedia",
                source_id=identifier,
                success=True,
                player_name=identifier,
                career=[
                    {"team": "Roma", "start_year": 2020, "end_year": 2026, "apps": 40},
                    {"team": "Juventus", "start_year": 2026, "end_year": None, "apps": 1},
                ],
            )
            for identifier in identifiers
        }


def _setup(tmp_path, monkeypatch, players):
    path = tmp_path / "players.json"
    path.write_text(json.dumps({"players": players}), encoding="utf-8")
    log_path = tmp_path / "logs" / "career_refresh.log"
    monkeypatch.setattr("domains.players.career_refresh._default_log_path", lambda: log_path)
    return path, [
        "--players-path", str(path),
        "--backup-dir", str(tmp_path / "backup"),
        "--failed-out", str(tmp_path / "failed.txt"),
        "--delay", "0",
    ]


def test_find_players_by_id_name_and_accent_insensitive_substring():
    players = [_player("dusan_vlahovic", "Dušan Vlahović"), _player("rafael_leao", "Rafael Leão")]

    assert [p["id"] for p in cli.find_players(players, "rafael_leao")] == ["rafael_leao"]
    assert [p["id"] for p in cli.find_players(players, "Dusan Vlahovic")] == ["dusan_vlahovic"]
    assert [p["id"] for p in cli.find_players(players, "leao")] == ["rafael_leao"]
    assert cli.find_players(players, "nessuno") == []


def test_single_player_refresh_updates_only_that_player(tmp_path, monkeypatch, capsys):
    path, common = _setup(tmp_path, monkeypatch, [_player("a", "Alpha"), _player("b", "Beta")])
    adapter = _Adapter()

    code = cli.main(
        ["--player", "alpha", *common],
        wikipedia_adapter_factory=lambda: adapter,
        club_lookup=lambda team, link: ("Italia", "Serie A"),
    )

    assert code == 0
    assert adapter.calls == [["Alpha"]]
    data = {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))["players"]}
    assert [s["team"] for s in data["a"]["career"]] == ["Roma", "Juventus"]
    assert len(data["b"]["career"]) == 1
    assert "nuova squadra: Juventus" in capsys.readouterr().out


def test_all_dry_run_does_not_write(tmp_path, monkeypatch, capsys):
    players = [_player("a", "Alpha"), _player("b", "Beta"), _player("c", "Gamma", active=False)]
    path, common = _setup(tmp_path, monkeypatch, players)
    before = path.read_text(encoding="utf-8")
    adapter = _Adapter()

    code = cli.main(["--all", "--dry-run", *common], wikipedia_adapter_factory=lambda: adapter)

    assert code == 0
    assert adapter.calls == [["Alpha", "Beta"]]
    assert path.read_text(encoding="utf-8") == before
    assert "2 modificati" in capsys.readouterr().out


def test_ambiguous_player_is_rejected(tmp_path, monkeypatch, capsys):
    _, common = _setup(tmp_path, monkeypatch, [_player("a", "Marco Rossi"), _player("b", "Marco Rossini")])

    code = cli.main(["--player", "marco", *common], wikipedia_adapter_factory=_Adapter)

    assert code == 2
    assert "ambiguo" in capsys.readouterr().err


def test_unresolved_new_team_is_listed_for_manual_completion(tmp_path, monkeypatch, capsys):
    path, common = _setup(tmp_path, monkeypatch, [_player("a", "Alpha")])

    code = cli.main(
        ["--player", "a", *common],
        wikipedia_adapter_factory=_Adapter,
        club_lookup=lambda team, link: (None, None),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "NON aggiunta" in out and "Juventus (2026)" in out
    assert "da completare a mano" in out
    career = json.loads(path.read_text(encoding="utf-8"))["players"][0]["career"]
    assert [s["team"] for s in career] == ["Roma"]
