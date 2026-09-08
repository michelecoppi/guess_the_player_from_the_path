"""Pulizia della collezione `daily_path`: sfide vecchie e documenti inservibili.

`daily_path` cresce di 365 documenti l'anno e non si guarda indietro: l'archivio mostra gli
ultimi dieci giorni, l'anti-ripetizione guarda gli ultimi 60, il numero della sfida e'
calcolato dalla data e non letto dal database. Un documento di due anni fa non lo legge
piu' nessuno.

Due categorie, tenute separate di proposito:

- **vecchi**: oltre la finestra che si vuole conservare (un anno di default). Si cancellano
  perche' non servono, non perche' siano rotti;
- **legacy**: documenti che il gioco non sa piu' aprire - id non in ISO (`08-09-25` invece
  di `2025-09-08`, cioe' scritti prima della migrazione), oppure senza il percorso di
  carriera o senza risposte accettate. Sono quelli che nell'archivio danno "sfida non piu'
  disponibile", e sono anche quelli che un domani rovinerebbero una modalita' allenamento
  costruita sulle sfide passate. Si cancellano solo se lo si chiede (`--drop-legacy`).

Il giorno di oggi e i giorni futuri non si toccano **mai**: sono la sfida in gioco e il
buffer gia' generato.

    python scripts/cleanup_daily_paths.py --dry-run          # cosa farebbe
    python scripts/cleanup_daily_paths.py                    # cancella i vecchi (>1 anno)
    python scripts/cleanup_daily_paths.py --drop-legacy      # anche quelli inservibili
    python scripts/cleanup_daily_paths.py --older-than 730   # tieni due anni

Prima di cancellare scrive sempre un JSON con i documenti che sta per togliere, nella
stessa cartella dei backup: una cancellazione senza copia non e' una pulizia, e' una
perdita di dati.
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backup_firestore import DEFAULT_OUT_DIR, jsonable  # noqa: E402
from services import firebase_service  # noqa: E402
from services.dates import shift_iso, today_iso  # noqa: E402

ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_KEEP_DAYS = 365
# Firestore accetta al massimo 500 operazioni per batch.
BATCH_SIZE = 400


def classify(doc_id, data, cutoff_day, today):
    """Cosa fare di un documento: 'keep', 'old' o 'legacy'.

    Funzione pura (nessun Firestore intorno), perche' e' la parte che decide che cosa
    sparisce: va provata su dei dizionari, non su un database vero."""
    data = data or {}
    day = data.get("day") if ISO_DAY.match(str(data.get("day", ""))) else None
    if not day and ISO_DAY.match(doc_id):
        day = doc_id

    # Senza una data leggibile e' per forza un documento pre-migrazione.
    if not day:
        return "legacy"

    # La sfida di oggi e il buffer dei giorni futuri non si toccano mai.
    if day >= today:
        return "keep"

    if day < cutoff_day:
        return "old"

    if not data.get("career_path") and not data.get("image_url"):
        return "legacy"
    if not data.get("correct_answers"):
        return "legacy"

    return "keep"


def scan(db, cutoff_day, today):
    buckets: dict[str, list] = {"keep": [], "old": [], "legacy": []}
    for doc in db.collection(firebase_service.DAILY_PATH_COLLECTION).stream():
        data = doc.to_dict() or {}
        buckets[classify(doc.id, data, cutoff_day, today)].append((doc.id, data, doc.reference))
    return buckets


def save_copy(entries, out_dir, label):
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(out_dir, f"daily_path-{label}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({doc_id: jsonable(data) for doc_id, data, _ in entries}, f, ensure_ascii=False, indent=2)
    return path


def delete(db, entries):
    deleted = 0
    for start in range(0, len(entries), BATCH_SIZE):
        batch = db.batch()
        for _, _, reference in entries[start:start + BATCH_SIZE]:
            batch.delete(reference)
        batch.commit()
        deleted += len(entries[start:start + BATCH_SIZE])
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Cancella le sfide giornaliere che non serve piu' tenere")
    parser.add_argument("--older-than", type=int, default=DEFAULT_KEEP_DAYS, help="giorni da conservare")
    parser.add_argument("--drop-legacy", action="store_true", help="cancella anche i documenti inservibili")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe senza cancellare")
    parser.add_argument("--backup-dir", default=DEFAULT_OUT_DIR, help="dove salvare la copia prima di cancellare")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    today = today_iso()
    cutoff_day = shift_iso(today, -args.older_than)
    buckets = scan(firebase_service.db, cutoff_day, today)

    logging.info(
        f"[CLEANUP] {len(buckets['keep'])} da tenere, {len(buckets['old'])} oltre "
        f"{args.older_than} giorni (prima del {cutoff_day}), {len(buckets['legacy'])} inservibili"
    )
    for doc_id, data, _ in buckets["legacy"]:
        logging.info(f"[CLEANUP] inservibile: {doc_id} (day={data.get('day')!r})")

    to_delete = list(buckets["old"])
    if args.drop_legacy:
        to_delete += buckets["legacy"]
    elif buckets["legacy"]:
        logging.info("[CLEANUP] i documenti inservibili restano: aggiungi --drop-legacy per toglierli")

    if not to_delete:
        logging.info("[CLEANUP] niente da cancellare")
        return

    if args.dry_run:
        logging.info(f"[CLEANUP] --dry-run: cancellerei {len(to_delete)} documenti")
        return

    path = save_copy(to_delete, args.backup_dir, "removed")
    logging.info(f"[CLEANUP] copia dei documenti da cancellare in {path}")
    deleted = delete(firebase_service.db, to_delete)
    logging.info(f"[CLEANUP] {deleted} documenti cancellati")


if __name__ == "__main__":
    main()
