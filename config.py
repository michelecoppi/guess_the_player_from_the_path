import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
# Base pubblica del servizio (es. https://xxx.run.app): serve alla mini app Telegram e
# al link di condivisione. Se non e' configurata, il bot funziona esattamente come prima.
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
WEBAPP_URL = f"{PUBLIC_BASE_URL}/app" if PUBLIC_BASE_URL else ""
BOT_USERNAME = (os.environ.get("BOT_USERNAME") or "").lstrip("@")

_admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_TELEGRAM_IDS = [int(x) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]

GENERATION_SECRET = os.getenv("GENERATION_SECRET")
