from datetime import datetime
import pytz
from telegram import Bot
from services.firebase_service import reload_daily_challenge
from config import BOT_TOKEN

bot = Bot(BOT_TOKEN)

async def update_daily_challenge():
    italy_tz = pytz.timezone('Europe/Rome')
    now_italy = datetime.now(italy_tz)
    today_str = now_italy.strftime('%d/%m/%y')  

    chat_id = 1224482376
    reload_daily_challenge(today_str)  

    text = f"Daily challenge aggiornata! 📅 {today_str}"
    await bot.send_message(chat_id=chat_id, text=text)
