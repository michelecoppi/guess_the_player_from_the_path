"""Telegram webhook and internal workers: `POST /webhook`, `POST /internal/*`.

The webhook only authenticates and enqueues on Cloud Tasks; the workers authenticate with
their shared secrets and run the work. What needs the bot comes from the injected
`TelegramBridge`. Moved verbatim from bot.py by #110 (docs/runtime-hardening.md).
"""
import asyncio
import hmac
import logging
from time import perf_counter

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from telegram import Update

import config
from apps.api.bridge import telegram
from services import alerts, monthly_closure, observability, performance, task_queue, work_receipts

router = APIRouter()


@router.post("/webhook")
async def webhook(req: Request):
    supplied = req.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not config.WEBHOOK_SECRET or not hmac.compare_digest(supplied.encode(), config.WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        data = await req.json()
        if not isinstance(data, dict) or type(data.get("update_id")) is not int:
            raise ValueError("invalid update_id")
        Update.de_json(data, telegram(req).application.bot)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid update") from None
    await run_in_threadpool(task_queue.enqueue, "/internal/telegram-update", data,
                            f"telegram-{data['update_id']}")
    return {"status": "ok"}


@router.post("/internal/daily-job")
async def trigger_daily_job(request: Request, x_cron_secret: str = Header(default=None)):
    """Chiamato da Cloud Scheduler a mezzanotte: su Cloud Run non c'e' un processo sempre
    acceso che possa tenere un cron interno, quindi il trigger arriva da fuori via HTTP."""
    if not config.GENERATION_SECRET or not hmac.compare_digest((x_cron_secret or "").encode(), config.GENERATION_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    await telegram(request).run_daily_job()
    return {"status": "ok"}


def _require_task_secret(supplied):
    if not config.TASK_SECRET or not hmac.compare_digest((supplied or "").encode(), config.TASK_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/internal/telegram-update")
async def consume_telegram_update(request: Request, payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    if type(payload.get("update_id")) is not int:
        raise HTTPException(status_code=400, detail="Invalid update")
    application = telegram(request).application
    update = Update.de_json(payload, application.bot)
    with observability.bind(update_id=update.update_id, **observability.describe_update(update)):
        return await _consume_update(application, update)


async def _consume_update(application, update):
    key = f"telegram-{update.update_id}"
    user = update.effective_user
    state = await run_in_threadpool(work_receipts.claim, key, serial_key=str(user.id) if user else None)
    if state == "busy":
        raise HTTPException(status_code=503, detail="Update in progress")
    if state == "uncertain":
        observability.log_event("telegram.update.uncertain", logging.ERROR, status="uncertain")
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
        started = perf_counter()
        async with asyncio.timeout(150):
            await application.process_update(update)
        # La durata del solo handler, con i campi dell'update gia' legati (comando, tipo): la
        # richiesta intera comprende anche ricevuta e coda, e non dice quale comando e' lento.
        usage = performance.current_usage()
        observability.log_event(
            "telegram.update.completed", duration_ms=round((perf_counter() - started) * 1000, 1),
            **(usage.fields() if usage else {}),
        )
        await run_in_threadpool(work_receipts.finish, key)
    return {"status": "ok"}


@router.post("/internal/broadcast")
async def consume_broadcast(request: Request, payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    return await telegram(request).broadcast_batch(payload["day"], payload.get("cursor"))


@router.post("/internal/monthly-close")
def consume_monthly_close(payload: dict, x_task_secret: str = Header(default=None)):
    _require_task_secret(x_task_secret)
    return monthly_closure.close_batch(payload["day"], payload.get("cursor"))
