import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from telegram import LabeledPrice, MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    BOT_USERNAME,
    GENERATION_SECRET,
    TASK_SECRET,
    WEBAPP_URL,
    WEBHOOK_SECRET,
    WEBHOOK_URL,
)
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
    admin_support_reply,
    admin_unblock,
)
from handlers.archive_handler import archive, archive_callback, back_to_today
from handlers.daily_job import broadcast_batch, update_daily_challenge
from handlers.error_handler import on_error
from handlers.events_handler import events, handle_event_navigation
from handlers.group_handler import (
    group_challenge,
    group_new_round_callback,
    group_standings,
)
from handlers.guess_handler import CARD_PREFIX, free_text_guess, guess, share_card_callback
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
from handlers.privacy_handler import forgetme
from handlers.shop_handler import (
    admin_refund,
    precheckout_callback,
    shop_callback,
    shop_command,
    successful_payment_callback,
)
from handlers.show_daily_path_handler import show
from handlers.show_stats_handler import back_to_stats_callback, show_trophies_callback, stats
from handlers.solution_handler import solution
from handlers.start_handler import start
from handlers.support_handler import paysupport
from handlers.top_users_handler import leaderboard_callback, top
from handlers.training_handler import training, training_callback
from services import (
    alerts,
    firebase_service,
    game,
    monthly_closure,
    shop,
    task_queue,
    trophies,
    work_receipts,
)
from services import leagues as league_rules
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from services.rate_limit import TokenBucket
from services.share import card_image
from services.webapp_api import (
    MAX_ARCHIVE_ATTEMPTS,
    build_archive_challenge,
    build_calendar,
    build_profile,
    build_public_profile,
    play,
    search_public_profiles,
)
from services.webapp_auth import user_id_from_init_data

