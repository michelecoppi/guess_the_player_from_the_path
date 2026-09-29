"""Persistenza della sfida inline (#240): il registro del mittente e il conto di ogni card.

Sul documento utente:
- `inline_sent`: le ultime chiavi inviate, per non rimandare lo stesso percorso;
- `inline_day` / `inline_count`: quante card sono partite oggi (tetto giornaliero);
- `inline_played`: le card a cui ha gia' risposto, perche' ognuno conti una volta sola.

In `inline_cards/{card}` c'e' solo il conto (`solved`, `failed`) e quanto serve per
riscrivere la didascalia del messaggio: **nessun id utente**. Chi chiede /forgetme sparisce
con il suo documento, e nelle card resta un numero.
"""
import secrets
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from services import firebase_service as fs

INLINE_CARDS = "inline_cards"
# Dopo un mese una card non si aggiorna piu' (il messaggio e' lontano nella chat); il campo
# serve a una policy TTL facoltativa, come `app_duels.expires_at`.
CARD_LIFETIME = timedelta(days=30)
PLAYED_MEMORY = 200


def _card_ref(card_id):
    return fs.db.collection(INLINE_CARDS).document(card_id)


def record_sent(user_id, key, today, limit, memory):
    """Segna l'invio di una card. False se il mittente aveva gia' raggiunto il tetto: la
    card e' partita comunque (Telegram non la ritira), ma non consuma un altro posto."""
    ref = fs.user_ref(user_id)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        user = snapshot.to_dict() or {}
        count = int(user.get("inline_count") or 0) if user.get("inline_day") == today else 0
        sent = [k for k in (user.get("inline_sent") or []) if k != key] + [key]
        within = count < limit
        transaction.update(ref, {
            "inline_sent": sent[-memory:],
            "inline_day": today,
            "inline_count": count + 1 if within else count,
        })
        return within

    return commit(fs.db.transaction())


def create_card(code, lang, inline_message_id, now=None):
    now = now or datetime.now(timezone.utc)
    card_id = secrets.token_hex(5)
    _card_ref(card_id).set({
        "code": code, "lang": lang, "inline_message_id": inline_message_id,
        "solved": 0, "failed": 0, "created_at": now, "expires_at": now + CARD_LIFETIME,
    })
    return card_id


def record_result(user_id, card_id, solved):
    """Conta il risultato di un giocatore su una card, una volta sola per giocatore.

    Ritorna la card aggiornata, oppure None se la card non c'e' o l'aveva gia' contato."""
    card_ref = _card_ref(card_id)
    user_ref = fs.user_ref(user_id)

    @firestore.transactional
    def commit(transaction):
        card_snapshot = card_ref.get(transaction=transaction)
        user_snapshot = user_ref.get(transaction=transaction)
        if not card_snapshot.exists or not user_snapshot.exists:
            return None
        played = list((user_snapshot.to_dict() or {}).get("inline_played") or [])
        if card_id in played:
            return None
        card = card_snapshot.to_dict() or {}
        field = "solved" if solved else "failed"
        card[field] = int(card.get(field) or 0) + 1
        transaction.update(card_ref, {field: card[field]})
        transaction.update(user_ref, {"inline_played": (played + [card_id])[-PLAYED_MEMORY:]})
        return card

    return commit(fs.db.transaction())
