import logging
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, GENERATION_SECRET, WEBHOOK_URL
from handlers.admin_handler import (
    admin_block,
    admin_blocked,
    admin_event_create,
    admin_events,
    admin_fs_add,
    admin_fs_del,
    admin_fs_list,
    admin_help,
    admin_next,
    admin_pool,
    admin_regen,
    admin_review,
    admin_stats,
    admin_status,
    admin_unblock,
)
from handlers.archive_handler import archive, archive_callback, back_to_today
from handlers.daily_job import update_daily_challenge
from handlers.events_handler import events, handle_event_navigation
from handlers.group_handler import (
    group_challenge,
    group_new_round_callback,
    group_standings,
)
from handlers.guess_handler import free_text_guess, guess
from handlers.help_handler import help
from handlers.hint_handler import hint_callback
from handlers.keyboards import bot_commands
from handlers.language_handler import language, language_callback
from handlers.league_handler import (
    invite_link,
    league_callback,
    league_create,
    league_join,
    league_leave,
    leagues,
)
from handlers.legend_handler import legend, legend_callback
from handlers.menu_handler import menu, menu_callback
from handlers.notify_handler import notify, notify_callback
from handlers.show_daily_path_handler import show
from handlers.show_stats_handler import back_to_stats_callback, show_trophies_callback, stats
from handlers.solution_handler import solution
from handlers.start_handler import start
from handlers.top_users_handler import leaderboard_callback, top
from handlers.training_handler import training, training_callback
from services import firebase_service, game
from services import leagues as league_rules
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from services.webapp_api import (
    build_archive_challenge,
    build_calendar,
    build_profile,
    play,
    player_names,
)
from services.webapp_auth import user_id_from_init_data