logging.basicConfig(level=logging.INFO)
# httpx registra a INFO la URL completa di ogni richiesta, e nelle chiamate a Telegram il
# token del bot **sta dentro la URL**: a INFO finisce in chiaro nei log di Cloud Run, che
# vede chiunque abbia il ruolo di lettura sui log. Da WARNING in su restano gli errori, che
# non portano la URL. Non e' un dettaglio di rumore: e' il token che apre il bot.
logging.getLogger("httpx").setLevel(logging.WARNING)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_error_handler(on_error)
api_limiter = TokenBucket()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("app", start))
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
telegram_app.add_handler(CommandHandler(["shop", "negozio"], shop_command))
telegram_app.add_handler(CommandHandler("top", top))
telegram_app.add_handler(CommandHandler("notify", notify))
telegram_app.add_handler(CommandHandler("language", language))
telegram_app.add_handler(CommandHandler("forgetme", forgetme))
telegram_app.add_handler(CommandHandler("paysupport", paysupport))
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
telegram_app.add_handler(CommandHandler("admin_refund", admin_refund))
telegram_app.add_handler(CommandHandler("admin_support_reply", admin_support_reply))
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
telegram_app.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop_"))
telegram_app.add_handler(CallbackQueryHandler(share_card_callback, pattern=f"^{CARD_PREFIX}:"))
telegram_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="show_.*"))
# Pagamenti in Stelle. La pre-checkout e' l'ultimo momento in cui si puo' rifiutare (Telegram
# aspetta dieci secondi); il messaggio con `successful_payment` e' la consegna, e non e' un
# messaggio di testo, quindi non passa mai dal gestore dei tentativi qui sotto.
telegram_app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
telegram_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
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
    if WEBAPP_URL:
        try:
            await telegram_app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Play", web_app=WebAppInfo(url=WEBAPP_URL))
            )
        except Exception as e:
            logging.warning(f"Impossibile impostare il pulsante mini app: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", WEBHOOK_SECRET):
        raise RuntimeError("WEBHOOK_SECRET must contain 32-256 URL-safe characters")
    task_queue.validate_configuration()
    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    else:
        logging.warning("WEBHOOK_URL non configurato: webhook Telegram non registrato all'avvio.")
    await _register_bot_commands()
    try:
        yield
    finally:
        await telegram_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def measure_webapp_request(request: Request, call_next):
    if not request.url.path.startswith("/app/api/"):
        return await call_next(request)
    started = perf_counter()
    response = await call_next(request)
    elapsed_ms = (perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    route = request.scope.get("route")
    logging.info("[WEBAPP] %s status=%s duration_ms=%.1f",
                 getattr(route, "path", "unknown"), response.status_code, elapsed_ms)
    return response

@app.get("/")
async def root():
    return {"message": "Bot attivo!"}

@app.head("/ping")
async def ping():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(req: Request):
    supplied = req.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not WEBHOOK_SECRET or not hmac.compare_digest(supplied.encode(), WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        data = await req.json()
        if not isinstance(data, dict) or type(data.get("update_id")) is not int:
            raise ValueError("invalid update_id")
        Update.de_json(data, telegram_app.bot)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid update") from None
    await run_in_threadpool(task_queue.enqueue, "/internal/telegram-update", data,
                            f"telegram-{data['update_id']}")
    return {"status": "ok"}


WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
_static_files: dict[str, str] = {}


def _static(name):
    """Un file di `webapp/`, letto una volta sola e poi tenuto in memoria.

    Le pagine servite da qui sono tre - la mini app e i due documenti legali - e stanno tutte
    sullo stesso servizio del bot: non serve un altro hosting, ne' un dominio in piu'. Sono
    file che cambiano solo con un deploy, quindi rileggerli ad ogni richiesta sarebbe un
    accesso al disco per niente."""
    if name not in _static_files:
        with open(os.path.join(WEBAPP_DIR, name), encoding="utf-8") as f:
            _static_files[name] = f.read()
    return _static_files[name]


def _static_response(name, request, media_type="text/html"):
    content = _static(name)
    etag = '"' + hashlib.sha256(content.encode()).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(value.strip().removeprefix("W/") in (etag, "*") for value in candidates):
        return Response(status_code=304, headers=headers)
    return Response(content, media_type=media_type, headers=headers)


@app.get("/app", response_class=HTMLResponse)
def webapp_page(request: Request):
    return _static_response("index.html", request)


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return _static_response("terms.html", request)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return _static_response("privacy.html", request)


@app.get("/legal.css")
def legal_css(request: Request):
    return _static_response("legal.css", request, "text/css")


@app.get("/app/client.js")
def client_logic(request: Request):
    return _static_response("client.js", request, "text/javascript")


@app.get("/app/strings.js")
def client_strings(request: Request):
    return _static_response("strings.js", request, "text/javascript")


@app.get("/app/arena.js")
def client_arena(request: Request):
    return _static_response("arena.js", request, "text/javascript")


@app.get("/app/arena.css")
def client_arena_style(request: Request):
    return _static_response("arena.css", request, "text/css")


@app.get("/app/referrals.js")
def client_referrals(request: Request):
    return _static_response("referrals.js", request, "text/javascript")


@app.get("/app/referrals.css")
def client_referrals_style(request: Request):
    return _static_response("referrals.css", request, "text/css")


def _webapp_user(payload, cost=1):
    """Chi sta chiamando, secondo la **sola** firma di initData.

    Il client non manda mai un id: se lo mandasse, chiunque potrebbe chiedere i dati di
    chiunque - e adesso che la mini app gioca davvero, potrebbe anche giocare al posto di un
    altro. Ritorna (user_id, documento utente); 404 se non ha mai fatto /start."""
    try:
        user_id = user_id_from_init_data(payload.get("initData", ""), BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None

    wait = api_limiter.retry_after(user_id, cost)
    if wait:
        raise HTTPException(status_code=429, detail="Troppe richieste", headers={"Retry-After": str(wait)})
    user_data = firebase_service.get_user_data(user_id)
    if user_data is None:
        raise HTTPException(status_code=404, detail="utente non registrato")
    return user_id, user_data


def _webapp_language(user_data):
    return user_data.get("language") or DEFAULT_LANGUAGE


@app.post("/app/api/me")
def webapp_me(payload: dict = Body(default={})):
    """Profilo, sfida di oggi, classifica, leghe e istogramma: una risposta sola."""
    user_id, user_data = _webapp_user(payload)
    return build_profile(
        user_id, lang=_webapp_language(user_data), user=user_data,
        include_social=payload.get("lightweight") is not True,
    )


@app.post("/app/api/profile/public")
def webapp_public_profile(payload: dict = Body(default={})):
    _, viewer = _webapp_user(payload)
    result = build_public_profile(payload.get("profile_id"), lang=_webapp_language(viewer))
    if result is None:
        raise HTTPException(status_code=404, detail="profilo non disponibile")
    return result


@app.post("/app/api/referrals")
def webapp_referrals(payload: dict = Body(default={})):
    from services import referrals
    # Costa piu' di ogni altra chiamata: una pagina puo' riconciliare venti amici, e ognuno
    # e' una query sullo storico. La sezione ha un pulsante "Aggiorna", non un polling.
    user_id, user = _webapp_user(payload, cost=10)
    cursor = payload.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 64):
        raise HTTPException(status_code=400, detail="invalid cursor")
    return referrals.dashboard(user_id, _webapp_language(user), cursor, user)


@app.post("/app/api/profile/search")
def webapp_search_profiles(payload: dict = Body(default={})):
    """Cerca profili per nome senza esporre il documento utente completo."""
    _webapp_user(payload, cost=2)
    query = payload.get("query")
    if not isinstance(query, str) or len(query.strip()) < 2:
        raise HTTPException(status_code=400, detail="servono almeno due caratteri")
    return {"profiles": search_public_profiles(query)}


@app.post("/app/api/guess")
def webapp_guess(payload: dict = Body(default={})):
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
def webapp_hint(payload: dict = Body(default={})):
    """Un indizio sulla sfida di oggi, allo stesso prezzo che si paga in chat."""
    user_id, user_data = _webapp_user(payload)
    return game.take_hint(user_id, _webapp_language(user_data))


@app.post("/app/api/arena")
def webapp_arena(payload: dict = Body(default={})):
    from config import BOT_USERNAME
    from services import app_events, arena
    user_id, user = _webapp_user(payload, cost=2)
    lang = _webapp_language(user)
    mode, action = payload.get("mode"), payload.get("action", "get")
    try:
        if mode == "training":
            return arena.training(user_id, action, payload.get("answer"), payload.get("revision"), lang)
        if mode == "duel":
            if action == "create" and (not BOT_USERNAME or not WEBAPP_URL):
                raise arena.ArenaError("unavailable")
            code = payload.get("code") or user.get("app_duel")
            if action == "get" and not code:
                # Nessuna partita aperta: resta lo storico, che e' gia' nel documento utente.
                return {"session": None, "ledger": arena.ledger(user)}
            result = arena.duel(user_id, user.get("first_name", "?"), action, code,
                                payload.get("answer"), payload.get("revision"), lang, profile=user)
            result["invite_url"] = f"https://t.me/{BOT_USERNAME}?start=duel_{result['code']}" if BOT_USERNAME else None
            return result
        if mode == "events":
            feedback = None
            if action == "guess":
                feedback = app_events.guess(user_id, user.get("first_name", "?"), payload.get("code"),
                                            payload.get("day"), payload.get("answer"), payload.get("revision"))
            elif action != "get":
                raise arena.ArenaError("invalid")
            return {**app_events.list_events(user_id, lang), "feedback": feedback}
        raise arena.ArenaError("invalid")
    except arena.ArenaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.post("/app/api/calendar")
def webapp_calendar(payload: dict = Body(default={})):
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
def webapp_league(payload: dict = Body(default={})):
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


@app.post("/app/api/shop")
def webapp_shop(payload: dict = Body(default={})):
    """La vetrina: la **stessa** che disegna il comando /shop (services/shop.py)."""
    _, user_data = _webapp_user(payload)
    return shop.catalogue_for(user_data, _webapp_language(user_data))


@app.post("/app/api/shop/buy")
async def webapp_shop_buy(payload: dict = Body(default={})):
    """Il link della fattura da aprire con `openInvoice` dentro la mini app.

    La pagina non riceve mai un prezzo da mandare indietro: qui si guarda solo **quale**
    oggetto vuole, e quanto costa lo dice il catalogo. Se il prezzo arrivasse dal client,
    chiunque potrebbe comprare la collezione completa per una Stella."""
    user_id, user_data = await run_in_threadpool(_webapp_user, payload)
    item_id = payload.get("item")
    status = shop.purchase_status(user_data, item_id)
    if status != "ok":
        return {"status": status}

    item = shop.get_item(item_id)
    name, description = shop.localize(item, _webapp_language(user_data))
    link = await telegram_app.bot.create_invoice_link(
        title=name,
        description=description[:255],
        payload=shop.payment_payload(user_id, user_data, item),
        # Le Stelle non passano da un fornitore esterno: il token e' vuoto per definizione.
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=name, amount=shop.price_for(user_data, item))],
    )
    return {"status": "ok", "link": link}


