"""Shared answer evaluation for bot and mini app events."""
from services.event_config import is_multi_answer
from services.matching import find_match, normalize


def evaluate_event_guess(event_type, guess, today_data):
    """Separata dal resto per poterla testare senza Telegram e senza Firestore.
    Ritorna (corretto, quante risposte azzeccate, totale risposte).

    Il confronto e' lo stesso della sfida giornaliera (services/matching.py): tollera
    accenti e refusi. Per gli eventi "career" si contano le **risposte azzeccate**, non le
    parole scritte: elencare due volte la stessa squadra non fa punteggio."""
    correct_answers = today_data.get("correct_answers", [])

    if not is_multi_answer(event_type):
        return find_match(guess, correct_answers) is not None, None, len(correct_answers)

    matched_answers = set()
    for part in guess.split(","):
        match = find_match(part, correct_answers)
        if match:
            matched_answers.add(normalize(match["answer"]))

    matched = len(matched_answers)
    min_correct = today_data.get("min_correct", len(correct_answers))
    return matched >= min_correct, matched, len(correct_answers)

