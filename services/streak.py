"""Striscia di giorni consecutivi indovinati.

E' la regola che fa tornare la gente il giorno dopo, e costa quasi niente: il documento
utente porta gia' il giorno dell'ultima partita, qui si aggiungono il giorno dell'ultima
risposta **giusta** e due contatori.

Le regole stanno qui, da sole e senza Firestore intorno, per due motivi: si leggono in
dieci righe e si testano senza database.
"""
from services.dates import normalize_day, shift_iso

# Punti in piu' al raggiungimento della soglia, dal piu' alto al piu' basso.
# Il tetto e' basso di proposito: la striscia deve premiare la costanza, non diventare il
# modo principale di fare punti (una sfida difficile ne vale 4).
STREAK_BONUS_THRESHOLDS = ((30, 3), (7, 2), (3, 1))


def next_streak(last_correct_day, day_iso, current_streak):
    """La striscia dopo una risposta giusta il giorno `day_iso`.

    - stesso giorno: resta com'e' (non si contano due volte);
    - giorno dopo l'ultimo indovinato: +1;
    - qualsiasi altro caso (salto di un giorno, primo giorno, dato mancante): riparte da 1.
    """
    previous = normalize_day(last_correct_day)
    current = current_streak or 0

    if previous == day_iso:
        return max(current, 1)
    if previous == shift_iso(day_iso, -1):
        return current + 1
    return 1


def streak_bonus(streak):
    """Punti bonus per la striscia raggiunta."""
    for threshold, bonus in STREAK_BONUS_THRESHOLDS:
        if streak >= threshold:
            return bonus
    return 0


def next_threshold(streak):
    """La prossima soglia utile, per dire all'utente quanto gli manca. None se e' al massimo."""
    thresholds = sorted(threshold for threshold, _ in STREAK_BONUS_THRESHOLDS)
    for threshold in thresholds:
        if streak < threshold:
            return threshold
    return None
