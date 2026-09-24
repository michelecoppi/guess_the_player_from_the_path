"""The Mini App JSON API: `POST /app/api/*`, authenticated only by the Telegram initData signature.

Routes authenticate, rate-limit, check feature flags and delegate to services; the rules
live in the domains (docs/architecture.md). Moved verbatim from bot.py by #110.
"""
import base64
import logging

from fastapi import APIRouter, Body, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from telegram import LabeledPrice

import config
from apps.api.bridge import telegram
from domains.shop import service as shop
from services import feature_flags, firebase_service, game, observability, performance, trophies
from services import leagues as league_rules
from services import product_analytics as analytics
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.feature_flags import FeatureDisabled, Flag
from services.i18n import DEFAULT_LANGUAGE
from services.rate_limit import TokenBucket
from services.share import card_image
from services.webapp_api import (
    MAX_ARCHIVE_ATTEMPTS,
    build_archive_challenge,
    build_calendar,
    build_profile,
    build_public_profile,
    is_daily_play,
    play,
    search_public_profiles,
)
from services.webapp_auth import user_id_from_init_data

router = APIRouter()
# Per process, like the Cloud Run instance it runs in (docs/performance.md).
api_limiter = TokenBucket()


def _require_feature(flag, user_id):
    """Solo dopo `_webapp_user`: chi non e' autenticato riceve 401, non lo stato dei flag."""
    feature_flags.ensure_enabled(flag, user_id=user_id)


# Le modalita' di /app/api/arena e il flag che le governa. `events` e' l'esperienza eventi
# della mini app (services/app_events.py), non gli eventi in chat ne' la loro generazione.
_ARENA_MODE_FLAGS = {"training": Flag.ARENA, "duel": Flag.ARENA, "events": Flag.EVENTS_V2, "story": Flag.ARENA}


def _webapp_user(payload, cost=1):
    """Chi sta chiamando, secondo la **sola** firma di initData.

    Il client non manda mai un id: se lo mandasse, chiunque potrebbe chiedere i dati di
    chiunque - e adesso che la mini app gioca davvero, potrebbe anche giocare al posto di un
    altro. Ritorna (user_id, documento utente); 404 se non ha mai fatto /start."""
    try:
        user_id = user_id_from_init_data(payload.get("initData", ""), config.BOT_TOKEN)
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


@router.post("/app/api/perf")
def webapp_startup_timing(payload: dict = Body(default={})):
    """Quanto ci ha messo la mini app ad aprirsi, misurato dal telefono (#32).

    Serve la firma di initData, ma non il documento utente: nessuna lettura Firestore per
    una misura. Nel log finisce solo un insieme chiuso di numeri limitati
    (`performance.miniapp_startup_fields`), senza id ne' testo del client."""
    try:
        user_id = user_id_from_init_data(payload.get("initData", ""), config.BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    wait = api_limiter.retry_after(user_id, 1)
    if wait:
        raise HTTPException(status_code=429, detail="Troppe richieste", headers={"Retry-After": str(wait)})
    fields = performance.miniapp_startup_fields(payload)
    if fields is None:
        raise HTTPException(status_code=422, detail="metriche non valide")
    observability.log_event("miniapp.startup.measured", **fields)
    return {"status": "ok"}


@router.post("/app/api/me")
def webapp_me(payload: dict = Body(default={})):
    """Profilo, sfida di oggi, classifica, leghe e istogramma: una risposta sola."""
    user_id, user_data = _webapp_user(payload)
    return build_profile(
        user_id, lang=_webapp_language(user_data), user=user_data,
        include_social=payload.get("lightweight") is not True,
    )


@router.post("/app/api/profile/public")
def webapp_public_profile(payload: dict = Body(default={})):
    _, viewer = _webapp_user(payload)
    result = build_public_profile(payload.get("profile_id"), lang=_webapp_language(viewer))
    if result is None:
        raise HTTPException(status_code=404, detail="profilo non disponibile")
    return result


@router.post("/app/api/referrals")
def webapp_referrals(payload: dict = Body(default={})):
    from domains.referrals import service as referrals
    # Costa piu' di ogni altra chiamata: una pagina puo' riconciliare venti amici, e ognuno
    # e' una query sullo storico. La sezione ha un pulsante "Aggiorna", non un polling.
    user_id, user = _webapp_user(payload, cost=10)
    cursor = payload.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 64):
        raise HTTPException(status_code=400, detail="invalid cursor")
    return referrals.dashboard(user_id, _webapp_language(user), cursor, user)


