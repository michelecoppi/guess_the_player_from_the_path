"""Test per `domains.players.club_resolution` (nessuna rete)."""

from domains.players.club_resolution import ClubCatalog, club_info_from_params, resolve_club

_PLAYERS = [
    {"career": [
        {"team": "Inter", "country": "Italia", "league": "Serie A"},
        {"team": "Leeds United", "country": "Inghilterra", "league": "Championship"},
        {"team": "Nacional", "country": "Uruguay", "league": "Uruguayan Primera Division"},
        {"team": "Flamengo", "country": "Brasile", "league": "Brasileirao"},
    ]},
]


def test_exact_and_alias_match_use_dataset_names():
    catalog = ClubCatalog(_PLAYERS)
    assert resolve_club("Internazionale", None, catalog) == ("Inter", "Italia", "Serie A", "esatto")
    assert resolve_club("Club X", "Inter", catalog)[3] == "esatto (link)"


def test_manual_table_wins():
    assert resolve_club("Motherwell", None, ClubCatalog(_PLAYERS)) == (
        "Motherwell", "Scozia", "Scottish Premiership", "manuale"
    )


def test_club_page_comes_before_fuzzy_prefix():
    catalog = ClubCatalog(_PLAYERS)
    resolved = resolve_club(
        "Nacional Medellin", None, catalog, lambda team, link: ("Colombia", "Categoria Primera A")
    )
    assert resolved == ("Nacional Medellin", "Colombia", "Categoria Primera A", "pagina del club")


def test_fuzzy_prefix_only_as_last_resort():
    catalog = ClubCatalog(_PLAYERS)
    assert resolve_club("Leeds", None, catalog, lambda t, link: (None, None))[:3] == (
        "Leeds United", "Inghilterra", "Championship"
    )
    assert resolve_club("Sconosciuto", None, catalog, lambda t, link: (None, None)) is None


def test_league_is_normalized_for_the_country_and_dissolved_clubs_rejected():
    catalog = ClubCatalog(_PLAYERS)
    assert resolve_club("Bangu", None, catalog, lambda t, link: ("Brasile", "Serie A"))[2] == "Brasileirao"
    assert resolve_club("Vecchio Club", None, catalog, lambda t, link: ("Italia", "Inattivo")) is None


def test_club_info_from_params():
    assert club_info_from_params("{{ITA}}", "Serie A") == ("Italia", "Serie A")
    assert club_info_from_params("Italia", "Serie A") == (None, "Serie A")


def test_catalog_add_makes_new_clubs_resolvable_offline():
    catalog = ClubCatalog(_PLAYERS)
    catalog.add("Al-Hilal", "Arabia Saudita", "Saudi Pro League")
    assert resolve_club("Al-Hilal", None, catalog)[:3] == ("Al-Hilal", "Arabia Saudita", "Saudi Pro League")
