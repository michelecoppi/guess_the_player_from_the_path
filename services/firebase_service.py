import firebase_admin
from cache import set_cache
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_PATH
from datetime import datetime
import pytz
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
            "chat_id": -1,
            "points_totali": 0,
            "daily_attempts": 0,
            "has_guessed_today": False,
            "trophies": [],
            "players_guessed": 0,
            "bonus_first_guessed": 0,
        })
        return f"Benvenuto, {first_name}! Il tuo account è stato creato. fai /help per vedere la lista dei comandi disponibili."
    else:
        return f"Ciao di nuovo, {first_name}!"

def update_user_points(user_id, points, bonus):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()
    
    for user in results:
        user_ref = users_ref.document(user.id)
        update_data = {
            "points_totali": firestore.Increment(points),
            "players_guessed": firestore.Increment(1),
            "has_guessed_today": True
        }

        if bonus > 0:
            update_data["bonus_first_guessed"] = firestore.Increment(1)
        
        user_ref.update(update_data)
        
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

def reload_daily_challenge(today_str):
    daily_path_ref = db.collection("daily_path")
    
    query = daily_path_ref.where("current_day", "==", today_str).limit(1)
    results = query.stream()

    doc = next(results, None)

    if doc:
        data = doc.to_dict()
        
        set_cache({
            "current_day": data.get("current_day"),
            "image_url": data.get("image_url"),
            "correct_answers": data.get("correct_answers", []),
            "difficulty": data.get("difficulty"),
            "first_correct_user": False  
        })

        reset_daily_attempts()

def load_daily_challenge(today_str):
    daily_path_ref = db.collection("daily_path")
    query = daily_path_ref.where("current_day", "==", today_str).limit(1)
    results = query.stream()

    doc = next(results, None)

    if doc:
        data = doc.to_dict()
        
        set_cache({
            "current_day": data.get("current_day"),
            "image_url": data.get("image_url"),
            "correct_answers": data.get("correct_answers", []),
            "difficulty": data.get("difficulty"),
            "first_correct_user": data.get("first_correct_user", False)  
        })
    else:
        logging.info(f"Nessuna daily challenge trovata per il giorno {today_str}")


def update_daily_challenge_first_correct():
    daily_path_ref = db.collection("daily_path")
    
    italy_tz = pytz.timezone('Europe/Rome')
    now_italy = datetime.now(italy_tz)
    today_str = now_italy.strftime('%d/%m/%y')  
    
    query = daily_path_ref.where("current_day", "==", today_str).limit(1)
    results = query.stream()

    doc = next(results, None)

    if doc:
        data = doc.to_dict()  
        daily_path_ref.document(doc.id).update({
            "first_correct_user": True
        })
        logging.info(f"[CACHE] Aggiornato il primo utente corretto per il giorno {today_str}")
    else:
        logging.info(f"[CACHE] Nessun daily challenge trovato per il giorno {today_str}")

def reset_daily_attempts():
    users_ref = db.collection("users")
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
def get_user_data(user_id):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()
    
    for user in results:
        return user.to_dict()
    
    return None

def get_all_users():
    users_ref = db.collection('users')
    users = users_ref.stream()

    user_list = []
    for user_doc in users:
        data = user_doc.to_dict()
        user_list.append({
            "telegram_id": data.get("telegram_id"),
            "username": data.get("first_name", "Sconosciuto"),
            "points": data.get("points_totali", 0)
        })
    return user_list

def get_all_broadcast_users():
    users_ref = db.collection("users")
    query = users_ref.where("chat_id", "!=", -1)
    results = query.stream()
    
    return [
        {
            "chat_id": user.to_dict()["chat_id"],
            "has_guessed_today": user.to_dict().get("has_guessed_today", False)
        }
        for user in results
    ]

def update_user_chat_id(user_id, chat_id):
    users_ref = db.collection("users")
    query = users_ref.where(field_path="telegram_id", op_string="==", value=user_id).limit(1)
    results = query.stream()

    for user in results:
        user_ref = users_ref.document(user.id)
        user_ref.update({
            "chat_id": chat_id
        })
def create_event():
    event_data = {
        "code": "BrazilianWeek_1_2025",
        "name": "Settimana Brasiliana",
        "description": "Settimana dedicata ai calciatori brasiliani arrivati in europa.",
        "start_date": "05/05/25",
        "end_date": "09/05/25",
        "trophy_day": "10/05/25",
        "type": "path",           
        "ranking": {},           
        "daily_data": {
            "05/05/25": {
                "image_url": "https://i.postimg.cc/Bvp0qT8d/photo-5807402448778808142-y.jpg",
                "correct_answers": ["Ronaldo"],   
                "points": 1,
                "first_correct_user": False,
            },
            "06/05/25": {
                "image_url": "https://i.postimg.cc/XYwWPSnN/photo-5807402448778808141-y.jpg",
                "correct_answers": ["Kaka","Kakà"],
                "points": 2,
                "first_correct_user": False,
            },
            "07/05/25": {
                "image_url": "https://i.postimg.cc/W1RjSbLf/photo-5807402448778808143-y.jpg",
                "correct_answers": ["Allan"],
                "points": 3,
                "first_correct_user": False,
            },
            "08/05/25": {
                "image_url": "https://i.postimg.cc/vmbyFqmr/photo-5807402448778808144-y.jpg",
                "correct_answers": ["Zico"],
                "points": 4,
                "first_correct_user": False,
            },
            "09/05/25": {
                "image_url": "https://i.postimg.cc/fTSDxSF9/photo-5807402448778808138-y.jpg",
                "correct_answers": ["Luiz Adriano","Adriano"],
                "points": 5,
                "first_correct_user": False,
            },
        } 
    }

    db.collection("events").add(event_data)
    