@router.post("/app/api/profile/search")
def webapp_search_profiles(payload: dict = Body(default={})):
    """Cerca profili per nome senza esporre il documento utente completo."""
    _webapp_user(payload, cost=2)
    query = payload.get("query")
    if not isinstance(query, str) or len(query.strip()) < 2:
        raise HTTPException(status_code=400, detail="servono almeno due caratteri")
    return {"profiles": search_public_profiles(query)}


@router.post("/app/api/guess")
def webapp_guess(payload: dict = Body(default={})):
    """Un tentativo dalla mini app: la sfida di oggi, o una giornata passata con `day`.

    Le regole sono quelle di services/game.py, cioe' **le stesse** che applica la chat: qui
    non si decide niente, si traduce solo il risultato in JSON."""
    user_id, user_data = _webapp_user(payload)
    if is_daily_play(payload.get("day")):
        # L'archivio passa di qui ma non e' la superficie Daily: resta giocabile.
        _require_feature(Flag.DAILY_UI, user_id)
    answer = (payload.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="risposta vuota")

    return play(
        user_id, user_data, answer,
        day=payload.get("day"), lang=_webapp_language(user_data),
    )


@router.post("/app/api/hint")
def webapp_hint(payload: dict = Body(default={})):
    """Un indizio sulla sfida di oggi, allo stesso prezzo che si paga in chat."""
    user_id, user_data = _webapp_user(payload)
    _require_feature(Flag.HINTS, user_id)
    return game.take_hint(user_id, _webapp_language(user_data), surface="miniapp")


