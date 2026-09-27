import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from services import trophies as trophy_tags
from services.firebase_service import get_user_data
from services.i18n import resolve_language, t
from services.path_image import render_avatar, render_palmares_image

TROPHIES_PER_PAGE = 5


def _palmares_image(lang, trophies):
    """Prima era un PNG su un hosting esterno (postimg): un link che nessuno controlla e
    che un giorno smette di rispondere. Ora la card la disegniamo noi, come il resto."""
    return render_palmares_image(
        title=t(lang, "image.palmares_title"),
        subtitle=t(lang, "image.palmares_subtitle", count=len(trophies)),
        trophies=len(trophies),
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data=None, edit_mode=False):
    user_id = update.effective_user.id
    if user_data is None:
        user_data = (await asyncio.to_thread(get_user_data, user_id))

    lang = (user_data or {}).get("language") or resolve_language(getattr(update.effective_user, "language_code", None))

    if not user_data:
        await update.effective_message.reply_text(t(lang, "stats.not_registered"))
        return

    trophies = user_data.get("trophies", [])
    context.user_data["user_data"] = user_data
    context.user_data["trophies"] = trophies
    context.user_data["lang"] = lang

    first_name = user_data.get("first_name", "N/A")
    points_totali = user_data.get("points_totali", 0)
    monthly_points = user_data.get("monthly_points", 0)
    players_guessed = user_data.get("players_guessed", 0)
    bonus_first_guessed = user_data.get("bonus_first_guessed", 0)
    telegram_id = user_data.get("telegram_id")

    stats_message = t(
        lang, "stats.message",
        name=first_name,
        points_totali=points_totali,
        monthly_points=monthly_points,
        players_guessed=players_guessed,
        bonus_first_guessed=bonus_first_guessed,
    )
    # Striscia e archivio sono su una riga a parte: le vecchie traduzioni di stats.message
    # restano valide anche per chi non ha ancora nessuno dei due contatori.
    stats_message += "\n" + t(
        lang, "stats.streak_line",
        streak=user_data.get("current_streak", 0),
        best=user_data.get("best_streak", 0),
        archive_solved=user_data.get("archive_solved", 0),
    )

    keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton(t(lang, "stats.button_trophies"), callback_data="show_trophies_0")]
    ])

    photos = await context.bot.get_user_profile_photos(telegram_id)
    if photos.total_count > 0:
        profile_pic = photos.photos[0][-1].file_id
    else:
        # Avatar con le iniziali generato al momento, al posto dell'icona presa da un sito
        # esterno: stessa grafica del resto del bot e nessun link che puo' morire.
        profile_pic = render_avatar(first_name)

    if edit_mode:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(
                media=profile_pic,
                caption=stats_message,
                parse_mode="Markdown"
            ),
            reply_markup=keyboard
        )
    else:
        await update.effective_message.reply_photo(
            photo=profile_pic,
            caption=stats_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

async def show_trophies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    trophies = context.user_data.get("trophies", [])
    lang = context.user_data.get("lang") or resolve_language(getattr(update.effective_user, "language_code", None))

    _, _, page_str = query.data.split("_")
    page = int(page_str)

    if not trophies:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "stats.button_back"), callback_data="back_to_stats")]
        ])
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=_palmares_image(lang, trophies),
                caption=t(lang, "stats.no_trophies"),
                parse_mode="Markdown"
            ),
            reply_markup=keyboard
        )
        return

    start = page * TROPHIES_PER_PAGE
    end = start + TROPHIES_PER_PAGE
    displayed = trophies[start:end]

    # Le stesse targhe della mini app (services/trophies.py). Prima la lettura del codice
    # stava qui e contava i pezzi fra un trattino basso e l'altro: l'id di un evento come
    # `un_amore_una_maglia` ne porta gia' tre suoi, quindi quasi tutti i trofei veri
    # cadevano nel ripiego e uscivano come codice grezzo.
    message = t(lang, "stats.trophies_title")
    for trophy in displayed:
        tag = trophy_tags.parse(trophy, lang)
        if tag:
            message += t(lang, "stats.trophy_line", medal=tag["medal"], label=tag["label"],
                         detail=tag["detail"])
        else:
            message += f"🏅 {trophy}\n"

    buttons = []
    if start > 0:
        buttons.append(InlineKeyboardButton(t(lang, "stats.nav_back"), callback_data=f"show_trophies_{page - 1}"))
    if end < len(trophies):
        buttons.append(InlineKeyboardButton(t(lang, "stats.nav_forward"), callback_data=f"show_trophies_{page + 1}"))

    keyboard = InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton(t(lang, "stats.button_back"), callback_data="back_to_stats")]
    ])

    await query.edit_message_media(
        media=InputMediaPhoto(
            media=_palmares_image(lang, trophies),
            caption=message,
            parse_mode="Markdown"
        ),
        reply_markup=keyboard
    )

async def back_to_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data.get("user_data")
    await stats(update, context, user_data=user_data, edit_mode=True)
