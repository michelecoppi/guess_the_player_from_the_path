import json

from scripts import import_players


def _dataset(players):
    return {"players": players}


def _valid_player(player_id="nuovo", aliases=None, teams=2):
    career = [
        {"team": f"Club {i}", "country": "Italia", "league": "Serie A", "start_year": 2000 + i * 3, "end_year": 2003 + i * 3}
        for i in range(teams)
    ]
    return {
        "id": player_id,
        "full_name": f"{player_id.title()} Test",
        "aliases": aliases if aliases is not None else [player_id],
        "nationality": "Italia",
        "popularity": 3,
        "career": career,
    }


def _run(tmp_path, monkeypatch, existing, incoming, **kwargs):
    dataset_path = tmp_path / "players.json"
    dataset_path.write_text(json.dumps(_dataset(existing)), encoding="utf-8")
    incoming_path = tmp_path / "incoming.json"
    incoming_path.write_text(json.dumps(_dataset(incoming)), encoding="utf-8")

    monkeypatch.setattr(import_players, "_PLAYERS_PATH", str(dataset_path))
    monkeypatch.setattr(import_players, "reload_dataset", lambda: None)

    result = import_players.import_players([str(incoming_path)], **kwargs)
    written = json.loads(dataset_path.read_text(encoding="utf-8"))
    return result, written["players"]


def test_import_adds_new_players(tmp_path, monkeypatch):
    result, players = _run(tmp_path, monkeypatch, [_valid_player("vecchio")], [_valid_player("nuovo")])

    assert result["added"] == ["nuovo"]
    assert [p["id"] for p in players] == ["vecchio", "nuovo"]


def test_import_normalizes_id_and_aliases(tmp_path, monkeypatch):
    incoming = _valid_player("Nuovo Giocatore", aliases=["  Nuovo  ", "nuovo", "ALTRO"])
    result, players = _run(tmp_path, monkeypatch, [], [incoming])

    assert result["added"] == ["nuovo_giocatore"]
    imported = players[0]
    assert imported["id"] == "nuovo_giocatore"
    assert imported["aliases"] == ["nuovo", "altro"]
    assert imported["verified"] is False  # i nuovi arrivi vanno sempre rivisti a mano


def test_import_skips_existing_ids_unless_update(tmp_path, monkeypatch):
    existing = _valid_player("messi")
    incoming = _valid_player("messi", aliases=["messi", "leo"])

    result, players = _run(tmp_path, monkeypatch, [existing], [incoming])
    assert result["skipped"] == ["messi"]
    assert players[0]["aliases"] == ["messi"]

    result, players = _run(tmp_path, monkeypatch, [existing], [incoming], update=True)
    assert result["updated"] == ["messi"]
    assert players[0]["aliases"] == ["messi", "leo"]


def test_import_rejects_invalid_player(tmp_path, monkeypatch):
    incoming = _valid_player("corto", teams=1)
    result, players = _run(tmp_path, monkeypatch, [], [incoming])

    assert result["added"] == []
    assert players == []
    assert result["rejected"][0][1] == "corto"


def test_import_rejects_alias_already_used_by_another_player(tmp_path, monkeypatch):
    existing = _valid_player("ronaldo_brasile", aliases=["ronaldo"])
    incoming = _valid_player("ronaldo_portogallo", aliases=["ronaldo"])

    result, players = _run(tmp_path, monkeypatch, [existing], [incoming])

    assert result["added"] == []
    assert len(players) == 1
    problems = result["rejected"][0][2]
    assert any("alias ambiguo" in p for p in problems)


def test_import_rejects_two_incoming_players_sharing_an_alias(tmp_path, monkeypatch):
    result, players = _run(
        tmp_path,
        monkeypatch,
        [],
        [_valid_player("primo", aliases=["stesso"]), _valid_player("secondo", aliases=["stesso"])],
    )

    assert result["added"] == ["primo"]
    assert len(result["rejected"]) == 1
    assert len(players) == 1


def test_dry_run_does_not_write(tmp_path, monkeypatch):
    result, players = _run(tmp_path, monkeypatch, [], [_valid_player("nuovo")], dry_run=True)

    assert result["added"] == ["nuovo"]
    assert players == []


def test_force_verified_flag(tmp_path, monkeypatch):
    result, players = _run(tmp_path, monkeypatch, [], [_valid_player("nuovo")], force_verified=True)

    assert result["added"] == ["nuovo"]
    assert players[0]["verified"] is True
