from datetime import datetime
from telegram import Bot
from config import BOT_TOKEN

bot = Bot(BOT_TOKEN)

async def send_daily_message():
    chat_id = 1224482376 
    text = f"Messaggio automatico! 📅 {datetime.now().strftime('%Y-%m-%d')}"
    await bot.send_message(chat_id=chat_id, text=text)