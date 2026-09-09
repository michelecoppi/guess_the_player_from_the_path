"""Il negozio in chat, e i due momenti del pagamento in Stelle.

Perche' un negozio anche in chat, visto che c'e' la mini app: perche' meta' delle persone il
bot lo usano solo in chat, e un negozio che si apre solo dentro la mini app sarebbe un
negozio che quella meta' non vede mai. La vetrina e' la stessa (services/shop.py): qui si
disegna con dei bottoni, li' con dell'HTML.

Come funziona un pagamento in Stelle, nell'ordine:

1. si manda una fattura con `currency="XTR"` e `provider_token=""` - le Stelle non passano da
   un fornitore di pagamento esterno, quindi il token non c'e' proprio;
2. Telegram chiede al bot il permesso di incassare (`PreCheckoutQuery`), e vuole una risposta
   **entro dieci secondi**: e' l'ultimo momento in cui si puo' dire di no, e infatti e' li'
   che si controlla che l'oggetto esista e che l'utente non ce l'abbia gia';
3. a incasso avvenuto arriva un messaggio con `successful_payment`: qui si consegna, e non si
   rifiuta piu' niente (i soldi sono gia' presi).

Il punto 3 puo' arrivare **due volte**: se il webhook non risponde in tempo Telegram
rispedisce l'update. La consegna e' idempotente sull'id della transazione
(`firebase_service.deliver_purchase`), quindi la seconda volta non fa niente.
"""
import logging

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_IDS, BOT_TOKEN
from handlers.keyboards import language_for, legal_buttons
from services import firebase_service, shop
from services.i18n import t

CALLBACK_PREFIX = "shop_"
CURRENCY = "XTR"

# Un'icona per ogni scaffale: in una lista di bottoni il simbolo si legge prima della parola.
SECTION_ICONS = {
    "theme": "🎨",
    "frame": "🖼",
    "title": "🏷",
    "badge": "🎖",
    "squares": "🟩",
    "bundle": "🎁",
}


# ---------------------------------------------------------------------------
# La vetrina
# ---------------------------------------------------------------------------

def _user(update):
    user_id = update.effective_user.id
    return user_id, firebase_service.get_user_data(user_id)


def _main_view(lang, user):
    owned = len(shop.owned_ids(user) - shop.free_ids())
    text = t(lang, "shop.title") + "\n\n" + t(lang, "shop.fair_play")
    if owned:
        text += "\n\n" + t(lang, "shop.owned_count", count=owned)

    rows = [
        [InlineKeyboardButton(
            f"{SECTION_ICONS[kind]} {t(lang, f'shop.section_{kind}')}",
            callback_data=f"{CALLBACK_PREFIX}kind_{kind}",
        )]
        for kind in shop.KINDS
    ]
    rows.append([InlineKeyboardButton(
        f"{SECTION_ICONS['bundle']} {t(lang, 'shop.section_bundle')}",
        callback_data=f"{CALLBACK_PREFIX}kind_bundle",
    )])
    if legal_buttons(lang):
        rows.append(legal_buttons(lang))
    return text, InlineKeyboardMarkup(rows)


def _section_view(lang, user, kind):
    """Uno scaffale: un bottone per oggetto, con il prezzo o il segno di chi ce l'ha gia'.

    Gli oggetti gratuiti restano in lista di proposito: sono il modo di **tornare indietro**
    a com'era prima, e un negozio che non lascia togliere quello che ha venduto e' un
    negozio che si fa disinstallare."""
    items = shop.bundles() if kind == "bundle" else shop.items_of_kind(kind)
    worn = shop.equipped(user)
    owned = shop.owned_ids(user)

    rows = []
    for item in items:
        if item.get("locked"):
            continue   # si vede solo dentro il pacchetto che lo contiene
        name, _ = shop.localize(item, lang)
        granted = shop.grants_of(item)
        has_it = all(one in owned for one in granted)
        if worn.get(kind) == item["id"]:
            label = f"👕 {name}"
        elif has_it:
            label = f"✅ {name}"
        elif item.get("achievement"):
            label = f"🔒 {name}"
        else:
            label = f"{name} · {shop.price_for(user, item)} ⭐"
        rows.append([InlineKeyboardButton(label, callback_data=f"{CALLBACK_PREFIX}item_{item['id']}")])

    rows.append([InlineKeyboardButton(t(lang, "shop.back"), callback_data=f"{CALLBACK_PREFIX}home")])
    return t(lang, f"shop.section_{kind}_intro"), InlineKeyboardMarkup(rows)


