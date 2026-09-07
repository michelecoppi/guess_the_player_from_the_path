"""Migrazione una tantum di Firestore al modello dati nuovo (vedi docs/firebase_review.md).

Cosa fa, in ordine:

1. **backup**: esporta in JSON `users`, `daily_path`, `events`, `seasons` prima di toccare
   qualsiasi cosa (si puo' saltare con --no-backup, ma non c'e' motivo di farlo);
2. **users**: sposta ogni documento sull'id `telegram_id`, fondendo eventuali duplicati
   creati dal vecchio `save_user()` non transazionale, e aggiunge `notifications_enabled` e
   `last_played_day`;
3. **daily_path**: converte le date da `gg/mm/aa` a ISO `YYYY-MM-DD`, id documento compreso;
4. **events**: converte le date, e sposta la mappa `ranking` in una sotto-collection
   `participants`, un documento per partecipante.

Va eseguita **a bot fermo**. E' idempotente: rieseguirla non fa danni.

    python scripts/migrate_firestore.py --dry-run     # mostra cosa farebbe
    python scripts/migrate_firestore.py               # esegue (con backup)
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.dates import normalize_day, today_iso  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

COUNTER_FIELDS = ("points_totali", "monthly_points", "players_guessed", "bonus_first_guessed")


# ---------------------------------------------------------------------------
# Trasformazioni pure (testabili senza Firestore)
# ---------------------------------------------------------------------------

def migrate_user_payload(data, today=None):
    """Documento utente nel formato nuovo.

    `has_guessed_today`/`daily_attempts` nel vecchio modello si riferivano implicitamente al
    giorno in cui girava il job notturno: qui li ancoriamo esplicitamente a oggi, altrimenti
    dopo la migrazione varrebbero per sempre."""
    today = today or today_iso()
    payload = dict(data)

    payload["telegram_id"] = data.get("telegram_id")
    payload["notifications_enabled"] = data.get(
        "notifications_enabled", data.get("chat_id", -1) != -1
    )

    has_guessed = data.get("has_guessed_today", False)
    attempts = data.get("daily_attempts", 0)
    if has_guessed or attempts:
        payload["last_played_day"] = normalize_day(data.get("last_played_day")) or today
    else:
        payload["last_played_day"] = normalize_day(data.get("last_played_day"))
        payload["daily_attempts"] = 0
        payload["has_guessed_today"] = False

    return payload


def merge_duplicate_users(first, second):
    """Fonde due documenti dello stesso utente (creati dal vecchio /start non atomico):
    i punti si sommano, i trofei si uniscono, le notifiche restano attive se lo erano in
    almeno uno dei due."""
    merged = dict(first)
    for field in COUNTER_FIELDS:
        merged[field] = first.get(field, 0) + second.get(field, 0)

    trophies = list(first.get("trophies", []))
    for trophy in second.get("trophies", []):
        if trophy not in trophies:
            trophies.append(trophy)
    merged["trophies"] = trophies

    chat_ids = [c for c in (first.get("chat_id"), second.get("chat_id")) if c not in (None, -1)]
    merged["chat_id"] = chat_ids[0] if chat_ids else -1
    merged["notifications_enabled"] = bool(
        first.get("notifications_enabled") or second.get("notifications_enabled")
    )
    merged["first_name"] = first.get("first_name") or second.get("first_name")

    days = [d for d in (first.get("last_played_day"), second.get("last_played_day")) if d]
    merged["last_played_day"] = max(days) if days else None
    merged["has_guessed_today"] = bool(
        first.get("has_guessed_today") or second.get("has_guessed_today")
    )
    merged["daily_attempts"] = max(first.get("daily_attempts", 0), second.get("daily_attempts", 0))
    return merged


def migrate_daily_path_payload(data, old_doc_id=None):
    payload = dict(data)
    day = normalize_day(data.get("day") or data.get("current_day"))
    if not day and old_doc_id:
        day = normalize_day(old_doc_id.replace("-", "/"))
    payload["day"] = day
    payload.pop("current_day", None)
    return day, payload


def migrate_event_payload(data):
    """Date in ISO; la classifica esce dal documento (torna a parte come partecipanti)."""
    payload = dict(data)
    payload["dates"] = [normalize_day(d) for d in data.get("dates", [])]
    payload["daily_data"] = {
        normalize_day(day): value for day, value in (data.get("daily_data") or {}).items()
    }
    if data.get("trophy_day"):
        payload["trophy_day"] = normalize_day(data["trophy_day"])
    payload.pop("ranking", None)
    return payload


def participants_from_ranking(ranking):
    """Da `ranking: {user_id: {...}}` a un documento per partecipante."""
    participants = {}
    for user_id, entry in (ranking or {}).items():
        if not isinstance(entry, dict):
            continue
        attempts_by_day = {normalize_day(k): v for k, v in (entry.get("daily_attempts") or {}).items()}
        last_day = max(attempts_by_day) if attempts_by_day else None
        participants[str(user_id)] = {
            "telegram_id": entry.get("telegram_id") or _as_int(user_id),
            "name": entry.get("name", "Sconosciuto"),
            "points": entry.get("points", 0),
            "daily_attempts": attempts_by_day.get(last_day, 0) if last_day else 0,
            "has_guessed_today": entry.get("has_guessed_today", False),
            "last_played_day": last_day,
        }
    return participants


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


# ---------------------------------------------------------------------------
# Esecuzione su Firestore
# ---------------------------------------------------------------------------

def backup(db, directory):
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dump = {}
    for collection in ("users", "daily_path", "events", "seasons"):
        dump[collection] = {doc.id: _jsonable(doc.to_dict()) for doc in db.collection(collection).stream()}
        logging.info(f"[BACKUP] {collection}: {len(dump[collection])} documenti")

    path = os.path.join(directory, f"firestore-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2, default=str)
    logging.info(f"[BACKUP] scritto {path}")
    return path


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def migrate_users(db, dry_run):
    users_ref = db.collection("users")
    target_payloads = {}
    to_delete = []

    for doc in users_ref.stream():
        data = doc.to_dict()
        telegram_id = data.get("telegram_id")
        if telegram_id is None:
            logging.warning(f"[USERS] {doc.id}: nessun telegram_id, lo salto (controllalo a mano)")
            continue

        target_id = str(telegram_id)
        payload = migrate_user_payload(data)

        if target_id in target_payloads:
            logging.warning(f"[USERS] duplicato per telegram_id {target_id}: fondo i due documenti")
            payload = merge_duplicate_users(target_payloads[target_id], payload)
        target_payloads[target_id] = payload

        if doc.id != target_id:
            to_delete.append(doc.reference)

    logging.info(f"[USERS] {len(target_payloads)} utenti, {len(to_delete)} documenti da rimuovere")
    if dry_run:
        return len(target_payloads)

    for target_id, payload in target_payloads.items():
        users_ref.document(target_id).set(payload, merge=True)
    for ref in to_delete:
        ref.delete()
    return len(target_payloads)


def migrate_daily_paths(db, dry_run):
    collection = db.collection("daily_path")
    migrated = 0

    for doc in collection.stream():
        day, payload = migrate_daily_path_payload(doc.to_dict(), doc.id)
        if not day:
            logging.warning(f"[DAILY_PATH] {doc.id}: data non riconoscibile, lo salto")
            continue
        if doc.id == day and doc.to_dict().get("day") == day:
            continue

        migrated += 1
        if dry_run:
            logging.info(f"[DAILY_PATH] {doc.id} -> {day}")
            continue

        collection.document(day).set(payload)
        if doc.id != day:
            doc.reference.delete()

    logging.info(f"[DAILY_PATH] {migrated} documenti migrati")
    return migrated


def migrate_events(db, dry_run):
    from firebase_admin import firestore

    collection = db.collection("events")
    migrated = 0

    for doc in collection.stream():
        data = doc.to_dict()
        payload = migrate_event_payload(data)
        participants = participants_from_ranking(data.get("ranking"))

        migrated += 1
        if dry_run:
            logging.info(f"[EVENTS] {doc.id}: {len(participants)} partecipanti, date -> ISO")
            continue

        for participant_id, participant in participants.items():
            doc.reference.collection("participants").document(participant_id).set(participant, merge=True)

        payload["ranking"] = firestore.DELETE_FIELD
        doc.reference.set(payload, merge=True)

    logging.info(f"[EVENTS] {migrated} eventi migrati")
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migra Firestore al modello dati nuovo")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe senza scrivere")
    parser.add_argument("--no-backup", action="store_true", help="salta l'export JSON preliminare")
    parser.add_argument("--backup-dir", default="backup", help="cartella dell'export (default: backup/)")
    parser.add_argument(
        "--only",
        default="users,daily_path,events",
        help="quali parti migrare, separate da virgola",
    )
    args = parser.parse_args()

    from services.firebase_service import db

    steps = [s.strip() for s in args.only.split(",") if s.strip()]

    if not args.no_backup and not args.dry_run:
        backup(db, args.backup_dir)

    if "users" in steps:
        migrate_users(db, args.dry_run)
    if "daily_path" in steps:
        migrate_daily_paths(db, args.dry_run)
    if "events" in steps:
        migrate_events(db, args.dry_run)

    logging.info("Migrazione completata" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