logging.basicConfig(level=logging.INFO)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("guess", guess))
telegram_app.add_handler(CommandHandler("events", events))
telegram_app.add_handler(CommandHandler("show", show))
# L'alias italiano vale come per gli altri comandi: il nome ufficiale resta l'inglese.
telegram_app.add_handler(CommandHandler(["solution", "soluzione"], solution))
telegram_app.add_handler(CommandHandler("stats", stats))
telegram_app.add_handler(CommandHandler("help", help))
telegram_app.add_handler(CommandHandler("menu", menu))
# Il nome ufficiale e' quello inglese (e' quello che il bot suggerisce nel menu "/");
# l'alias italiano resta registrato per chi lo ha gia' imparato.
telegram_app.add_handler(CommandHandler(["archive", "archivio"], archive))
telegram_app.add_handler(CommandHandler(["today", "oggi"], back_to_today))
# Allenamento (privato) e partita di gruppo: due facce dello stesso motore, cioe' le
# sfide gia' passate riproposte senza toccare la classifica generale.
telegram_app.add_handler(CommandHandler(["training", "allenamento"], training))
telegram_app.add_handler(CommandHandler(["round", "sfida"], group_challenge))
telegram_app.add_handler(CommandHandler(["standings", "classifica"], group_standings))
telegram_app.add_handler(CommandHandler(["league", "lega"], leagues))
telegram_app.add_handler(CommandHandler(["league_create", "lega_crea"], league_create))
telegram_app.add_handler(CommandHandler(["league_join", "lega_entra"], league_join))
telegram_app.add_handler(CommandHandler(["league_leave", "lega_esci"], league_leave))
telegram_app.add_handler(CommandHandler("top", top))
telegram_app.add_handler(CommandHandler("notify", notify))
telegram_app.add_handler(CommandHandler("language", language))
telegram_app.add_handler(CommandHandler(["legend", "legenda"], legend))
telegram_app.add_handler(CommandHandler("admin_help", admin_help))
telegram_app.add_handler(CommandHandler("admin_status", admin_status))
telegram_app.add_handler(CommandHandler("admin_stats", admin_stats))
telegram_app.add_handler(CommandHandler("admin_pool", admin_pool))
telegram_app.add_handler(CommandHandler("admin_regen", admin_regen))
telegram_app.add_handler(CommandHandler("admin_review", admin_review))
telegram_app.add_handler(CommandHandler("admin_next", admin_next))
telegram_app.add_handler(CommandHandler("admin_events", admin_events))
telegram_app.add_handler(CommandHandler("admin_block", admin_block))
telegram_app.add_handler(CommandHandler("admin_unblock", admin_unblock))
telegram_app.add_handler(CommandHandler("admin_blocked", admin_blocked))
telegram_app.add_handler(CommandHandler("admin_fs_add", admin_fs_add))
telegram_app.add_handler(CommandHandler("admin_fs_list", admin_fs_list))
telegram_app.add_handler(CommandHandler("admin_fs_del", admin_fs_del))
telegram_app.add_handler(CommandHandler("admin_event_create", admin_event_create))
# La foto della coppia padre/figlio arriva con il comando nella didascalia, non nel testo:
# i CommandHandler non intercettano le didascalie, serve un MessageHandler dedicato.
telegram_app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/admin_fs_add"), admin_fs_add))
telegram_app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
telegram_app.add_handler(CallbackQueryHandler(archive_callback, pattern="^arch_"))
telegram_app.add_handler(CallbackQueryHandler(league_callback, pattern="^lg_"))
telegram_app.add_handler(CallbackQueryHandler(notify_callback, pattern="^(enable_notify|disable_notify|notify_on)$"))
telegram_app.add_handler(CallbackQueryHandler(hint_callback, pattern="^hint_daily$"))
telegram_app.add_handler(CallbackQueryHandler(language_callback, pattern="^set_lang_"))
telegram_app.add_handler(CallbackQueryHandler(legend_callback, pattern="^legend$"))
telegram_app.add_handler(CallbackQueryHandler(training_callback, pattern="^trn_"))
telegram_app.add_handler(CallbackQueryHandler(group_new_round_callback, pattern="^grp_new$"))
telegram_app.add_handler(CallbackQueryHandler(show_trophies_callback, pattern=r"^show_trophies_\d+$"))
telegram_app.add_handler(CallbackQueryHandler(back_to_stats_callback, pattern="^back_to_stats$"))
telegram_app.add_handler(CallbackQueryHandler(handle_event_navigation, pattern="^event_"))
telegram_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="show_.*"))
# Ultimo di proposito: in chat privata un messaggio di testo che non e' un comando vale
# come tentativo sulla sfida del giorno (non serve piu' scrivere /guess).
telegram_app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, free_text_guess)
)

async def _register_bot_commands():
    """Il menu "/" accanto alla casella di scrittura, tradotto per lingua. Se Telegram non
    risponde il bot parte lo stesso: e' un abbellimento, non una dipendenza."""
    try:
        for lang in SUPPORTED_LANGUAGES:
            await telegram_app.bot.set_my_commands(bot_commands(lang), language_code=lang)
        # Senza language_code e' il menu di chi ha una lingua che non supportiamo.
        await telegram_app.bot.set_my_commands(bot_commands("en"))
    except Exception as e:
        logging.warning(f"Impossibile impostare il menu comandi: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(WEBHOOK_URL)
    else:
        logging.warning("WEBHOOK_URL non configurato: webhook Telegram non registrato all'avvio.")
    await _register_bot_commands()
    yield


app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Bot attivo!"}

@app.head("/ping")
async def ping():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}


WEBAPP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "index.html")
_webapp_html = None


@app.get("/app", response_class=HTMLResponse)
async def webapp_page():
    """La mini app Telegram: una pagina sola, servita dallo stesso servizio del bot (non
    serve un altro hosting, ne' un dominio in piu')."""
    global _webapp_html
    if _webapp_html is None:
        with open(WEBAPP_PATH, encoding="utf-8") as f:
            _webapp_html = f.read()
    return HTMLResponse(_webapp_html)


