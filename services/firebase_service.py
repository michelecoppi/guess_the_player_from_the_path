import firebase_admin
from cache import set_cache
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_PATH
from datetime import datetime
import logging


cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)


firebase_admin.initialize_app(cred)
db = firestore.client()


def save_user(user_id, first_name):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()

    if not any(results):
        user_ref = db.collection("users").document() 
        user_ref.set({
            "first_name": first_name,
            "telegram_id": user_id,
            "date_created": datetime.now(),
            "points_totali": 0,
            "daily_attempts": 0,
            "has_guessed_today": False,
        })
        return f"Benvenuto, {first_name}! Il tuo account è stato creato."
    else:
        return f"Ciao di nuovo, {first_name}!"

def update_user_points(user_id, points):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()

    for user in results:
        user_ref = users_ref.document(user.id)
        user_ref.update({
            "points_totali": firestore.Increment(points),
            "has_guessed_today": True
        })
def get_user_daily_status(user_id):
    users_ref = db.collection("users")
    query = users_ref.where("telegram_id", "==", user_id).limit(1)
    results = query.stream()

    for user in results:
        user_data = user.to_dict()
        daily_attempts = user_data.get("daily_attempts", 0)
        has_guessed_today = user_data.get("has_guessed_today", False)
        return daily_attempts, has_guessed_today

    return 0, False

def reload_daily_challenge():
    daily_path_ref = db.collection("daily_path")
    
    today = datetime.now().strftime("%d/%m/%y")
    
    query = daily_path_ref.where("current_day", "==", today).limit(1)
    results = query.stream()

    doc = next(results, None)

    if doc:
        data = doc.to_dict()
        
        set_cache({
            "current_day": data.get("current_day"),
            "image_url": data.get("image_url"),
            "answers": data.get("answers", []),
            "difficulty": data.get("difficulty"),
            "first_correct_user": False  
        })

        reset_daily_attempts()

        logging.info(f"[CACHE] Daily challenge caricata per il giorno {today}")
    else:
        logging.info(f"[CACHE] Nessun daily challenge trovato per il giorno {today}")

def update_daily_challenge_first_correct():
    daily_path_ref = db.collection("daily_path")
    
    today = datetime.now().strftime("%d/%m/%y")
    
    query = daily_path_ref.where("current_day", "==", today).limit(1)
    results = query.stream()

    doc = next(results, None)

    if doc:
        data = doc.to_dict()
        
        daily_path_ref.document(doc.id).update({
            "first_correct_user": True
        })
        logging.info(f"[CACHE] Aggiornato il primo utente corretto per il giorno {today}")
    else:
        logging.info(f"[CACHE] Nessun daily challenge trovato per il giorno {today}")

def reset_daily_attempts():
    users_ref = firestore.client().collection("users")
    users = users_ref.stream()

    for user in users:
        user_ref = users_ref.document(user.id)
        user_ref.update({"daily_attempts": 0, "has_guessed_today": False})
    logging.info("Tentativi giornalieri resettati per tutti gli utenti")
def update_user_daily_attempts(user_id, attempts):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()

    for user in results:
        user_ref = users_ref.document(user.id)
        user_ref.update({
            "daily_attempts": attempts
        })