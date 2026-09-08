"""Quanti hanno indovinato una giornata, in una riga.

E' l'unico numero del gioco che parla della **sfida** e non del giocatore, ed e' quello che
rende leggibile un risultato: "3/3" da solo non dice se la giornata era dura, "l'ha
indovinato il 12%" si'.

Compare a giornata chiusa (la soluzione e il messaggio di mezzanotte) e mai prima: durante
la giornata la percentuale e' ancora in formazione, e soprattutto direbbe a chi non ha
ancora giocato quanto e' facile la sfida di oggi. Per lo stesso motivo non finisce nella
card da condividere.

I contatori li tiene `firebase_service.register_daily_outcome`.
"""
from services.i18n import t

# Sotto questo numero di giocatori la percentuale non significa niente: con tre partecipanti
# "33%" e' un solo utente, e nella prima ora di una giornata sarebbe sempre un numero
# estremo. Meglio non dire niente che dire una cifra che non regge.
MIN_PLAYERS_FOR_RATE = 5


def solve_percent(players, solved):
    """La percentuale arrotondata all'intero, o None se non c'e' niente da dire."""
    if not players or players < MIN_PLAYERS_FOR_RATE:
        return None
    return round(100 * min(solved, players) / players)


def rate_line(lang, players, solved, unknown_key="solution.rate_unknown"):
    """La riga pronta da mettere nel messaggio.

    `unknown_key=None` per chi preferisce non scrivere niente quando il dato non c'e' (il
    messaggio di mezzanotte, che e' gia' lungo)."""
    percent = solve_percent(players, solved)
    if percent is None:
        return t(lang, unknown_key) if unknown_key else ""
    return t(lang, "solution.rate", percent=percent, solved=solved, players=players)
