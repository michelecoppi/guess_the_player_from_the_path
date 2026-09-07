import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

_admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_TELEGRAM_IDS = [int(x) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]

GENERATION_SECRET = os.getenv("GENERATION_SECRET")