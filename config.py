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

# Chat privata (di solito un canale) dove il bot carica le figurine da condividere con
# `shareMessage` (#185): Telegram vuole la foto come file gia' caricato, e un URL pubblico della
# card esporrebbe il nome di chi l'ha fatta. Senza, la mini app usa la condivisione classica.
_share_storage_raw = (os.getenv("SHARE_STORAGE_CHAT_ID") or "").strip()
SHARE_STORAGE_CHAT_ID = int(_share_storage_raw) if _share_storage_raw.lstrip("-").isdigit() else None

_admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_TELEGRAM_IDS = [int(x) for x in _admin_ids_raw.split(",") if x.strip().isdigit()]

GENERATION_SECRET = os.getenv("GENERATION_SECRET")

# Separate secrets: never generate at startup (replicas must share the same value).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
TASK_SECRET = os.getenv("TASK_SECRET", "")
TASKS_QUEUE = os.getenv("TASKS_QUEUE", "")
BROADCAST_QUEUE = os.getenv("BROADCAST_QUEUE", "")