@router.post("/app/api/arena")
def webapp_arena(payload: dict = Body(default={})):
    from services import app_events, arena, story
    user_id, user = _webapp_user(payload, cost=2)
    lang = _webapp_language(user)
    mode, action = payload.get("mode"), payload.get("action", "get")
    if mode in _ARENA_MODE_FLAGS:
        # Spento: nessuna lettura ne' mossa nuova. Duelli e sessioni restano intatti su
        # Firestore e ricompaiono tali e quali quando il flag si riaccende.
        _require_feature(_ARENA_MODE_FLAGS[mode], user_id)
    try:
        if mode == "training":
            return arena.training(user_id, action, payload.get("answer"), payload.get("revision"), lang)
        if mode == "duel":
            if action == "create" and (not config.BOT_USERNAME or not config.WEBAPP_URL):
                raise arena.ArenaError("unavailable")
            if action == "list":
                # Tutti i duelli ancora aperti: in attesa di un avversario, in corso o
                # conclusi ma non ancora archiviati sul profilo di chi li guarda.
                return arena.list_duels(user_id, profile=user)
            code = payload.get("code") or user.get("app_duel")
            if action == "get" and not code:
                # Nessuna partita aperta: resta lo storico, che e' gia' nel documento utente.
                return {"session": None, "ledger": arena.ledger(user)}
            was_new = action == "create"
            was_join = action == "join"
            result = arena.duel(user_id, user.get("first_name", "?"), action, code,
                                payload.get("answer"), payload.get("revision"), lang, profile=user)
            if action != "delete":
                result["invite_url"] = f"https://t.me/{config.BOT_USERNAME}?start=duel_{result['code']}" if config.BOT_USERNAME else None
            if was_new:
                analytics.capture(analytics.Event.DUEL_CREATED, user_id=user_id,
                                  properties={"surface": "miniapp"})
            elif was_join:
                analytics.capture(analytics.Event.DUEL_JOINED, user_id=user_id,
                                  properties={"surface": "miniapp"})
            if action in ("join", "guess", "reveal") and result.get("complete"):
                # `complete` flips exactly once per player (arena.duel records the match on
                # the first request that observes it), so this cannot double-fire on a poll.
                analytics.capture(analytics.Event.DUEL_COMPLETED, user_id=user_id,
                                  properties={"surface": "miniapp"})
            return result
        if mode == "events":
            feedback = None
            if action == "guess":
                feedback = app_events.guess(user_id, user.get("first_name", "?"), payload.get("code"),
                                            payload.get("day"), payload.get("answer"), payload.get("revision"))
            elif action == "reveal":
                app_events.reveal(user_id, payload.get("code"), payload.get("day"), payload.get("revision"))
            elif action != "get":
                raise arena.ArenaError("invalid")
            return {**app_events.list_events(user_id, lang), "feedback": feedback}
        if mode == "story":
            if action == "list":
                return story.list_chapters(user_id, lang)
            chapter_id = payload.get("chapter_id")
            if not isinstance(chapter_id, str) or not chapter_id:
                raise story.StoryError("invalid")
            return story.chapter(user_id, chapter_id, action, payload.get("answer"), payload.get("revision"), lang)
        raise arena.ArenaError("invalid")
    except (arena.ArenaError, story.StoryError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/app/api/calendar")
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


@router.post("/app/api/league")
def webapp_league(payload: dict = Body(default={})):
    """Crea una lega, entra o esce. Le regole (limiti, lunghezza del nome, codici) stanno in
    services/leagues.py: le stesse dei comandi /league_*."""
    user_id, user_data = _webapp_user(payload)
    action = payload.get("action")
    name = user_data.get("first_name")

    if action == "create":
        status, code = league_rules.create(user_id, user_data, payload.get("name"), name)
        if status == "ok":
            analytics.capture(analytics.Event.LEAGUE_CREATED, user_id=user_id, properties={"surface": "miniapp"})
        return {"status": status, "code": code, "link": league_rules.invite_link(code, config.BOT_USERNAME) if code else ""}
    if action == "join":
        status, league = league_rules.join(user_id, user_data, payload.get("code"), name)
        if status == "ok":
            analytics.capture(analytics.Event.LEAGUE_JOINED, user_id=user_id, properties={"surface": "miniapp"})
        return {"status": status, "league": league}
    if action == "leave":
        status, league = league_rules.leave(user_id, payload.get("code"))
        return {"status": status, "league": league}

    raise HTTPException(status_code=400, detail="azione sconosciuta")


@router.post("/app/api/shop")
def webapp_shop(payload: dict = Body(default={})):
    """La vetrina: la **stessa** che disegna il comando /shop (domains/shop/service.py)."""
    user_id, user_data = _webapp_user(payload)
    _require_feature(Flag.SHOP, user_id)
    analytics.capture(analytics.Event.SHOP_VIEWED, user_id=user_id, properties={"surface": "miniapp"})
    return shop.catalogue_for(user_data, _webapp_language(user_data))


@router.post("/app/api/shop/buy")
async def webapp_shop_buy(request: Request, payload: dict = Body(default={})):
    """Il link della fattura da aprire con `openInvoice` dentro la mini app.

    La pagina non riceve mai un prezzo da mandare indietro: qui si guarda solo **quale**
    oggetto vuole, e quanto costa lo dice il catalogo. Se il prezzo arrivasse dal client,
    chiunque potrebbe comprare la collezione completa per una Stella."""
    user_id, user_data = await run_in_threadpool(_webapp_user, payload)
    if not await run_in_threadpool(feature_flags.is_enabled, Flag.SHOP, user_id=user_id):
        # Prima di creare la fattura: nessun link, quindi nessun addebito possibile.
        observability.log_event("payment.invoice.refused", reason="feature_disabled")
        analytics.capture(analytics.Event.SHOP_PURCHASE_REFUSED, user_id=user_id, properties={
            "surface": "miniapp", "reason": "feature_disabled", "success": False,
        })
        raise FeatureDisabled(Flag.SHOP)
    item_id = payload.get("item")
    status = shop.purchase_status(user_data, item_id)
    if status != "ok":
        observability.log_event("payment.invoice.refused", reason=status,
                                item_id=item_id if isinstance(item_id, str) else None)
        analytics.capture(analytics.Event.SHOP_PURCHASE_REFUSED, user_id=user_id, properties={
            "surface": "miniapp", "reason": status, "success": False,
            "item_id": item_id if isinstance(item_id, str) else None,
        })
        return {"status": status}

    item = shop.get_item(item_id)
    name, description = shop.localize(item, _webapp_language(user_data))
    price = shop.price_for(user_data, item)
    link = await telegram(request).application.bot.create_invoice_link(
        title=name,
        description=description[:255],
        payload=shop.payment_payload(user_id, user_data, item),
        # Le Stelle non passano da un fornitore esterno: il token e' vuoto per definizione.
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=name, amount=price)],
    )
    observability.log_event("payment.invoice.created", item_id=item_id, amount=price)
    # Intent, not completion: see successful_payment_callback (handlers/shop_handler.py) for
    # the one authoritative `shop_purchase_completed`, common to both surfaces.
    analytics.capture(analytics.Event.SHOP_PURCHASE_STARTED, user_id=user_id, properties={
        "surface": "miniapp", "item_id": item_id, "item_kind": item.get("kind"), "price_stars": price,
    })
    return {"status": "ok", "link": link}