@app.post("/app/api/shop/equip")
def webapp_shop_equip(payload: dict = Body(default={})):
    """Indossa un oggetto gia' posseduto. La regola sta in services/shop.py: qui si passa
    solo l'utente autenticato dalla firma di initData, mai un id arrivato dal client."""
    user_id, user_data = _webapp_user(payload)
    status = shop.equip(user_id, user_data, payload.get("item"))
    if status != "ok":
        return {"status": status}
    return {"status": "ok", "cosmetics": shop.appearance(
        firebase_service.get_user_data(user_id), _webapp_language(user_data)
    )}


@app.post("/app/api/shop/look")
def webapp_shop_look(payload: dict = Body(default={})):
    user_id, user_data = _webapp_user(payload)
    action = payload.get("action")
    name = payload.get("name")
    if action == "save":
        status = shop.save_look(user_id, user_data, name)
    elif action == "wear":
        status = shop.use_look(user_id, user_data, name)
    elif action == "delete" and isinstance(name, str):
        looks = [look for look in (user_data.get("cosmetics") or {}).get("looks", []) if look["name"] != name]
        firebase_service.save_looks(user_id, looks)
        status = "ok"
    else:
        status = "unknown_item"
    return {"status": status}


@app.post("/app/api/shop/history")
def webapp_shop_history(payload: dict = Body(default={})):
    user_id, user_data = _webapp_user(payload)
    lang = _webapp_language(user_data)
    rows = []
    for purchase in firebase_service.get_user_purchases(user_id):
        item = shop.get_item(purchase.get("item_id"))
        rows.append({"name": shop.localize(item, lang)[0] if item else purchase.get("item_id", ""),
                     "day": purchase.get("day", ""), "stars": purchase.get("stars", 0),
                     "refunded": bool(purchase.get("refunded")), "charge_id": purchase.get("charge_id", "")})
    return {"purchases": rows, "support_url": f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""}


