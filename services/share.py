"""Card del risultato da condividere.

E' il pezzo che porta gente nuova senza spendere niente: un risultato che si incolla in un
gruppo, senza mai rivelare la risposta. Da qui la scelta dei quadratini al posto del testo
("preso al secondo tentativo" direbbe quanto era facile, e in un gruppo dove qualcuno non
ha ancora giocato conta).

Il bottone e' un normale link a `t.me/share/url`, non la modalita' inline: cosi' funziona
anche con la inline mode del bot disattivata.
"""
from urllib.parse import quote

from config import BOT_USERNAME
from services import shop
from services.i18n import t
from services.path_image import render_share_card

CORRECT = "🟩"
WRONG = "🟥"
UNUSED = "⬜"
# Un indizio chiesto = una lampadina. Come i quadratini, e' un segno e non una parola:
# nella card non c'e' niente da tradurre.
HINT = "💡"


def result_squares(attempts_used, max_attempts, solved=True, symbols=None):
    """Un quadratino per tentativo: rossi quelli sbagliati, verde quello giusto, bianchi
    quelli non usati.

    `symbols` e' la terna (giusto, sbagliato, non usato) comprata in negozio: cambia i segni,
    non cosa vogliono dire. La lunghezza si conta in **caratteri**, non in emoji: un simbolo
    composto (💚, ❤️) puo' valere piu' di un carattere, quindi le caselle vuote si contano
    sui tentativi rimasti e non su `len()` della stringa - altrimenti una card con i cuori
    uscirebbe piu' corta di una con i quadratini."""
    correct, wrong_symbol, unused = symbols or (CORRECT, WRONG, UNUSED)
    attempts_used = max(0, min(attempts_used, max_attempts))
    wrong = max(attempts_used - 1 if solved else attempts_used, 0)
    filled = wrong + (1 if solved else 0)
    return wrong_symbol * wrong + (correct if solved else "") + unused * (max_attempts - filled)


def bot_link():
    return f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""


def share_text(lang, number, attempts_used, max_attempts, solved=True, streak=0, archive=False,
               hints=0, symbols=None):
    """`archive=True` marca il risultato come recuperato dall'archivio: il numero della
    sfida basterebbe a distinguerlo da quella di oggi, ma in un gruppo dove la sfida di
    oggi e' ancora aperta la riga va letta al volo, non confrontata con un calendario.

    `hints` aggiunge una lampadina per indizio chiesto. Non e' una punizione: e' quello che
    rende confrontabili due righe uguali. Senza, "1/3" di chi si e' fatto dire nazionalita' e
    ruolo e "1/3" di chi l'ha preso al buio si leggono allo stesso modo, e il gruppo non ha
    modo di accorgersene.

    La percentuale di chi ha indovinato resta fuori di proposito (services/daily_stats.py):
    e' un'informazione sulla difficolta' della sfida, e la card la legge anche chi oggi non
    ha ancora giocato.

    `symbols` sono i quadratini comprati in negozio (services/shop.py). Cambiano l'aspetto e
    basta: il punteggio "2/3" accanto resta, quindi una card con i cuori si confronta con una
    classica senza doverla decifrare."""
    title_key = "share.archive_title" if archive else "share.title"
    lines = [t(lang, title_key, number=number)]

    score = f"{attempts_used}/{max_attempts}" if solved else f"X/{max_attempts}"
    line = f"{result_squares(attempts_used, max_attempts, solved, symbols)} {score}"
    if hints > 0:
        line += "  " + HINT * hints
    if streak >= 2:
        line += "  " + t(lang, "share.streak", streak=streak)
    lines.append(line)

    link = bot_link()
    if link:
        lines.append(link)
    return "\n".join(lines)


def card_image(user, lang, number, attempts_used, max_attempts, solved=True, streak=0,
               hints=0, honour=""):
    """La figurina del risultato: la stessa riga, ma da guardare.

    La riga di testo resta e non se ne va: e' quella che funziona sempre - si incolla ovunque,
    non pesa niente e si legge anche a immagini spente. La figurina e' in piu', ed e' il posto
    dove una finitura comprata in negozio si vede davvero.

    Le parole arrivano gia' tradotte da qui: `render_share_card` disegna e basta."""
    look = shop.appearance(user or {}, lang)
    meta = []
    if streak >= 2:
        meta.append(t(lang, "share.streak", streak=streak))
    if hints > 0:
        meta.append(HINT * hints)
    return render_share_card(
        number, attempts_used, max_attempts, solved=solved,
        name=(user or {}).get("first_name", ""),
        style=look.get("card") or {},
        title=(look.get("title") or {}).get("label", ""),
        shirt=look.get("number", ""),
        honour=honour,
        meta="   ".join(meta),
        footer=bot_link().replace("https://", ""),
    )


def share_url(text):
    """URL del bottone "Condividi". None se non sappiamo qual e' il link del bot: meglio
    nessun bottone che un bottone che porta a una pagina vuota."""
    link = bot_link()
    if not link:
        return None
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"
