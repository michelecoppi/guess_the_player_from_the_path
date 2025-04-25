from telegram.ext import ApplicationBuilder, CommandHandler
from handlers.start_handler import start
from config import BOT_TOKEN 



app = ApplicationBuilder().token(BOT_TOKEN).build()


app.add_handler(CommandHandler("start", start))


app.run_polling()