@app.post("/app/api/card")
def webapp_result_card(payload: dict = Body(default={})):
    """La figurina dell'ultimo risultato, come data URI.

    Torna in JSON e non come immagine servita da un URL perche' l'autenticazione della mini
    app e' la firma di initData, che viaggia nel corpo di una POST: un `<img src>` verso una
    GET vorrebbe dire o un endpoint senza firma o un id nell'URL, e nessuna delle due va
    bene per una card che porta il nome di chi l'ha fatta."""
    user_id, user_data = _webapp_user(payload, cost=6)
    lang = _webapp_language(user_data)
    day = payload.get("day")
    attempts = int(payload.get("attempts") or 0)
    total = int(payload.get("max_attempts") or 0) or MAX_ATTEMPTS
    if not (1 <= attempts <= total <= MAX_ARCHIVE_ATTEMPTS + MAX_ATTEMPTS):
        raise HTTPException(status_code=400, detail="tentativi fuori scala")
    pinned = trophies.showcase(user_data, lang)
    buffer = card_image(
        user_data, lang, challenge_number(day), attempts, total,
        solved=bool(payload.get("solved", True)),
        streak=int(payload.get("streak") or 0),
        hints=int(payload.get("hints") or 0),
        honour=f"{pinned[0]['label']} - {pinned[0]['detail']}" if pinned else "",
    )
    return {"image": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}


