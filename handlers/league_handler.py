"""Leghe private: una classifica fra amici, dentro lo stesso gioco.

E' la parte social che mancava: il bot era tutto "io contro la classifica mondiale", dove
dopo una settimana sai gia' che non prendi nessuno. In una lega da otto persone invece la
posizione cambia ogni giorno.

Scelte che vale la pena spiegare:

- i punti di una lega stanno sul documento del **membro** (come i partecipanti agli eventi),
  aggiornati quando l'utente indovina: cosi' la classifica e' una query ordinata invece di
  una lettura per ogni iscritto;
- si contano solo i punti fatti **da quando si e' entrati**: entrare in una lega vecchia non
  ti mette ultimo per sempre, e chi ha giocato per mesi non parte gia' vincitore;
- l'elenco delle leghe di un utente e' un array sul suo documento (`leagues`), quindi
  aggiornare i punti non richiede nessuna query per sapere dove scriverli.
"""
import asyncio
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import BOT_USERNAME
from services import firebase_service
from services import leagues as league_rules
from services.i18n import resolve_language, t
from services.leagues import MAX_LEAGUES_PER_USER, MAX_MEMBERS, MAX_NAME_LENGTH

CALLBACK_PREFIX = "lg_"
DEEP_LINK_PREFIX = "lega_"

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def invite_link(code):
    if not BOT_USERNAME:
        return ""
    return f"https://t.me/{BOT_USERNAME}?start={DEEP_LINK_PREFIX}{code}"


def _lang_for(update: Update, user_data=None):
    if user_data and user_data.get("language"):
        return user_data["language"]
    return resolve_language(getattr(update.effective_user, "language_code", None))


def _leagues_keyboard(leagues, lang):
    rows = [
        [InlineKeyboardButton(league["name"], callback_data=f"{CALLBACK_PREFIX}{league['code']}")]
        for league in leagues
    ]
    return InlineKeyboardMarkup(rows) if rows else None


def format_leaderboard(league, members, lang, viewer_id=None):
    message = t(lang, "league.leaderboard_title", name=league.get("name", "?"), code=league.get("code", "?"))
    if not members:
        return message + t(lang, "league.leaderboard_empty")

    for position, member in enumerate(members, start=1):
        medal = MEDALS.get(position, f"{position}.")
        highlight = t(lang, "top.you_tag") if member.get("telegram_id") == viewer_id else ""
        message += f"{medal} {member.get('name', '?')}{highlight} - {member.get('points', 0)} {t(lang, 'top.points_suffix')}\n"
    return message


async def leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lega: le leghe di cui fai parte, con un bottone per ognuna."""
    user_id = update.effective_user.id
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user_id))
    lang = _lang_for(update, user_data)

    if not user_data:
        await update.effective_message.reply_text(t(lang, "league.not_registered"))
        return

    codes = user_data.get("leagues", [])
    found = (await asyncio.to_thread(lambda: [league for league in (firebase_service.get_league(code) for code in codes) if league]))

    if not found:
        await update.effective_message.reply_text(t(lang, "league.none"), parse_mode="HTML")
        return

    await update.effective_message.reply_text(
        t(lang, "league.intro"),
        reply_markup=_leagues_keyboard(found, lang),
        parse_mode="HTML",
    )


async def league_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user.id))
    lang = _lang_for(update, user_data)
    message = update.effective_message

    if not user_data:
        await message.reply_text(t(lang, "league.not_registered"))
        return

    name = " ".join(context.args).strip() if context.args else ""
    status, code = (await asyncio.to_thread(league_rules.create, user.id, user_data, name, user.first_name))

    if status == "ok":
        await message.reply_text(
            t(lang, "league.created", name=name, code=code, link=invite_link(code) or code),
            parse_mode="HTML",
        )
        return
    if status == "no_name":
        await message.reply_text(t(lang, "league.usage_create"), parse_mode="HTML")
        return
    if status == "name_too_long":
        await message.reply_text(t(lang, "league.name_too_long", max=MAX_NAME_LENGTH))
        return
    if status == "limit":
        await message.reply_text(t(lang, "league.limit_reached", max=MAX_LEAGUES_PER_USER), parse_mode="HTML")
        return

    await message.reply_text(t(lang, "league.not_found", code="?"), parse_mode="HTML")


async def league_join(update: Update, context: ContextTypes.DEFAULT_TYPE, code=None):
    user = update.effective_user
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user.id))
    lang = _lang_for(update, user_data)
    message = update.effective_message

    if not user_data:
        await message.reply_text(t(lang, "league.not_registered"))
        return

    code = league_rules.normalize_code(code or (context.args[0] if context.args else ""))
    status, league = (await asyncio.to_thread(league_rules.join, user.id, user_data, code, user.first_name))

    if status == "ok":
        await message.reply_text(t(lang, "league.joined", name=league.get("name", code)), parse_mode="HTML")
        return
    if status == "no_code":
        await message.reply_text(t(lang, "league.usage_join"), parse_mode="HTML")
        return
    if status == "limit":
        await message.reply_text(t(lang, "league.limit_reached", max=MAX_LEAGUES_PER_USER), parse_mode="HTML")
        return
    if status == "already_member":
        await message.reply_text(t(lang, "league.already_member"))
        return
    if status == "full":
        await message.reply_text(t(lang, "league.full", max=MAX_MEMBERS))
        return

    await message.reply_text(t(lang, "league.not_found", code=code), parse_mode="HTML")


async def league_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = (await asyncio.to_thread(firebase_service.get_user_data, user_id))
    lang = _lang_for(update, user_data)
    message = update.effective_message

    code = league_rules.normalize_code(context.args[0] if context.args else "")
    status, league = (await asyncio.to_thread(league_rules.leave, user_id, code))

    if status == "ok":
        await message.reply_text(t(lang, "league.left", name=league.get("name", code)), parse_mode="HTML")
        return
    if status == "no_code":
        await message.reply_text(t(lang, "league.usage_leave"), parse_mode="HTML")
        return
    if status == "not_member":
        await message.reply_text(t(lang, "league.not_member"))
        return

    await message.reply_text(t(lang, "league.not_found", code=code), parse_mode="HTML")


async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    lang = _lang_for(update, (await asyncio.to_thread(firebase_service.get_user_data, user_id)))
    code = query.data[len(CALLBACK_PREFIX):]

    league = (await asyncio.to_thread(firebase_service.get_league, code))
    if not league:
        await query.message.reply_text(t(lang, "league.not_found", code=code), parse_mode="HTML")
        return

    members = (await asyncio.to_thread(firebase_service.get_league_leaderboard, code))
    keyboard = None
    link = invite_link(code)
    if link:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "league.button_invite"), url=_share_url(link, league))]])

    await query.message.reply_text(
        format_leaderboard(league, members, lang, viewer_id=user_id),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _share_url(link, league):
    text = f"{league.get('name', '')} - Guess the Player"
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"
