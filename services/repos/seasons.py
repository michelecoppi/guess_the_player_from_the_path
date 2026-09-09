"""Firestore seasons repository. Shared dependencies live in the compatibility facade."""
import logging

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists


def get_or_create_season(month_name, year):
    """La stagione mensile serve a numerare i trofei. Se manca, il reset mensile non deve
    saltare in silenzio (era il comportamento precedente): la creiamo noi, numerandola
    dopo l'ultima esistente."""
    from services import firebase_service as fs
    query = fs.db.collection(fs.SEASONS_COLLECTION).where("month", "==", month_name).where("year", "==", year).limit(1)
    for doc in query.stream():
        return doc.to_dict(), False

    existing = fs.db.collection(fs.SEASONS_COLLECTION).order_by(
        "season_number", direction=firestore.Query.DESCENDING
    ).limit(1).stream()
    last = next(existing, None)
    next_number = (last.to_dict().get("season_number", 0) + 1) if last else 1

    season = {
        "month": month_name,
        "year": year,
        "season_number": next_number,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    ref = fs.db.collection(fs.SEASONS_COLLECTION).document(f"{year}-{month_name}")
    try:
        ref.create(season)
    except AlreadyExists:
        return ref.get().to_dict(), False
    logging.info(f"[SEASON] Creata stagione mancante {month_name} {year} (numero {next_number})")
    return season, True