@app.post("/app/api/trophies/pin")
def webapp_pin_trophies(payload: dict = Body(default={})):
    """Quali trofei stanno sul profilo. La regola su cosa si puo' appendere sta in
    services/trophies.py: qui arriva una lista di codici dal client, e un codice non e' una
    prova di aver vinto niente."""
    user_id, user_data = _webapp_user(payload)
    status = trophies.pin(user_id, user_data, payload.get("codes"))
    if status != "ok":
        return {"status": status}
    lang = _webapp_language(user_data)
    fresh = firebase_service.get_user_data(user_id)
    return {"status": "ok", "pinned": trophies.showcase(fresh, lang)}


@app.post("/internal/daily-job")
async def trigger_daily_job(x_cron_secret: str = Header(default=None)):
    """Chiamato da Cloud Scheduler a mezzanotte: su Cloud Run non c'e' un processo sempre
    acceso che possa tenere un cron interno, quindi il trigger arriva da fuori via HTTP."""
    if not GENERATION_SECRET or not hmac.compare_digest((x_cron_secret or "").encode(), GENERATION_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    await update_daily_challenge()
    return {"status": "ok"}


def _require_task_secret(supplied):
    if not TASK_SECRET or not hmac.compare_digest((supplied or "").encode(), TASK_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/internal/telegram-update")
async def consume_telegram_update(payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    if type(payload.get("update_id")) is not int:
        raise HTTPException(status_code=400, detail="Invalid update")
    update = Update.de_json(payload, telegram_app.bot)
    key = f"telegram-{update.update_id}"
    user = update.effective_user
    state = await run_in_threadpool(work_receipts.claim, key, serial_key=str(user.id) if user else None)
    if state == "busy":
        raise HTTPException(status_code=503, detail="Update in progress")
    if state == "uncertain":
        logging.error("Update %s interrupted: manual reconciliation required", update.update_id)
        # Nessuno se ne accorgerebbe altrimenti: la richiesta torna 200, l'utente non riceve
        # niente e non c'e' nessun errore da nessuna parte. E' il solo guasto del bot che
        # richiede per forza un intervento umano, quindi e' il solo che vale un messaggio.
        await alerts.notify_admins(
            f"⚠️ Update {update.update_id} interrotto a meta'"
            + (f" (utente {user.id})" if user else "")
            + ". Il tentativo puo' essere gia' stato consumato, quindi non viene riprovato: "
            "va riconciliato a mano dai log e dallo storico."
        )
        return {"status": state}
    if state == "claimed":
        async with asyncio.timeout(150):
            await telegram_app.process_update(update)
        await run_in_threadpool(work_receipts.finish, key)
    return {"status": "ok"}


@app.post("/internal/broadcast")
async def consume_broadcast(payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    return await broadcast_batch(payload["day"], payload.get("cursor"))


@app.post("/internal/monthly-close")
def consume_monthly_close(payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    return monthly_closure.close_batch(payload["day"], payload.get("cursor"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
