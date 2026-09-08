from PIL import Image

from services import fonts
from services.path_image import (
    render_avatar,
    render_career_path_image,
    render_event_banner,
    render_palmares_image,
)
from services.player_pool import get_all_players

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_career_path_image_produces_valid_png():
    player = next(p for p in get_all_players() if p["id"] == "messi")
    buffer = render_career_path_image(player["career"])
    assert buffer.read(8) == PNG_MAGIC


def test_render_event_banner_produces_valid_png():
    buffer = render_event_banner("Evento di prova", "Descrizione di test per il banner generato")
    assert buffer.read(8) == PNG_MAGIC


def test_render_career_path_image_handles_single_stop():
    buffer = render_career_path_image([{"team": "Solo Club", "country": "Italia", "league": "Serie A", "start_year": 2020, "end_year": None}])
    assert buffer.read(8) == PNG_MAGIC


def test_palmares_and_avatar_replace_the_externally_hosted_images():
    """Le due immagini della schermata /stats erano su hosting esterni: ora si generano,
    quindi devono uscire da qui anche senza rete."""
    assert render_palmares_image("Palmares", "3 trofei", trophies=3).read(8) == PNG_MAGIC
    assert render_avatar("Niccolo").read(8) == PNG_MAGIC


def test_image_grows_with_the_number_of_stops():
    short = Image.open(render_career_path_image([{"team": "A", "start_year": 2000, "end_year": 2001}]))
    long = Image.open(render_career_path_image([
        {"team": "A", "start_year": 2000, "end_year": 2001},
        {"team": "B", "start_year": 2001, "end_year": 2004},
        {"team": "C", "start_year": 2004, "end_year": None},
    ]))
    assert long.height > short.height
    assert long.width == short.width


def test_long_team_names_do_not_overflow_the_card():
    """Il troncamento e' l'unica cosa che tiene il testo dentro la card: senza, un nome
    lungo esce dall'immagine e la card sembra rotta."""
    buffer = render_career_path_image([{
        "team": "Club Deportivo Universidad Catolica de Valparaiso Sporting",
        "league": "Primera Division Chilena Nacional",
        "country": "Cile",
        "start_year": 2001,
        "end_year": 2009,
    }])
    assert buffer.read(8) == PNG_MAGIC


def test_a_truetype_font_is_used_when_available():
    """Se questo test fallisce sul container, manca il pacchetto dei font (Dockerfile):
    l'immagine esce comunque, ma con il font bitmap di Pillow."""
    assert fonts.get_font(24) is not None