@router.post("/app/api/shop/equip")
def webapp_shop_equip(payload: dict = Body(default={})):
    """Indossa un oggetto gia' posseduto. La regola sta in domains/shop/service.py: qui si passa
    solo l'utente autenticato dalla firma di initData, mai un id arrivato dal client."""
    user_id, user_data = _webapp_user(payload)
    _require_feature(Flag.SHOP, user_id)
    item_id = payload.get("item")
    status = shop.equip(user_id, user_data, item_id)
    if status != "ok":
        return {"status": status}
    equipped_item = shop.get_item(item_id) if isinstance(item_id, str) else None
    analytics.capture(analytics.Event.SHOP_ITEM_EQUIPPED, user_id=user_id, properties={
        "surface": "miniapp", "item_id": item_id if isinstance(item_id, str) else None,
        "item_kind": equipped_item.get("kind") if equipped_item else None,
    })
    return {"status": "ok", "cosmetics": shop.appearance(
        firebase_service.get_user_data(user_id), _webapp_language(user_data)
    )}


@router.post("/app/api/shop/look")
def webapp_shop_look(payload: dict = Body(default={})):
    user_id, user_data = _webapp_user(payload)
    _require_feature(Flag.SHOP, user_id)
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


@router.post("/app/api/shop/history")
def webapp_shop_history(payload: dict = Body(default={})):
    # Mai dietro il flag `shop`: e' da qui che si recupera il charge id per un rimborso.
    user_id, user_data = _webapp_user(payload)
    lang = _webapp_language(user_data)
    rows = []
    for purchase in firebase_service.get_user_purchases(user_id):
        item = shop.get_item(purchase.get("item_id"))
        rows.append({"name": shop.localize(item, lang)[0] if item else purchase.get("item_id", ""),
                     "day": purchase.get("day", ""), "stars": purchase.get("stars", 0),
                     "refunded": bool(purchase.get("refunded")), "charge_id": purchase.get("charge_id", "")})
    return {"purchases": rows, "support_url": f"https://t.me/{config.BOT_USERNAME}" if config.BOT_USERNAME else ""}


@router.post("/app/api/support/report")
async def webapp_report(request: Request, payload: dict = Body(default={})):
    """Segnala un errore in una carriera o nella mini app: stesso canale di /paysupport (un
    messaggio agli admin), ma per bug e dati, non per acquisti - vedi /admin_report_reply."""
    user_id, user_data = await run_in_threadpool(_webapp_user, payload, 5)
    body = (payload.get("message") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="messaggio vuoto")
    if not config.ADMIN_TELEGRAM_IDS:
        observability.log_event("support.report.unavailable", logging.ERROR)
        raise HTTPException(status_code=503, detail="assistenza non disponibile")

    name = user_data.get("first_name") or "—"
    text = (
        "🛠 Segnalazione dalla mini app\n"
        f"Utente: {name}\nTelegram ID: {user_id}\n\n{body[:3500]}\n\n"
        f"Rispondi: /admin_report_reply {user_id} <messaggio>"
    )
    bot = telegram(request).application.bot
    try:
        for admin_id in config.ADMIN_TELEGRAM_IDS:
            await bot.send_message(chat_id=admin_id, text=text)
    except Exception as exc:
        observability.log_event("support.report.failed", logging.ERROR, exc_info=exc)
        raise HTTPException(status_code=502, detail="invio non riuscito") from None
    return {"status": "ok"}


@router.post("/app/api/card")
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


@router.post("/app/api/trophies/pin")
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
