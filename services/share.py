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
from services.i18n import t

CORRECT = "🟩"
WRONG = "🟥"
UNUSED = "⬜"


def result_squares(attempts_used, max_attempts, solved=True):
    """Un quadratino per tentativo: rossi quelli sbagliati, verde quello giusto, bianchi
    quelli non usati."""
    attempts_used = max(0, min(attempts_used, max_attempts))
    wrong = attempts_used - 1 if solved else attempts_used
    squares = WRONG * max(wrong, 0)
    if solved:
        squares += CORRECT
    return squares + UNUSED * (max_attempts - len(squares))


def bot_link():
    return f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""


def share_text(lang, number, attempts_used, max_attempts, solved=True, streak=0, archive=False):
    """`archive=True` marca il risultato come recuperato dall'archivio: il numero della
    sfida basterebbe a distinguerlo da quella di oggi, ma in un gruppo dove la sfida di
    oggi e' ancora aperta la riga va letta al volo, non confrontata con un calendario."""
    title_key = "share.archive_title" if archive else "share.title"
    lines = [t(lang, title_key, number=number)]

    score = f"{attempts_used}/{max_attempts}" if solved else f"X/{max_attempts}"
    line = f"{result_squares(attempts_used, max_attempts, solved)} {score}"
    if streak >= 2:
        line += "  " + t(lang, "share.streak", streak=streak)
    lines.append(line)

    link = bot_link()
    if link:
        lines.append(link)
    return "\n".join(lines)


def share_url(text):
    """URL del bottone "Condividi". None se non sappiamo qual e' il link del bot: meglio
    nessun bottone che un bottone che porta a una pagina vuota."""
    link = bot_link()
    if not link:
        return None
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"
