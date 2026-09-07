"""Entrypoint eseguito da GitHub Actions (o manualmente) per generare in anticipo:
- il buffer di sfide giornaliere (data/config.json -> buffer_days_ahead)
- un nuovo evento tematico, se le regole di rotazione lo consentono

Non richiede che il bot (Render) sia sveglio: scrive direttamente su Firestore usando
le stesse credenziali del service account (services/firebase_service.py).
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    from services.daily_generator import ensure_daily_buffer
    from services.event_generator import maybe_generate_event

    generated_days = ensure_daily_buffer()
    if generated_days:
        for day in generated_days:
            logging.info(f"[DAILY] Generata sfida per {day['date']}: player_id={day['player_id']} difficulty={day['difficulty']}")
    else:
        logging.info("[DAILY] Nessuna nuova sfida da generare: buffer gia' completo")

    event_code = maybe_generate_event()
    if event_code:
        logging.info(f"[EVENT] Nuovo evento generato: {event_code}")
    else:
        logging.info("[EVENT] Nessun nuovo evento generato (evento attivo o rotazione non ancora pronta)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Generazione contenuti fallita")
        sys.exit(1)
