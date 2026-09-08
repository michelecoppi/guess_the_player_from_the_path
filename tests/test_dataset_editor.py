import json

import pytest

from services import dataset_editor, player_pool
from services.dataset_editor import DatasetEditError

CONFIG = {
    "min_teams_in_career": 2,
    "top_leagues": ["Serie A", "Premier League"],
    "known_leagues": ["Eredivisie"],
    "difficulty_thresholds": {"easy": 5, "medium": 9, "hard": 13},
    "difficulty_weights": {"popularity": 4.0, "minor_leagues": 3.0, "extra_countries": 0.5, "extra_teams": 0.2},
}


def _player(player_id="tizio", popularity=3, leagues=("Serie A", "Serie A"), **extra):
    career = [
        {
            "team": f"Club {i}",
            "country": "Italia",
            "league": league,
            "start_year": 2000 + i * 3,
            "end_year": 2003 + i * 3,
        }
        for i, league in enumerate(leagues)
    ]
    player = {
        "id": player_id,
        "full_name": player_id.title(),
        "aliases": [player_id],
        "nationality": "Italia",
        "popularity": popularity,
        "verified": True,
        "career": career,
    }
    player.update(extra)
    return player


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Dataset e config finti: le funzioni qui sotto **scrivono su disco**, e devono farlo
    su una copia usa e getta, non su data/players.json."""
    players_path = tmp_path / "players.json"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    backup_dir = tmp_path / "backup"

    monkeypatch.setattr(player_pool, "_PLAYERS_PATH", str(players_path))
    monkeypatch.setattr(player_pool, "_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(dataset_editor, "_PLAYERS_PATH", str(players_path))
    monkeypatch.setattr(dataset_editor, "_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(dataset_editor, "BACKUP_DIR", str(backup_dir))

    def write(players, comment="dataset di prova"):
        players_path.write_text(
            json.dumps({"_comment": comment, "players": players}, ensure_ascii=False), encoding="utf-8"
        )
        player_pool.reload_dataset()

    def read():
        return json.loads(players_path.read_text(encoding="utf-8"))

    write([_player()])
    yield type("Dataset", (), {"write": staticmethod(write), "read": staticmethod(read), "path": players_path,
                               "config_path": config_path, "backup_dir": backup_dir})
    player_pool.reload_dataset()


def test_list_players_shows_every_card_with_its_status(dataset):
    dataset.write([
        _player("selezionabile"),
        _player("da_rivedere", verified=False),
        _player("allenamento", practice_only=True),
        _player("rotto", leagues=("Serie A",)),
    ])

    by_id = {row["id"]: row for row in dataset_editor.list_players(blocked_ids=["selezionabile"])}

    assert by_id["selezionabile"]["status"] == dataset_editor.STATUS_BLOCKED
    assert by_id["da_rivedere"]["status"] == dataset_editor.STATUS_UNVERIFIED
    assert by_id["allenamento"]["status"] == dataset_editor.STATUS_PRACTICE
    assert by_id["rotto"]["status"] == dataset_editor.STATUS_INCOMPLETE
    assert by_id["rotto"]["problems"]


def test_score_is_split_between_fame_and_path(dataset):
    dataset.write([_player("misto", popularity=3, leagues=("Serie A", "J1 League"))])

    row = dataset_editor.list_players()[0]

    assert row["from_popularity"] == 8.0  # (5 - 3) * 4.0
    assert row["from_path"] == pytest.approx(row["score"] - 8.0)


def test_changing_popularity_rewrites_the_dataset_and_clears_the_cache(dataset):
    dataset.write([_player("tizio", popularity=1)])
    assert dataset_editor.list_players()[0]["difficulty"] == "impossible"

    result = dataset_editor.apply_player_changes({"tizio": {"popularity": 4}})

    assert result["changes"] == [{"id": "tizio", "field": "popularity", "before": 1, "after": 4}]
    assert dataset.read()["players"][0]["popularity"] == 4
    # senza reload_dataset() la cache in memoria continuerebbe a dire 'impossible'
    assert dataset_editor.list_players()[0]["difficulty"] == "easy"


def test_saving_keeps_the_comment_and_the_untouched_players(dataset):
    dataset.write([_player("primo"), _player("secondo", popularity=5)], comment="non toccare")

    dataset_editor.apply_player_changes({"primo": {"popularity": 1}})

    written = dataset.read()
    assert written["_comment"] == "non toccare"
    assert [p["id"] for p in written["players"]] == ["primo", "secondo"]
    assert written["players"][1] == _player("secondo", popularity=5)


def test_flags_are_removed_instead_of_written_false(dataset):
    dataset.write([_player("tizio", practice_only=True)])

    dataset_editor.apply_player_changes({"tizio": {"practice_only": False, "verified": False}})

    written = dataset.read()["players"][0]
    assert "practice_only" not in written
    assert written["verified"] is False  # 'verified' sta in tutte le schede: resta scritto


def test_a_backup_is_written_before_touching_the_dataset(dataset):
    dataset.write([_player("tizio", popularity=3)])

    result = dataset_editor.apply_player_changes({"tizio": {"popularity": 5}})

    backup = json.loads(open(result["backup"], encoding="utf-8").read())
    assert backup["players"][0]["popularity"] == 3


def test_career_league_can_be_corrected(dataset):
    dataset.write([_player("tizio", popularity=3, leagues=("Serie A", "Eredivise"))])  # refuso
    before = dataset_editor.list_players()[0]["score"]

    result = dataset_editor.apply_player_changes({}, career_changes={"tizio": {1: "Eredivisie"}})

    assert result["changes"][0]["field"] == "career[2].league"
    assert dataset.read()["players"][0]["career"][1]["league"] == "Eredivisie"
    assert dataset_editor.list_players()[0]["score"] < before


def test_invalid_popularity_is_refused_without_writing(dataset):
    with pytest.raises(DatasetEditError, match="Notorieta'"):
        dataset_editor.apply_player_changes({"tizio": {"popularity": 9}})
    assert dataset.read()["players"][0]["popularity"] == 3
    assert not dataset.backup_dir.exists()


def test_unknown_id_is_refused(dataset):
    with pytest.raises(DatasetEditError, match="Id non presenti"):
        dataset_editor.apply_player_changes({"nessuno": {"popularity": 3}})


def test_saving_without_changes_is_refused(dataset):
    with pytest.raises(DatasetEditError, match="Nessuna modifica"):
        dataset_editor.apply_player_changes({"tizio": {"popularity": 3}})


def test_an_empty_league_is_refused(dataset):
    with pytest.raises(DatasetEditError, match="non puo' essere vuoto"):
        dataset_editor.apply_player_changes({}, career_changes={"tizio": {0: "   "}})
    assert not dataset.backup_dir.exists()


def test_a_change_that_breaks_the_dataset_is_refused(dataset):
    """'one_club_career' su una carriera di due squadre e' una contraddizione: meglio un
    errore che una scheda rotta che sparisce in silenzio dalla selezione automatica."""
    with pytest.raises(DatasetEditError, match="incoerente"):
        dataset_editor.apply_player_changes({"tizio": {"one_club_career": True}})
    assert "one_club_career" not in dataset.read()["players"][0]


def test_existing_problems_do_not_block_a_correction(dataset):
    """Il dataset contiene per costruzione schede da rivedere: correggerne un'altra deve
    restare possibile."""
    dataset.write([_player("rotto", leagues=("Serie A",)), _player("sano", popularity=2)])

    dataset_editor.apply_player_changes({"sano": {"popularity": 4}})

    assert dataset.read()["players"][1]["popularity"] == 4


def test_preview_says_who_changes_bucket_without_saving(dataset):
    dataset.write([_player("tizio", popularity=2)])

    preview = dataset_editor.preview_player_changes({"tizio": {"popularity": 4}})

    assert preview["moves"] == [
        {"id": "tizio", "full_name": "Tizio", "before": "hard", "after": "easy"}
    ]
    assert dataset.read()["players"][0]["popularity"] == 2


def test_settings_preview_counts_the_whole_dataset(dataset):
    dataset.write([_player("a", popularity=5), _player("b", popularity=4), _player("c", popularity=3)])

    preview = dataset_editor.preview_difficulty_settings(
        {"easy": 3, "medium": 7, "hard": 11},
        dataset_editor.difficulty_settings()["weights"],
    )

    assert sum(preview["before"].values()) == 3
    assert preview["before"] != preview["after"]
    assert {move["id"] for move in preview["moves"]} == {"b", "c"}


def test_settings_are_saved_keeping_the_rest_of_the_config(dataset):
    result = dataset_editor.update_difficulty_settings(
        {"easy": 6, "medium": 10, "hard": 14},
        {"popularity": 4.0, "minor_leagues": 2.5, "extra_countries": 0.5, "extra_teams": 0.2},
    )

    written = json.loads(dataset.config_path.read_text(encoding="utf-8"))
    assert written["difficulty_thresholds"] == {"easy": 6, "medium": 10, "hard": 14}
    assert written["difficulty_weights"]["minor_leagues"] == 2.5
    assert written["top_leagues"] == CONFIG["top_leagues"]  # il resto non si tocca
    assert result["backup"]


def test_thresholds_must_grow(dataset):
    with pytest.raises(DatasetEditError, match="devono crescere"):
        dataset_editor.update_difficulty_settings(
            {"easy": 9, "medium": 5, "hard": 13},
            dataset_editor.difficulty_settings()["weights"],
        )


def test_negative_weights_are_refused(dataset):
    with pytest.raises(DatasetEditError, match="negativi"):
        dataset_editor.update_difficulty_settings(
            dataset_editor.difficulty_settings()["thresholds"],
            {"popularity": -1, "minor_leagues": 3.0, "extra_countries": 0.5, "extra_teams": 0.2},
        )


def test_career_weights_show_why_a_stop_costs(dataset):
    dataset.write([_player("tizio", leagues=("Serie A", "Eredivisie", "J1 League"))])
    player = player_pool.get_player_by_id("tizio")

    tiers = [stop["tier"] for stop in dataset_editor.career_with_weights(player)]

    assert tiers == ["top", "noto", "oscuro"]


def test_known_league_names_include_those_already_in_use(dataset):
    dataset.write([_player("tizio", leagues=("Serie A", "J1 League"))])

    names = dataset_editor.known_league_names()

    assert "J1 League" in names  # in uso ma fuori dalle liste di config
    assert "Premier League" in names  # in lista ma non in uso
