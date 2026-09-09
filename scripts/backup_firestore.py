"""Export JSON di Firestore, da eseguire a mano o dal workflow settimanale.

Perche' non l'export gestito di Firestore: quello richiede il piano Blaze e un bucket. Qui
il database e' piccolo (utenti, un documento per giorno di gioco, qualche evento) e un JSON
per volta e' un backup che si legge, si mette in un artifact di GitHub Actions e si
ripristina con un ciclo for. Il valore di un backup e' che qualcuno lo esegua davvero.

A differenza del backup dentro `scripts/migrate_firestore.py` - che copre solo le quattro
collezioni toccate dalla migrazione, e senza sotto-collezioni - qui si esporta **tutto
quello che serve per ricostruire**: leghe con i membri, eventi con i partecipanti, utenti
con il loro archivio. Le sotto-collezioni sono la meta' dei dati del gioco (i partecipanti
a un evento, i punti di lega): un backup senza sarebbe un backup finto.

    python scripts/backup_firestore.py                       # in backup/
    python scripts/backup_firestore.py --out /tmp --quiet    # per gli script
    python scripts/backup_firestore.py --collections users   # solo una collezione
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import firebase_service  # noqa: E402

# Le collezioni di primo livello del gioco. `admin_settings` c'e' perche' contiene i
# giocatori sospesi (/admin_block): si perderebbe un dato che non sta in nessun file.
# `purchases` e' il registro dei pagamenti in Stelle: e' l'unico posto dove sta l'id
# della transazione Telegram, cioe' l'unica cosa con cui si puo' rimborsare qualcuno.
COLLECTIONS = (
    "users",
    "daily_path",
    "events",
    "seasons",
    "leagues",
    "father_son_pairs",
    "admin_settings",
    "purchases",
)

DEFAULT_OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")


def jsonable(value):
    """Firestore restituisce datetime, riferimenti e tipi suoi: qui diventano stringhe."""
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def export_document(doc, with_subcollections=True):
    """Il documento e, sotto la chiave `_subcollections`, quello che ha appeso."""
    payload = {"_data": jsonable(doc.to_dict() or {})}
    if not with_subcollections:
        return payload

    subcollections = {}
    for subcollection in doc.reference.collections():
        entries = {sub.id: export_document(sub) for sub in subcollection.stream()}
        if entries:
            subcollections[subcollection.id] = entries
    if subcollections:
        payload["_subcollections"] = subcollections
    return payload


def export(db, collections=COLLECTIONS, with_subcollections=True):
    dump = {}
    for name in collections:
        documents = {
            doc.id: export_document(doc, with_subcollections)
            for doc in db.collection(name).stream()
        }
        dump[name] = documents
        logging.info(f"[BACKUP] {name}: {len(documents)} documenti")
    return dump


def write_dump(dump, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(out_dir, f"firestore-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Esporta Firestore in un file JSON")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="cartella di destinazione")
    parser.add_argument("--collections", nargs="*", default=list(COLLECTIONS), help="collezioni da esportare")
    parser.add_argument("--no-subcollections", action="store_true", help="salta le sotto-collezioni")
    parser.add_argument("--quiet", action="store_true", help="stampa solo il percorso del file")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO, format="%(levelname)s %(message)s"
    )

    dump = export(
        firebase_service.db,
        collections=args.collections,
        with_subcollections=not args.no_subcollections,
    )
    path = write_dump(dump, args.out)

    total = sum(len(documents) for documents in dump.values())
    logging.info(f"[BACKUP] {total} documenti scritti in {path}")
    print(path)


if __name__ == "__main__":
    main()
