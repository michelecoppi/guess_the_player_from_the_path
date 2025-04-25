import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_PATH
from datetime import datetime


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
            "points_totali": 0
        })
        return f"Benvenuto, {first_name}! Il tuo account è stato creato."
    else:
        return f"Ciao di nuovo, {first_name}!"

