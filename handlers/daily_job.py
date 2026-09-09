"""Job di mezzanotte: genera i contenuti mancanti, avvisa gli utenti, chiude eventi e mese.

Non c'e' piu' nessun azzeramento di contatori qui dentro: i tentativi giornalieri sono
azzerati "da soli" perche' ogni documento porta il giorno a cui si riferisce
(`last_played_day`). Il job puo' quindi saltare - o girare in ritardo - senza che il gioco
del giorno dopo risulti sballato.
"""
import asyncio
import logging

from telegram import Bot
from telegram.error import Forbidden, RetryAfter

from config import ADMIN_TELEGRAM_IDS, BOT_TOKEN
from handlers.keyboards import app_keyboard
from services import broadcast_store, firebase_service, monthly_closure, task_queue, work_receipts
from services.daily_challenge import invalidate as invalidate_daily_cache
from services.daily_generator import ensure_daily_buffer
from services.daily_stats import solve_percent
from services.dates import now_italy, shift_iso, to_display, today_iso
from services.event_generator import maybe_generate_event
from services.i18n import DEFAULT_LANGUAGE, content_text, month_label, t

_bot = None


def get_bot():
    """Il client Telegram si crea al primo utilizzo, come il client Firestore: cosi' il
    modulo si puo' importare (e testare) senza avere BOT_TOKEN configurato."""
    global _bot
    if _bot is None:
        _bot = Bot(BOT_TOKEN)
    return _bot


async def update_daily_challenge():
    now = now_italy()
    today = today_iso()
    yesterday = shift_iso(today, -1)

    payload = await asyncio.to_thread(broadcast_store.get_job, today)
    if payload is None:
        await asyncio.to_thread(ensure_daily_buffer)
        await asyncio.to_thread(maybe_generate_event, now)
        invalidate_daily_cache()
        finished_event = await asyncio.to_thread(firebase_service.get_event_trophy_day, yesterday)
        if finished_event:
            await asyncio.to_thread(firebase_service.update_users_trophies, finished_event)
        monthly_result = await asyncio.to_thread(monthly_closure.prepare, now) if now.day == 1 else None
        payload = {
            "reference_day": yesterday,
            # Il nome dell'evento chiuso viaggia nel payload perche' il riepilogo agli admin
            # lo scrive l'ultima pagina del broadcast, che gira in un'altra richiesta e non
            # ha piu' sotto mano quello che e' stato deciso qui.
            "finished_event_name": (finished_event or {}).get("name", ""),
            "yesterday_player": await asyncio.to_thread(firebase_service.get_display_name_for_day, yesterday),
            "stats": list(await asyncio.to_thread(firebase_service.get_daily_stats, yesterday)),
            "current_event": await asyncio.to_thread(firebase_service.get_current_event, today),
            "monthly_result": monthly_result,
        }
        payload = await asyncio.to_thread(broadcast_store.save_job, today, payload)
    monthly = payload.get("monthly_result") is not None
    path = "/internal/monthly-close" if monthly else "/internal/broadcast"
    key = f"monthly-{today}-start" if monthly else f"broadcast-{today}-start"
    await asyncio.to_thread(task_queue.enqueue, path, {"day": today}, key, broadcast=True)
    return {"day": today, "status": "queued"}


async def broadcast_batch(day, cursor=None):
    payload = await asyncio.to_thread(broadcast_store.get_job, day)
    if payload is None:
        raise ValueError("Daily payload missing")
    users, next_cursor = await asyncio.to_thread(broadcast_store.page, payload["reference_day"], cursor)
    # Argomenti espliciti e non `**payload`: sul documento del giorno finiscono anche campi
    # di servizio (il totale inviato), e passarli tutti farebbe fallire la firma.
    sent, errors = await _broadcast(
        payload["reference_day"], payload.get("yesterday_player"), payload.get("current_event"),
        payload.get("monthly_result"), tuple(payload.get("stats") or (0, 0)),
        users=users, notification_day=day,
    )
    # Prima del controllo sugli errori: quello che e' partito e' partito, e al retry le
    # ricevute saltano questi utenti, quindi il totale non conta due volte nessuno.
    await asyncio.to_thread(broadcast_store.add_sent, day, sent)
    if errors:
        raise RuntimeError("Transient broadcast failure; retry this page")
    if next_cursor:
        await asyncio.to_thread(task_queue.enqueue, "/internal/broadcast", {"day": day, "cursor": next_cursor},
                                f"broadcast-{day}-{next_cursor}", broadcast=True)
    else:
        await _report_completion(day, payload)
    return {"sent": sent, "next_cursor": next_cursor}