def _item_view(lang, user, item):
    """La scheda di un oggetto: cos'e', quanto costa, e l'unico bottone che ha senso adesso
    (comprarlo se non ce l'ha, indossarlo se ce l'ha, niente se ce l'ha gia' addosso)."""
    name, description = shop.localize(item, lang)
    kind = item.get("kind")
    text = f"<b>{name}</b>\n{description}"

    if kind == "bundle":
        pieces = [shop.localize(shop.get_item(one), lang)[0] for one in shop.grants_of(item)]
        text += "\n\n" + t(lang, "shop.bundle_contains", items=", ".join(pieces))

    rows = []
    if item.get("achievement") and item["id"] not in shop.owned_ids(user):
        goal = item["achievement"]
        text += "\n\n" + t(lang, "shop.earned_progress", progress=user.get(goal["field"], 0), target=goal["target"])
        rows.append([InlineKeyboardButton(t(lang, "shop.back"), callback_data=f"{CALLBACK_PREFIX}kind_{kind}")])
        return text, InlineKeyboardMarkup(rows)
    if kind == "bundle" and shop.price_for(user, item) < item["price"] and shop.price_for(user, item):
        missing = [shop.localize(shop.get_item(one), lang)[0] for one in shop.grants_of(item) if one not in shop.owned_ids(user)]
        text += "\n\n" + t(lang, "shop.partial", items=", ".join(missing))
    status = shop.purchase_status(user, item["id"])
    if status == "ok":
        text += "\n\n" + t(lang, "shop.price", price=shop.price_for(user, item))
        rows.append([InlineKeyboardButton(
            t(lang, "shop.buy_button", price=shop.price_for(user, item)),
            callback_data=f"{CALLBACK_PREFIX}buy_{item['id']}",
        )])
    elif kind != "bundle":
        if shop.equipped(user).get(kind) == item["id"]:
            text += "\n\n" + t(lang, "shop.worn_tag")
        else:
            rows.append([InlineKeyboardButton(
                t(lang, "shop.equip_button"), callback_data=f"{CALLBACK_PREFIX}equip_{item['id']}"
            )])
    else:
        text += "\n\n" + t(lang, "shop.owned_tag")
        if shop.can_wear_bundle(item):
            rows.append([InlineKeyboardButton(t(lang, "shop.equip_all"),
                         callback_data=f"{CALLBACK_PREFIX}equip_{item['id']}")])

    back_kind = kind if kind in shop.KINDS else "bundle"
    if legal_buttons(lang):
        rows.append(legal_buttons(lang))
    rows.append([InlineKeyboardButton(t(lang, "shop.back"), callback_data=f"{CALLBACK_PREFIX}kind_{back_kind}")])
    return text, InlineKeyboardMarkup(rows)


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = language_for(update)
    _, user = _user(update)
    text, keyboard = _main_view(lang, user)
    await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sfogliare il negozio modifica **lo stesso** messaggio invece di mandarne uno nuovo:
    sono passi dentro una vetrina, non risposte a domande diverse."""
    query = update.callback_query
    action = query.data[len(CALLBACK_PREFIX):]
    lang = language_for(update)
    user_id, user = _user(update)

    if action == "home":
        await query.answer()
        text, keyboard = _main_view(lang, user)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if action.startswith("kind_"):
        await query.answer()
        text, keyboard = _section_view(lang, user, action[len("kind_"):])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if action.startswith("item_"):
        item = shop.get_item(action[len("item_"):])
        if not item:
            await query.answer(t(lang, "shop.error_unknown_item"), show_alert=True)
            return
        await query.answer()
        text, keyboard = _item_view(lang, user, item)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if action.startswith("equip_"):
        item_id = action[len("equip_"):]
        status = shop.equip(user_id, user, item_id)
        if status != "ok":
            await query.answer(t(lang, f"shop.error_{status}"), show_alert=True)
            return
        await query.answer(t(lang, "shop.equipped_ok"))
        # Si rilegge l'utente: il messaggio deve mostrare la maglietta sull'oggetto giusto.
        _, user = _user(update)
        text, keyboard = _item_view(lang, user, shop.get_item(item_id))
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if action.startswith("buy_"):
        await _send_invoice(update, context, lang, user, action[len("buy_"):])
        return

    await query.answer()


# ---------------------------------------------------------------------------
# Pagamento
# ---------------------------------------------------------------------------

async def _send_invoice(update, context, lang, user, item_id):
    query = update.callback_query
    item = shop.get_item(item_id)
    status = shop.purchase_status(user, item_id)
    if status != "ok":
        await query.answer(t(lang, f"shop.error_{status}"), show_alert=True)
        return

    await query.answer()
    name, description = shop.localize(item, lang)
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=name,
        # Telegram taglia la descrizione a 255 caratteri: meglio tagliarla noi che vederla
        # troncata a meta' parola.
        description=description[:255],
        payload=shop.payment_payload(update.effective_user.id, user, item),
        # Le Stelle non passano da un fornitore esterno: il token e' vuoto per definizione,
        # non e' una configurazione che manca.
        provider_token="",
        currency=CURRENCY,
        prices=[LabeledPrice(label=name, amount=shop.price_for(user, item))],
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """L'ultimo momento in cui si puo' dire di no, e Telegram aspetta al massimo dieci
    secondi: qui si fanno solo controlli che costano una lettura, niente scritture.

    Il caso che conta e' "ce l'ha gia'": fra l'apertura del negozio e il pagamento puo'
    esserci passata in mezzo la stessa cosa comprata dalla mini app, o un pacchetto che
    conteneva questo pezzo. Incassare per non consegnare niente sarebbe una fregatura, e il
    rimborso lo dovremmo fare a mano."""
    query = update.pre_checkout_query
    item_id, user_id = shop.parse_payload(query.invoice_payload)
    lang = language_for(update)

    if not item_id or user_id != query.from_user.id:
        logging.warning(f"[SHOP] Pre-checkout con payload inatteso: {query.invoice_payload!r}")
        await query.answer(ok=False, error_message=t(lang, "shop.error_unknown_item"))
        return

    user_data = firebase_service.get_user_data(user_id)
    status = shop.purchase_status(user_data, item_id)
    if status != "ok":
        await query.answer(ok=False, error_message=t(lang, f"shop.error_{status}"))
        return

    quote = shop.payment_quote(query.invoice_payload)
    expected = shop.price_for(user_data, shop.get_item(item_id))
    missing = set(shop.grants_of(shop.get_item(item_id))) - shop.owned_ids(user_data)
    if query.currency != CURRENCY or query.total_amount != expected or (quote and (
        quote["price"] != expected or set(quote["granted"]) != missing
    )):
        await query.answer(ok=False, error_message=t(lang, "shop.error_price_changed"))
        return
    reservation = firebase_service.reserve_checkout(user_id, query.id,
        (user_data.get("cosmetics") or {}).get("owned", []))
    if reservation != "ok":
        await query.answer(ok=False, error_message=t(lang, f"shop.error_{reservation}"))
        return
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Incasso avvenuto: qui si consegna e basta.

    Non si rifiuta piu' niente, nemmeno un payload strano: le Stelle sono gia' state prese, e
    l'unica cosa peggiore di consegnare qualcosa di inatteso e' non consegnare niente. Un
    payload che non riconosciamo finisce nei log come errore da guardare a mano."""
    payment = update.effective_message.successful_payment
    lang = language_for(update)
    user_id = update.effective_user.id

    # Chi paga puo' non avere mai fatto /start (una fattura si apre anche da un link): senza
    # documento utente non c'e' dove scrivere quello che ha comprato.
    firebase_service.save_user(user_id, update.effective_user.first_name, lang)

    item_id, _ = shop.parse_payload(payment.invoice_payload)
    item = shop.get_item(item_id)
    if item is None:
        logging.error(
            f"[SHOP] Pagamento {payment.telegram_payment_charge_id} di {user_id} non consegnato: "
            f"payload {payment.invoice_payload!r}"
        )
        await update.effective_message.reply_text(t(lang, "shop.delivery_problem"))
        return

    quote = shop.payment_quote(payment.invoice_payload)
    if not shop.deliver(user_id, item_id, payment.telegram_payment_charge_id, payment.total_amount,
                        granted=quote["granted"] if quote else None):
        # Update rispedito da Telegram: era gia' consegnato, e un secondo "grazie" farebbe
        # solo pensare a un secondo addebito.
        return

    name, _ = shop.localize(item, lang)
    await update.effective_message.reply_text(
        t(lang, "shop.thanks", item=name) + "\n\n" + t(lang, "shop.refund_hint"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Rimborso (amministratori)
# ---------------------------------------------------------------------------

async def _refund_star_payment(user_id, charge_id):
    """`refundStarPayment` a mano: python-telegram-bot 20.7 non ha ancora il metodo, e
    aggiornare la libreria per una chiamata sola vorrebbe dire ricontrollare tutto il resto."""
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/refundStarPayment",
            json={"user_id": user_id, "telegram_payment_charge_id": str(charge_id)},
        )
    body = response.json()
    return bool(body.get("ok")), body.get("description", "")


async def admin_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin_refund <charge_id> - ridà le Stelle e ritira quello che erano servite a comprare.

    Le due cose vanno insieme: rimborsare senza ritirare regala l'oggetto, ritirare senza
    rimborsare e' peggio ancora. Se Telegram rifiuta il rimborso non si tocca niente."""
    if update.effective_user.id not in ADMIN_TELEGRAM_IDS:
        await update.message.reply_text("⛔ Comando riservato agli amministratori.")
        return

    args = getattr(context, "args", None) or []
    if not args:
        await update.message.reply_text("Uso: /admin_refund <charge_id>")
        return

    charge_id = args[0]
    purchase = firebase_service.get_purchase(charge_id)
    if not purchase:
        await update.message.reply_text(f"Nessun acquisto con id {charge_id}.")
        return
    if purchase.get("refunded"):
        await update.message.reply_text(f"L'acquisto {charge_id} risulta gia' rimborsato.")
        return

    ok, error = await _refund_star_payment(purchase["user_id"], charge_id)
    if not ok:
        await update.message.reply_text(f"Telegram ha rifiutato il rimborso: {error}")
        return

    revoked = firebase_service.revoke_purchase(charge_id)
    await update.message.reply_text(
        f"Rimborsate {purchase.get('stars')} ⭐ a {purchase['user_id']}.\n"
        f"Ritirati: {', '.join(revoked) if revoked else 'niente (li aveva anche da altri acquisti)'}"
    )
