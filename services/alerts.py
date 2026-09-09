"""Avvisi agli amministratori per i guasti che nessun log fara' mai notare.

Ci sono due modi di fallire, in questo bot, e vanno trattati diversamente.

Il primo e' l'errore che l'utente vede: un handler che solleva un'eccezione. Lo prende
handlers/error_handler.py, che risponde in chat e avvisa gli admin - c'e' gia' qualcuno che
si accorge di qualcosa, foss'anche solo l'utente.

Il secondo e' l'interruzione a meta' di un lavoro durevole (services/work_receipts.py). Un
update che si ferma dopo aver iniziato lascia una ricevuta `uncertain`: il tentativo puo'
essere gia' stato consumato, il messaggio puo' essere gia' partito, e per questo **non si
riprova**. Nessuno solleva niente, nessuno risponde niente, e la richiesta torna 200. Sono
esattamente i casi che richiedono un intervento umano, ed erano gli unici che nessuno
avrebbe visto: una riga di logging.error dentro Cloud Run che si guarda solo se si sa gia'
di doverla cercare.

Da qui non passano gli errori normali: se ogni guasto diventasse un messaggio, il canale
degli avvisi smetterebbe di voler dire "guarda questo".
"""
import logging

from telegram import Bot

from config import ADMIN_TELEGRAM_IDS, BOT_TOKEN

_bot = None


def get_bot():
    """Il client Telegram si crea al primo utilizzo, come quello di Firestore: cosi' il
    modulo si puo' importare (e testare) senza avere BOT_TOKEN configurato."""
    global _bot
    if _bot is None:
        # Senza token non c'e' niente da avvisare, ma nemmeno da far fallire: chi chiama e'
        # gia' dentro la gestione di un guasto, e `notify_admins` inghiotte l'eccezione.
        if not BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN non configurato: nessun avviso puo' partire")
        _bot = Bot(BOT_TOKEN)
    return _bot


async def notify_admins(text):
    """Non solleva mai: e' gia' il gestore di un guasto, e fallire qui vorrebbe dire
    trasformare un avviso mancato nell'errore che nasconde quello vero."""
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await get_bot().send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logging.warning("Impossibile avvisare l'admin %s: %s", admin_id, e)
