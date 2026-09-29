"""La figurina del risultato: quello che deve mostrare e, soprattutto, quello che non deve."""
import pytest
from PIL import Image

from domains.shop import service as shop
from services import path_image, share


def user(card=None, **worn):
    equipped = {"card": card} if card else {}
    equipped.update(worn)
    return {
        "first_name": "Anna",
        "cosmetics": {"owned": [one for one in equipped.values()], "equipped": equipped},
    }


def opened(buffer):
    return Image.open(buffer)


@pytest.mark.parametrize("item", [one for one in shop.items_of_kind("card")])
def test_every_finish_in_the_catalogue_can_actually_be_drawn(item):
    """Una finitura scritta in data/shop.json che il disegno non conosce uscirebbe come una
    card piatta, senza che nessuno se ne accorga fino a quando qualcuno la compra."""
    assert item["style"]["finish"] in path_image.FINISHES
    image = opened(path_image.render_share_card(1, 1, 3, style=item["style"]))
    assert image.size == (path_image.CARD_WIDTH, path_image.CARD_HEIGHT)


def test_a_card_without_a_style_still_comes_out_whole():
    """Uno slot vuoto non deve produrre una figurina mezza disegnata: si ripiega sui colori
    di partenza, che e' sempre meglio di un buco."""
    plain = opened(path_image.render_share_card(12, 2, 3))
    assert plain.size == (path_image.CARD_WIDTH, path_image.CARD_HEIGHT)
    assert plain.getpixel((10, 10)) != (0, 0, 0)


def test_the_card_never_carries_the_answer():
    """La regola della riga di testo vale identica per l'immagine: la si incolla in un gruppo
    dove qualcuno non ha ancora giocato. Qui si controlla il **contratto**: fra i valori che
    entrano nel disegno non c'e' nessun posto dove possa finire un nome di calciatore."""
    import inspect
    signature = inspect.signature(path_image.render_share_card).parameters
    assert "player" not in signature and "answer" not in signature and "solution" not in signature


def test_a_lost_day_draws_no_winning_square():
    won = opened(path_image.render_share_card(1, 2, 3, solved=True,
                                              style=shop.get_item("figurina_classica")["style"]))
    lost = opened(path_image.render_share_card(1, 3, 3, solved=False,
                                               style=shop.get_item("figurina_classica")["style"]))
    glow = (56, 189, 130)
    assert glow in [pixel for _, pixel in won.getcolors(1 << 20)]
    assert glow not in [pixel for _, pixel in lost.getcolors(1 << 20)]


def test_the_card_uses_the_finish_the_user_is_wearing():
    dressed = user(card="figurina_foil")
    assert shop.appearance(dressed, "it")["card"]["finish"] == "foil"
    image = opened(share.card_image(dressed, "it", 7, 2, 3))
    assert image.size == (path_image.CARD_WIDTH, path_image.CARD_HEIGHT)


def test_the_text_line_is_untouched_by_the_card():
    """La figurina si aggiunge, non sostituisce: chi ha le immagini spente deve continuare a
    vedere il suo risultato."""
    line = share.share_text("it", 7, 2, 3, solved=True, streak=4)
    assert "2/3" in line
    assert "\U0001f7e5\U0001f7e9⬜" in line


def _has_colour(image, colour, tolerance=6):
    """I bordi delle icone sono smussati, ma dentro il colore arriva pieno: basta trovarne
    qualche pixel vicino, nella fascia sotto il punteggio."""
    band = image.convert("RGB").crop((0, 540, path_image.CARD_WIDTH, 610))
    return any(all(abs(a - b) <= tolerance for a, b in zip(pixel, colour))
               for _, pixel in band.getcolors(1 << 20))


@pytest.mark.parametrize("streak, hints, flame, bulb", [
    (5, 2, True, True),
    (3, 0, True, False),
    (1, 1, False, True),
    (0, 0, False, False),
])
def test_streak_and_hints_are_drawn_icons_not_emoji(streak, hints, flame, bulb):
    """Il font della figurina non ha le emoji: 🔥 e 💡 uscivano come quadratini vuoti. Ora
    sono una fiamma e una lampadina disegnate, e la serie compare da 2 giorni in su come
    nella riga di testo."""
    image = opened(path_image.render_share_card(9, 2, 3, streak=streak, hints=hints))
    assert _has_colour(image, path_image.FLAME_OUTER) is flame
    assert _has_colour(image, path_image.BULB_GLASS) is bulb


def test_the_card_takes_numbers_not_emoji_text():
    """Non c'e' piu' un parametro dove far passare una stringa con le emoji dentro."""
    import inspect
    signature = inspect.signature(path_image.render_share_card).parameters
    assert "meta" not in signature
    assert {"streak", "hints"} <= set(signature)


def test_card_image_hands_streak_and_hints_to_the_drawing(monkeypatch):
    seen = {}
    monkeypatch.setattr(share, "render_share_card", lambda *args, **kwargs: seen.update(kwargs))
    share.card_image(user(), "it", 7, 2, 3, streak=4, hints=2)
    assert seen["streak"] == 4 and seen["hints"] == 2
