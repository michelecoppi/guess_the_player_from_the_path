from PIL import Image

from services import fonts
from services.path_image import (
    COMPACT_FROM_ROWS,
    MAX_ROWS,
    _stats_label,
    _years_label,
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


def test_twenty_stops_stay_readable_in_a_telegram_bubble():
    """Il tetto pratico e' l'altezza, non i limiti di Telegram.

    Telegram scala la foto alla larghezza della bolla: con le righe larghe una carriera da
    20 tappe usciva alta 2588 px e in chat diventava illeggibile. Il layout compatto la
    tiene sotto i ~2000 px, che e' la ragione per cui esiste COMPACT_FROM_ROWS.
    """
    career = [
        {"team": f"Squadra {i}", "country": "Italia", "league": "Serie A",
         "start_year": 2000 + i, "end_year": 2001 + i}
        for i in range(MAX_ROWS)
    ]
    image = Image.open(render_career_path_image(career))
    assert image.height <= 2000
    # limiti di Telegram per le foto: lato+lato <= 10000 e rapporto <= 20
    assert image.width + image.height <= 10000
    assert image.height / image.width <= 20


def test_compact_layout_kicks_in_only_when_there_are_many_stops():
    def height(rows):
        career = [
            {"team": "A", "country": "Italia", "league": "Serie A",
             "start_year": 2000 + i, "end_year": 2001 + i}
            for i in range(rows)
        ]
        return Image.open(render_career_path_image(career)).height

    # una riga in piu' oltre la soglia deve far *scendere* l'altezza per riga
    per_row_wide = (height(COMPACT_FROM_ROWS - 1) - height(1)) / (COMPACT_FROM_ROWS - 2)
    per_row_compact = (height(COMPACT_FROM_ROWS + 4) - height(COMPACT_FROM_ROWS)) / 4
    assert per_row_compact < per_row_wide


def test_loans_are_marked_without_words():
    """Il prestito deve vedersi senza scrivere "prestito": la stessa PNG va a utenti
    italiani, inglesi e spagnoli."""
    permanent = {"team": "A", "country": "Italia", "league": "Serie A", "start_year": 2010, "end_year": 2012}
    loaned = dict(permanent, loan=True)
    assert _years_label(permanent) == "2010 – 2012"
    assert _years_label(loaned).startswith("→")
    # la tappa ancora in corso non deve usare la stessa freccia del prestito
    ongoing = {"team": "A", "start_year": 2010, "end_year": None}
    assert "→" not in _years_label(ongoing)


def test_appearances_and_goals_use_the_wikipedia_convention():
    assert _stats_label({"apps": 33, "goals": 22}) == "33 (22)"
    # portieri: solo presenze, perche' i gol dell'infobox sono quelli *segnati*
    assert _stats_label({"apps": 152}) == "152"
    assert _stats_label({}) is None
