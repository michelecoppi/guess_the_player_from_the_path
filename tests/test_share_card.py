"""La figurina del risultato: quello che deve mostrare e, soprattutto, quello che non deve."""
import pytest
from PIL import Image

from services import path_image, share, shop


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
