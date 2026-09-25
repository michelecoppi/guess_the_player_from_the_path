"""Partita di gruppo: un round alla volta, vince chi risponde per primo.

Non e' la sfida di oggi ripubblicata nel gruppo, ed e' la scelta che regge tutto il resto:
la risposta comparirebbe in chiaro davanti a chi non ha ancora giocato, e brucerebbe la
giornata anche a chi non stava guardando. Il round pesca invece dallo stesso materiale
dell'allenamento (services/practice_content.py): calciatori riservati, che come sfida del
giorno non escono mai, e sfide gia' passate, che sono pubbliche per costruzione.

Le altre tre conseguenze della stessa scelta:

- **i punti restano nel gruppo** (`group_rounds/{chat}/players/{utente}`) e non toccano ne'
  la classifica generale ne' quella del mese: un gruppo creato con un account secondario non
  sposta niente di quello che conta;
- **si risponde con `/guess`**, non a messaggio libero. Leggere i messaggi liberi di un
  gruppo vorrebbe dire spegnere la privacy mode in BotFather, cioe' ricevere *tutti* i
  messaggi di *tutti* i gruppi in cui il bot e' dentro. I comandi arrivano lo stesso;
- **non serve essersi registrati**: in gruppo non c'e' niente da salvare sull'utente, e
  chiedere /start prima di poter giocare toglierebbe alla modalita' l'unica cosa che la
  rende utile, cioe' che chi passa di li' possa rispondere e basta.

Qui stanno le regole, senza Telegram: `handlers/group_handler.py` legge l'update, chiama
queste funzioni e traduce il risultato in un messaggio (#147).
"""
import logging
from dataclasses import dataclass
from typing import Any, Optional

from domains.groups import repository
from services import practice_content
from services.difficulty import points_for_difficulty
from services.guess_feedback import build_comparison
from services.matching import find_match

MAX_GROUP_ATTEMPTS = 3
STANDINGS_SIZE = 10


@dataclass(frozen=True)
class OpenedRound:
    number: int
    difficulty: Optional[str]
    points: int
    career_path: list[dict[str, Any]]


@dataclass(frozen=True)
class AnswerOutcome:
    """Com'e' andato un `/guess` nel gruppo.

    `status` e' uno fra: `no_round` (nessun round aperto), `usage` (manca il nome),
    `already_solved` (`winner` e' il nome di chi l'ha vinto, None se l'ha appena preso
    qualcun altro), `no_attempts`, `wrong` (`attempts_left`, `comparison`), `correct`
    (`points`, `number`)."""
    status: str
    winner: Optional[str] = None
    attempts_left: int = 0
    comparison: Optional[dict[str, Any]] = None
    points: int = 0
    number: int = 0


def open_round(chat_id) -> Optional[OpenedRound]:
    """Apre un round nuovo (e chiude quello in corso). None se non c'e' materiale da giocare."""
    previous = repository.get_group_round(chat_id) or {}
    challenge = practice_content.pick(exclude_keys=previous.get("recent_keys", []))
    if not challenge or not challenge.get("career_path"):
        return None

    round_doc = repository.start_group_round(chat_id, challenge)
    return OpenedRound(
        number=round_doc["number"],
        difficulty=challenge.get("difficulty"),
        points=points_for_difficulty(challenge.get("difficulty")),
        career_path=challenge["career_path"],
    )


def submit_answer(chat_id, user_id, name, answer) -> AnswerOutcome:
    """Un tentativo nel round aperto del gruppo. I controlli che non costano un tentativo
    (nessun round, nome mancante, round gia' vinto) vengono prima di consumarlo."""
    round_doc = repository.get_group_round(chat_id)
    if not round_doc or not round_doc.get("correct_answers"):
        return AnswerOutcome("no_round")

    if not answer:
        return AnswerOutcome("usage")

    if round_doc.get("solved_by"):
        return AnswerOutcome("already_solved", winner=round_doc.get("solved_name"))

    number = round_doc.get("number", 0)
    attempt = repository.begin_group_attempt(chat_id, user_id, number, name, MAX_GROUP_ATTEMPTS)
    if not attempt["ok"]:
        return AnswerOutcome("no_attempts")

    logging.info(f"[GROUP] {chat_id} round {number}: tentativo di {user_id} ({len(answer)} caratteri)")

    if not find_match(answer, round_doc.get("correct_answers", [])):
        return AnswerOutcome(
            "wrong",
            attempts_left=attempt["attempts_left"],
            comparison=build_comparison(answer, round_doc.get("player_id")),
        )

    # Due risposte giuste nello stesso istante, in un gruppo, sono la norma: il round lo
    # prende chi vince la transazione, esattamente come il bonus del primo sulla sfida di
    # oggi.
    if not repository.claim_group_round(chat_id, number, user_id, name):
        return AnswerOutcome("already_solved")

    points = points_for_difficulty(round_doc.get("difficulty"))
    repository.add_group_points(chat_id, user_id, name, points)
    return AnswerOutcome("correct", points=points, number=number)


def standings(chat_id, limit=STANDINGS_SIZE) -> list[dict[str, Any]]:
    """La classifica di questo gruppo, che non c'entra con quella generale: righe con
    `position`, `name`, `points`, `rounds_won`."""
    players = repository.get_group_leaderboard(chat_id, limit=limit)
    return [
        {
            "position": position,
            "name": player.get("name"),
            "points": player.get("points", 0),
            "rounds_won": player.get("rounds_won", 0),
        }
        for position, player in enumerate(players, start=1)
    ]
