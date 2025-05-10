from telegram import Update
from telegram.ext import ContextTypes


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "🛠️ Comandi disponibili:\n\n"
        "/start - Inizia a usare il bot e registrati.\n"
        "/guess <risposta> - Indovina la carriera con il comando in privato al bot!\n"
        "/show - Mostra la sfida giornaliera.\n"
        "/stats - Mostra le tue statistiche.\n"
        "/top - Mostra la classifica dei migliori utenti.\n"
        "/events - Mostra il centro eventi.\n"
        "/notify - Attiva o disattiva le notifiche.\n"
    )
    
    await update.message.reply_text(help_message)