def _webapp_user(payload):
    """Chi sta chiamando, secondo la **sola** firma di initData.

    Il client non manda mai un id: se lo mandasse, chiunque potrebbe chiedere i dati di
    chiunque - e adesso che la mini app gioca davvero, potrebbe anche giocare al posto di un
    altro. Ritorna (user_id, documento utente); 404 se non ha mai fatto /start."""
    try:
        user_id = user_id_from_init_data(payload.get("initData", ""), BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None

    user_data = firebase_service.get_user_data(user_id)
    if user_data is None:
        raise HTTPException(status_code=404, detail="utente non registrato")
    return user_id, user_data


def _webapp_language(user_data):
    return user_data.get("language") or DEFAULT_LANGUAGE


@app.post("/app/api/me")
async def webapp_me(payload: dict = Body(default={})):
    """Profilo, sfida di oggi, classifica, leghe e istogramma: una risposta sola."""
    user_id, user_data = _webapp_user(payload)
    return build_profile(user_id, lang=_webapp_language(user_data))


@app.post("/app/api/players")
async def webapp_players(payload: dict = Body(default={})):
    """I nomi per il completamento automatico del campo di risposta.

    Non regala niente (sono tutte le schede del dataset, anche quelle che come sfida del
    giorno non escono mai) ma toglie di mezzo il "l'ho scritto giusto?", che era il modo piu'
    stupido di bruciare un tentativo."""
    _webapp_user(payload)
    return {"players": player_names()}


@app.post("/app/api/guess")
async def webapp_guess(payload: dict = Body(default={})):
    """Un tentativo dalla mini app: la sfida di oggi, o una giornata passata con `day`.

    Le regole sono quelle di services/game.py, cioe' **le stesse** che applica la chat: qui
    non si decide niente, si traduce solo il risultato in JSON."""
    user_id, user_data = _webapp_user(payload)
    answer = (payload.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="risposta vuota")

    return play(
        user_id, user_data, answer,
        day=payload.get("day"), lang=_webapp_language(user_data),
    )


@app.post("/app/api/hint")
async def webapp_hint(payload: dict = Body(default={})):
    """Un indizio sulla sfida di oggi, allo stesso prezzo che si paga in chat."""
    user_id, user_data = _webapp_user(payload)
    return game.take_hint(user_id, _webapp_language(user_data))


@app.post("/app/api/calendar")
async def webapp_calendar(payload: dict = Body(default={})):
    """Il calendario delle giornate passate, con com'e' andata a chi guarda."""
    user_id, user_data = _webapp_user(payload)
    lang = _webapp_language(user_data)
    day = payload.get("day")
    if day:
        challenge = build_archive_challenge(user_id, day, lang)
        if challenge is None:
            raise HTTPException(status_code=404, detail="giornata inesistente")
        return challenge
    return {"days": build_calendar(user_id, lang)}


@app.post("/app/api/league")
async def webapp_league(payload: dict = Body(default={})):
    """Crea una lega, entra o esce. Le regole (limiti, lunghezza del nome, codici) stanno in
    services/leagues.py: le stesse dei comandi /league_*."""
    user_id, user_data = _webapp_user(payload)
    action = payload.get("action")
    name = user_data.get("first_name")

    if action == "create":
        status, code = league_rules.create(user_id, user_data, payload.get("name"), name)
        return {"status": status, "code": code, "link": invite_link(code) if code else ""}
    if action == "join":
        status, league = league_rules.join(user_id, user_data, payload.get("code"), name)
        return {"status": status, "league": league}
    if action == "leave":
        status, league = league_rules.leave(user_id, payload.get("code"))
        return {"status": status, "league": league}

    raise HTTPException(status_code=400, detail="azione sconosciuta")


@app.post("/internal/daily-job")
async def trigger_daily_job(x_cron_secret: str = Header(default=None)):
    """Chiamato da Cloud Scheduler a mezzanotte: su Cloud Run non c'e' un processo sempre
    acceso che possa tenere un cron interno, quindi il trigger arriva da fuori via HTTP."""
    if not GENERATION_SECRET or x_cron_secret != GENERATION_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    await update_daily_challenge()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
