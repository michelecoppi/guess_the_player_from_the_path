"""L'evento padre/figlio e' l'unico costruito a mano: questo test verifica che il documento
prodotto da /admin_event_create sia poi renderizzato correttamente dal centro eventi
(foto della coppia, testo della modalita', nessuna fuga di risposta nella didascalia).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from handlers.events_handler import get_event_home_message, get_today_player_message
from services.dates import to_display
from services.manual_event_service import build_father_son_event, get_template

ITALY_TZ = ZoneInfo("Europe/Rome")


def _today_event():
    template = get_template("coppie_leggendarie")
    pairs = [
        {"id": "p1", "file_id": "AgACAgQAAx0-foto-1", "answers": ["maldini", "paolo e cesare maldini"]},
        {"id": "p2", "file_id": "AgACAgQAAx0-foto-2", "answers": ["maldini junior"]},
    ]
    _, doc, _ = build_father_son_event(pairs, datetime.now(ITALY_TZ), template)
    return doc


def test_today_message_uses_the_photo_sent_by_the_admin():
    event = _today_event()
    message, image = get_today_player_message(event)

    assert image == "AgACAgQAAx0-foto-1"
    assert "padre-figlio" in message.lower()


def test_today_message_does_not_reveal_the_answer():
    event = _today_event()
    message, _ = get_today_player_message(event)

    for answer in event["daily_data"][event["dates"][0]]["correct_answers"]:
        assert answer not in message.lower()


def test_home_message_explains_the_father_son_gameplay():
    event = _today_event()
    message = get_event_home_message(event)

    assert "coppia padre/figlio" in message.lower()
    assert to_display(event["dates"][-1]) in message
