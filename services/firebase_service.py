import firebase_admin
from cache import set_cache
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_PATH
from datetime import datetime
import pytz
import logging


cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)

ITALY_TZ = pytz.timezone('Europe/Rome')


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
    
    now_italy = datetime.now(ITALY_TZ)
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
def get_current_event():

    now_italy = datetime.now(ITALY_TZ)
    current_date = now_italy.strftime('%d/%m/%y')
    
    events_ref = db.collection("events")
    query = events_ref.where("dates", "array_contains", current_date)
    results = query.stream()

    for event in results:
        event_data = event.to_dict()
        event_data["ref"] = event.reference
        return event_data

    return None

def reset_daily_guess_status_event(event_data, event_ref):
    rankings = event_data.get("ranking", {})

    for user_id, user_data in rankings.items():
        if isinstance(user_data, dict):
            user_data["has_guessed_today"] = False

    event_ref.update({"ranking": rankings})
    logging.info(f"Reset globale completato per evento con codice {event_data.get('code')}")


def get_event_trophy_day():
    now_italy = datetime.now(ITALY_TZ)
    current_date = now_italy.strftime('%d/%m/%y')
    
    events_ref = db.collection("events")
    query = events_ref.where("trophy_day", "==", current_date)
    results = query.stream()

    for event in results:
        return event.to_dict()

    return None

def update_users_trophies(event_doc):
    event_code = event_doc.get("code")
    ranking = event_doc.get("ranking", {}) 

    sorted_users = sorted(ranking.values(), key=lambda u: u.get("points", 0), reverse=True)

    for idx, user_data in enumerate(sorted_users[:3], start=1):
        telegram_id = user_data.get("telegram_id")
        if not telegram_id:
            continue

        trophy_string = f"{idx}_{event_code}"
        user_query = db.collection("users").where("telegram_id", "==", telegram_id).limit(1).stream()
        user_doc = next(user_query, None)

        if user_doc:
            user_doc.reference.update({
                "trophies": firestore.ArrayUnion([trophy_string])
            })


def get_display_name_for_date(date_str):
    daily_data = db.collection("daily_path")
    query = daily_data.where("current_day", "==", date_str).limit(1).stream()
    result = next(query, None)
    if not result:
        return None
    
    data = result.to_dict()
    solutions = data.get("correct_answers", [])

    full_names = [s for s in solutions if " " in s]
    if full_names:
        return full_names[0].title()

    if solutions:
        return solutions[0].title() 

    return None

def create_reverse_event():
    event_data = {
        "code": "PlayerCareer_1_2025",
        "name": "Player Career",
        "description": "Indovina alcune squadre dove hanno giocato questi giocatori",
	    "dates":["12/05/25","13/05/25","14/05/25","15/05/25","16/05,25"],
	    "event_img":"https://i.postimg.cc/J4typYSQ/Carriera-da-Giocatore-in-Azione.png",
	    "leaberboard_img":"https://i.postimg.cc/9FvfJmdW/badges-0004-leaderboard-300x300.png",
        "trophy_day": "17/05/25",
        "type": "career",
        "ranking": {},
        "daily_data": {
            "15/05/25": {
                "player_name": "Mohamed Salah",
                "image_url": "https://i.postimg.cc/MZgCMv0m/Mohamed-Salah-2018.jpg",
                "correct_answers": ["fiorentina", "roma", "liverpool", "chelsea", "basilea", "el mokawloon"],
                "min_correct": 3,
                "points": 1,
                "first_correct_user": False
            },
            "16/05/25": {
                "player_name": "Carlos Tevez",
                "image_url": "https://i.postimg.cc/Kvr0Gz0z/Carlos-Tevez-with-Argentina-November-2014-cropped.jpg",
                "correct_answers": ["juventus", "manchester city", "manchester united", "boca juniors", "west ham", "corinthians", "shanghai shenua"],
                "min_correct": 3,
                "points": 2,
                "first_correct_user": False
            },
            "17/05/25": {
                "player_name": "Giorgio Chiellini",
                "image_url": "https://i.postimg.cc/vmprLF0k/chiellini.png",
                "correct_answers": ["juventus", "fiorentina", "livorno", "los angeles fc"],
                "min_correct": 3,
                "points": 3,
                "first_correct_user": False
            },
            "18/05/25": {
                "player_name": "Ruud Gullit",
                "image_url": "https://i.postimg.cc/768zJ16y/e4c93dc561d0736c25857c9b7a80f333.jpg",
                "correct_answers": ["chelsea", "milan", "sampdoria", "psv", "feyenoord","hfc haarlem"],
                "min_correct": 4,
                "points": 4,
                "first_correct_user": False
            },
            "19/05/25": {
                "player_name": "Javier Mascherano",
                "image_url": "https://i.postimg.cc/4dgKxJLf/Mascherano-Congreso-2-cropped.jpg",
                "correct_answers": ["barcellona", "west ham", "liverpool", "river plate", "estudiantes", "hebei china fortune", "corinthians"],
                "min_correct": 3,
                "points": 5,
                "first_correct_user": False
            }
        }
    }

    db.collection("events").add(event_data)
  