"""Completa i documenti utente a cui mancano dei campi.

I campi del documento utente si sono aggiunti col tempo (la lingua, la striscia di giorni
consecutivi, i contatori di archivio e allenamento). Chi si era registrato prima e' rimasto
senza: `save_user()` sul documento gia' esistente non scriveva niente, quindi quei campi non
comparivano mai da soli.

Da adesso `/start` completa il documento di chi lo esegue (services/firebase_service.py,
`missing_user_fields`), ma solo per chi passa di li'. Questo script fa la stessa identica
cosa su **tutti** gli utenti in una volta, senza aspettare che rifacciano /start.

Cosa NON fa: non tocca nessun campo gia' presente - punti, trofei, striscia e lingua scelta
a mano restano quelli che sono - e **non assegna una lingua** a chi non ce l'ha: quale sia
lo sa solo il client Telegram, quindi lo scrive /start. Chi resta senza continua a essere
servito nella lingua del suo client, che e' il ripiego di oggi. Con `--language xx` la si
puo' forzare lo stesso.

Si puo' eseguire a bot acceso ed e' idempotente: la seconda volta non trova piu' niente da
fare.

    python scripts/backfill_users.py --dry-run    # elenca chi verrebbe corretto
    python scripts/backfill_users.py             # scrive
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

BATCH_SIZE = 400  # il limite di un batch Firestore e' 500 operazioni


def plan_backfill(documents, language=None):
    """Da [(doc_id, dati)] a [(doc_id, campi da aggiungere)], saltando chi e' gia' completo.

    Funzione pura, cosi' la si prova senza Firestore."""
    from services.firebase_service import missing_user_fields

    plan = []
    for doc_id, data in documents:
        user_id = data.get("telegram_id")
        if user_id is None and str(doc_id).lstrip("-").isdigit():
            user_id = int(doc_id)
        missing = missing_user_fields(
            data or {},
            user_id=user_id,
            first_name=(data or {}).get("first_name"),
            language=language,
        )
        if missing:
            plan.append((doc_id, missing))
    return plan


def backfill(db, dry_run=False, language=None):
    from services.firebase_service import USERS_COLLECTION

    collection = db.collection(USERS_COLLECTION)
    documents = [(doc.id, doc.to_dict() or {}) for doc in collection.stream()]
    plan = plan_backfill(documents, language=language)

    logging.info(f"[USERS] {len(documents)} documenti, {len(plan)} da completare")
    for doc_id, missing in plan:
        logging.info(f"[USERS] {doc_id}: {', '.join(sorted(missing))}")

    if dry_run or not plan:
        return len(plan)

    batch = db.batch()
    pending = 0
    for doc_id, missing in plan:
        batch.update(collection.document(doc_id), missing)
        pending += 1
        if pending == BATCH_SIZE:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()

    logging.info(f"[USERS] {len(plan)} documenti completati")
    return len(plan)


def main():
    parser = argparse.ArgumentParser(description="Completa i documenti utente incompleti")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe senza scrivere")
    parser.add_argument(
        "--language", default=None,
        help="forza una lingua per chi non ne ha una valida (default: la lascia decidere a /start)",
    )
    args = parser.parse_args()

    from services.firebase_service import db

    backfill(db, dry_run=args.dry_run, language=args.language)
    logging.info("Fatto" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