async def _report_completion(day, payload):
    """Il riepilogo di fine giornata agli admin, l'unico segnale che il giro e' finito.

    Lo manda l'ultima pagina, non il trigger di mezzanotte: fra i due ci sono N richieste
    separate, e un "fatto" scritto prima del primo invio non direbbe niente."""
    total = (await asyncio.to_thread(broadcast_store.get_job, day) or {}).get("sent_total", 0)
    monthly = payload.get("monthly_result")
    await _notify_admins(
        f"✅ Giornata {to_display(day)} aggiornata. Notifiche inviate: {total}."
        + (f"\n🏆 Trofei assegnati per {payload['finished_event_name']}." if payload.get("finished_event_name") else "")
        + (f"\n📅 Risultati stagione {monthly['month_name']} {monthly['year']}." if monthly else "")
    )


async def _broadcast(reference_day, yesterday_player, current_event, monthly_result, stats=(0, 0), *, users=None, notification_day=None):
    """`monthly_result` (se non None) e' {'month_name', 'year', 'winners'}: il podio viene
    reso nella lingua di ciascun destinatario, non e' piu' un testo unico precomposto.

    `stats` e' (giocatori, risolutori) della giornata appena chiusa: diventa la riga "l'ha
    indovinato il 41%". Qui la giornata e' chiusa e la percentuale e' definitiva, quindi
    dirla non anticipa niente a nessuno."""
    broadcast_users = users if users is not None else await asyncio.to_thread(firebase_service.get_broadcast_users, reference_day)

    sent = 0
    errors = 0
    for user in broadcast_users:
        chat_id = user["chat_id"]
        receipt = None
        if notification_day:
            if (user.get("last_notification_day") or "") >= notification_day:
                continue
            receipt = f"notify-{notification_day}-{user['user_id']}"
            status = await asyncio.to_thread(work_receipts.claim, receipt)
            if status == "busy":
                errors += 1
                continue
            if status != "claimed":
                if status == "uncertain":
                    logging.error("Notification delivery uncertain: %s", receipt)
                continue
        lang = user.get("language", DEFAULT_LANGUAGE)
        player_label = yesterday_player or t(lang, "job.player_fallback")

        if user.get("has_guessed_today"):
            text = t(lang, "job.congrats", player=player_label)
        else:
            text = t(lang, "job.missed", player=player_label)

        percent = solve_percent(*stats)
        if percent is not None:
            text += t(lang, "job.rate_line", percent=percent)

        if current_event:
            event_name = content_text(current_event, "name", lang, default=t(lang, "job.unknown_event"))
            text += t(lang, "job.event_mention", event_name=event_name)
        if monthly_result:
            month = month_label(lang, monthly_result["month_name"])
            text += "\n\n" + t(lang, "job.monthly_results_title", month=month, year=monthly_result["year"])
            for winner in monthly_result["winners"]:
                text += t(
                    lang, "job.monthly_winner_line",
                    position=winner["position"], username=winner["username"], points=winner["monthly_points"],
                )
        text += t(lang, "job.feedback_line")
        keyboard = app_keyboard(lang)
        if keyboard:
            text += "\n\n" + t(lang, "app.daily_invite")

        try:
            await get_bot().send_message(chat_id=chat_id, text=text, **({"reply_markup": keyboard} if keyboard else {}))
            if receipt:
                await asyncio.to_thread(broadcast_store.mark_sent, user["user_id"], notification_day)
                await asyncio.to_thread(work_receipts.finish, receipt)
            sent += 1
            await asyncio.sleep(0.05)
        except Forbidden:
            if receipt:
                await asyncio.to_thread(work_receipts.finish, receipt)
                await asyncio.to_thread(firebase_service.set_user_notifications, user["user_id"], chat_id, False)
        except RetryAfter:
            if receipt:
                await asyncio.to_thread(work_receipts.release, receipt)
            errors += 1
        except Exception:
            errors += 1
            logging.error("Notification failed for user %s; delivery may be uncertain", chat_id)

    return sent, errors


async def _notify_admins(text):
    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await get_bot().send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logging.info(f"Impossibile avvisare l'admin {admin_id}: {e}")


def handle_monthly_reset(today):
    return monthly_closure.close(today)
