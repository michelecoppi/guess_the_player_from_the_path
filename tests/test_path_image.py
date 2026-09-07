from services.path_image import render_career_path_image, render_event_banner
from services.player_pool import get_all_players


def test_render_career_path_image_produces_valid_png():
    player = next(p for p in get_all_players() if p["id"] == "messi")
    buffer = render_career_path_image(player["career"])
    header = buffer.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_render_event_banner_produces_valid_png():
    buffer = render_event_banner("Evento di prova", "Descrizione di test per il banner generato")
    header = buffer.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_render_career_path_image_handles_single_stop():
    buffer = render_career_path_image([{"team": "Solo Club", "country": "Italia", "league": "Serie A", "start_year": 2020, "end_year": None}])
    header = buffer.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"
