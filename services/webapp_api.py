"""Quello che la mini app Telegram legge e scrive.

Sta qui e non dentro gli endpoint di bot.py per la stessa ragione per cui `play_daily` sta
fuori dagli handler: cosi' si prova senza tirare su FastAPI e senza Firestore.

**La regola che non si tocca**: da qui non esce mai niente che permetta di rispondere senza
indovinare. Le risposte accettate (`correct_answers`) e l'id del calciatore (`player_id`)
sono sul documento della sfida, e il documento non si serializza mai per intero: ogni card
elenca i campi uno per uno. Il client e' il telefono di chi gioca, e chiunque sa aprire gli
strumenti di sviluppo puo' leggere quello che gli mandiamo.

Chi sia l'utente lo decide **solo** la firma di initData (services/webapp_auth.py), mai il
client: nessuna di queste funzioni riceve un id da fuori.
"""
import contextvars
from concurrent.futures import ThreadPoolExecutor

from domains.referrals import service as referrals
from domains.shop import service as shop
from services import daily_result, feature_flags, firebase_service, game, trophies
from services import product_analytics as analytics
from services.career_order import order_career
from services.content_i18n import localize_career
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.daily_result import ResultUnavailable as ResultUnavailable  # re-export for apps/api/miniapp.py
from services.dates import normalize_day, to_display, today_iso
from services.difficulty import points_for_difficulty
from services.feature_flags import Flag
from services.hints import MAX_HINTS, build_hints
from services.i18n import DEFAULT_LANGUAGE, difficulty_label, t
from services.player_pool import get_player_by_id
from services.share import card_image, share_text, share_url

MAX_LEAGUES_SHOWN = 5
LEADERBOARD_SIZE = 10
CALENDAR_DAYS = 30
PROFILE_SEARCH_SIZE = 10

# Tentativi su una sfida d'archivio giocata dalla mini app: gli stessi della chat
# (handlers/archive_handler.py), perche' e' la stessa partita vista da un'altra finestra.
MAX_ARCHIVE_ATTEMPTS = 3


def build_profile(user_id, day_iso=None, lang=None, *, user=None, include_social=True):
    """Tutto quello che serve alla schermata principale, in una risposta sola. None se
    l'utente non esiste ancora (non ha mai fatto /start)."""
    if user is None:
        user = firebase_service.get_user_data(user_id)
    if not user:
        return None

    day_iso = day_iso or today_iso()
    lang = lang or user.get("language") or DEFAULT_LANGUAGE
    features = feature_flags.resolved_features(user_id=user_id)
    # `include_social=False` is the lightweight polling variant used to refresh game state
    # only; the full bundle is what a real "the Mini App/Daily was opened" looks like, so
    # that is the only branch that counts as a view (avoids an event per poll).
    if include_social:
        analytics.capture(analytics.Event.MINIAPP_OPENED, user_id=user_id, properties={"language": lang})
        analytics.capture(analytics.Event.DAILY_VIEWED, user_id=user_id,
                          properties={"surface": "miniapp", "language": lang})

    profile = {
        "language": lang,
        "user": _user_summary(user),
        # I cosmetici comprati in negozio: colori del tema, cornice, titolo, distintivo.
        # Stanno nel profilo e non dietro la scheda del negozio perche' la pagina si deve
        # disegnare gia' giusta alla prima apertura (domains/shop/service.py, `appearance`).
        "cosmetics": shop.appearance(user, lang),
        "wardrobe": _public_wardrobe(user, lang),
        # I trofei vinti, scelti da chi li ha vinti (services/trophies.py). Viaggiano col
        # profilo e non dietro una scheda loro per la stessa ragione dei cosmetici: la
        # prima schermata deve gia' essere quella giusta.
        "trophies": {"pinned": trophies.showcase(user, lang), "all": trophies.cabinet(user, lang),
                     "max": trophies.MAX_PINNED},
        "distribution": _distribution(user),
        # Feature flags (#51) risolti per chi guarda: solo booleani, mai regole, liste di
        # utenti/gruppi o percentuali. La pagina li usa per nascondere; decide il server.
        "features": features,
    }
    # Le letture non dipendono l'una dall'altra: partono tutte insieme e la risposta aspetta
    # la piu' lenta invece della somma (#260). Prima erano in fila - sfida, due classifiche,
    # poi documento e classifica di ogni lega - e Firestore era oltre meta' della richiesta.
    challenge = _read(firebase_service.get_daily_path, day_iso)
    # Wrong guesses and hints do not change standings; refresh only game state.
    if include_social:
        # Classifica spenta: lista vuota, stessa forma per i client gia' in giro. Punti e
        # posizioni non si toccano, semplicemente non si leggono.
        leaderboard_on = features[Flag.LEADERBOARD.value]
        top = _read(firebase_service.get_top_users, field="points_totali", limit=LEADERBOARD_SIZE) if leaderboard_on else None
        monthly = _read(firebase_service.get_top_users, field="monthly_points", limit=LEADERBOARD_SIZE) if leaderboard_on else None
        leagues = _start_league_reads(user)
    profile["today"] = _today_summary(user, day_iso, lang, challenge=challenge.result() or {})
    if include_social:
        profile["leaderboard"] = _leaderboard(user_id, rows=top.result()) if top else []
        # La mensile e' la prima scheda della Mini App (#256): stessa forma della generale,
        # "points" sono i punti del mese, quelli che la chiusura mensile premia.
        profile["monthly_leaderboard"] = _leaderboard(user_id, monthly=True, rows=monthly.result()) if monthly else []
        profile["leagues"] = _league_cards(leagues, user_id)
    return profile


# Letture del profilo in parallelo (#260). Ogni richiesta ne lancia al massimo 3 + 2 per lega
# e le aspetta subito, senza lanciarne altre da dentro: il pool non si blocca su se stesso.
_READS = ThreadPoolExecutor(max_workers=16, thread_name_prefix="profile-reads")


def _read(fn, *args, **kwargs):
    """Avvia una lettura in un thread con il contesto della richiesta, cosi' resta contata
    sulla richiesta che l'ha fatta (#32)."""
    return _READS.submit(contextvars.copy_context().run, fn, *args, **kwargs)


def _user_summary(user):
    return {
        "name": user.get("first_name", "?"),
        "points": user.get("points_totali", 0),
        "monthly_points": user.get("monthly_points", 0),
        "players_guessed": user.get("players_guessed", 0),
        "bonus_first_guessed": user.get("bonus_first_guessed", 0),
        "streak": user.get("current_streak", 0),
        "best_streak": user.get("best_streak", 0),
        "archive_solved": user.get("archive_solved", 0),
        "trophies": len(user.get("trophies", [])),
    }


def _public_wardrobe(user, lang):
    """Localized owned styles only; no purchase, payment or saved-look data."""
    return [
        {"id": item_id, "kind": item["kind"], "name": shop.localize(item, lang)[0],
         "free": shop.is_free(item)}
        for item_id in sorted(shop.owned_ids(user))
        if (item := shop.get_item(item_id)) and item.get("kind") in shop.KINDS
    ]


def build_public_profile(target_id, lang=DEFAULT_LANGUAGE):
    """An explicit public projection, never the private /me response."""
    if type(target_id) is not int or target_id <= 0 or target_id > 2**52:
        return None
    user = firebase_service.get_user_data(target_id)
    if not user:
        return None
    appearance = shop.appearance(user, lang)
    return {
        "user": _user_summary(user),
        "cosmetics": appearance,
        "wardrobe": _public_wardrobe(user, lang),
        # Solo quelli appesi: la bacheca intera e' roba di chi la possiede, il profilo
        # pubblico mostra quello che ha scelto di far vedere.
        "trophies": trophies.showcase(user, lang),
        "wearing": [{"kind": kind, "name": shop.localize(shop.get_item(item_id), lang)[0]}
                    for kind, item_id in appearance["equipped"].items()],
    }


def search_public_profiles(query, limit=PROFILE_SEARCH_SIZE):
    """Risultati minimi per trovare un profilo pubblico dal nome.

    Firestore cerca per prefisso e distingue maiuscole e minuscole. I nomi Telegram sono
    normalmente capitalizzati, quindi normalizziamo ogni parola senza alterare il metodo
    generico usato dalla dashboard. Non escono mai documento utente, leghe o acquisti.
    """
    if not isinstance(query, str):
        return []
    prefix = " ".join(query.strip().split())
    if len(prefix) < 2:
        return []
    safe_limit = max(1, min(int(limit or PROFILE_SEARCH_SIZE), PROFILE_SEARCH_SIZE))
    users = firebase_service.find_users_by_first_name(prefix.title(), limit=safe_limit)
    return [
        {
            "profile_id": user.get("telegram_id"),
            "name": user.get("first_name", "?"),
            "badge": shop.badge_emoji(user),
            "points": user.get("points_totali", 0),
            "trophies": len(user.get("trophies", [])),
        }
        for user in users
        if type(user.get("telegram_id")) is int and 0 < user["telegram_id"] <= 2**52
    ]


def _distribution(user):
    """In quanti tentativi risolve di solito: un valore per tentativo possibile.

    E' l'istogramma alla Wordle. I contatori li scrive `register_correct_guess`, quindi qui
    non c'e' nessuna lettura in piu': stanno gia' sul documento utente."""
    counters = user.get("solved_in") or {}
    return [{"attempts": n, "count": int(counters.get(str(n), 0))} for n in range(1, MAX_ATTEMPTS + 1)]


def _today_summary(user, day_iso, lang, challenge=None):
    """La sfida di oggi come la vede questo utente.

    `career_path` c'e' perche' la mini app disegna il percorso in HTML invece di ricevere la
    PNG: le tappe si possono aprire al tocco, e soprattutto il paese arriva gia' tradotto
    invece che cotto dentro l'immagine.

    `hints` riporta **solo gli indizi gia' pagati**: quelli non ancora presi non si mandano
    al client, altrimenti basterebbe guardare la risposta di rete per averli gratis."""
    if challenge is None:  # chi l'ha gia' letta (build_profile, in parallelo) la passa
        challenge = firebase_service.get_daily_path(day_iso) or {}
    played_today = normalize_day(user.get("last_played_day")) == day_iso
    solved = bool(played_today and user.get("has_guessed_today"))
    attempts_used = user.get("daily_attempts", 0) if played_today else 0
    hints_used = user.get("daily_hints", 0) if played_today else 0

    available = build_hints(get_player_by_id(challenge.get("player_id")), lang) if challenge else []
    max_hints = min(len(available), MAX_HINTS)

    return {
        "day": day_iso,
        "number": challenge_number(day_iso),
        "available": bool(challenge),
        "solved": solved,
        "attempts_used": attempts_used,
        "attempts_left": max(MAX_ATTEMPTS - attempts_used, 0),
        "max_attempts": MAX_ATTEMPTS,
        "difficulty": challenge.get("difficulty"),
        "difficulty_label": difficulty_label(lang, challenge.get("difficulty")),
        "points": points_for_difficulty(challenge.get("difficulty")) if challenge else 0,
        "bonus_available": bool(challenge) and not challenge.get("first_correct_user", False),
        "career_path": localize_career(order_career(challenge.get("career_path")), lang),
        "hints": {
            "used": hints_used,
            "total": max_hints,
            # Solo quelli gia' pagati.
            "taken": available[:hints_used],
        },
    }


def _leaderboard(user_id, monthly=False, rows=None):
    field = "monthly_points" if monthly else "points_totali"
    score_key = "monthly_points" if monthly else "points"
    top = rows if rows is not None else firebase_service.get_top_users(field=field, limit=LEADERBOARD_SIZE)
    return [
        {
            "position": position,
            "profile_id": entry.get("telegram_id"),
            "name": entry.get("username", "?"),
            "badge": shop.badge_emoji(entry) or entry.get("badge", ""),
            "points": entry.get(score_key, 0),
            "me": entry.get("telegram_id") == user_id,
        }
        for position, entry in enumerate(top, start=1)
    ]


def _start_league_reads(user):
    """Documento e classifica di ogni lega, tutti insieme: sono letture indipendenti (#260)."""
    return [
        (code, _read(firebase_service.get_league, code), _read(firebase_service.get_league_leaderboard, code, limit=20))
        for code in (user.get("leagues") or [])[:MAX_LEAGUES_SHOWN]
    ]


def _league_cards(reads, user_id):
    leagues = []
    for code, league_read, members_read in reads:
        league = league_read.result()
        members = members_read.result()
        if not league:
            continue
        position = next(
            (index for index, member in enumerate(members, start=1) if member.get("telegram_id") == user_id),
            None,
        )
        points = next(
            (member.get("points", 0) for member in members if member.get("telegram_id") == user_id),
            0,
        )
        leagues.append({
            "code": code,
            "name": league.get("name", code),
            "members": league.get("members_count", len(members)),
            "position": position,
            "points": points,
            "standings": [
                {
                    "position": index,
                    "profile_id": member.get("telegram_id"),
                    "name": member.get("name", "?"),
                    "points": member.get("points", 0),
                    "me": member.get("telegram_id") == user_id,
                }
                for index, member in enumerate(members, start=1)
            ],
        })
    return leagues


# ---------------------------------------------------------------------------
# Calendario delle giornate passate
# ---------------------------------------------------------------------------

def build_calendar(user_id, lang=DEFAULT_LANGUAGE, days=CALENDAR_DAYS, today=None):
    """Le ultime giornate con com'e' andata a questo utente.

    Gli stati sono quattro e vanno tenuti distinti, perche' vogliono dire cose diverse:

    - `solved`: presa il giorno stesso (e in quanti tentativi);
    - `lost`: giocata il giorno stesso e non presa;
    - `recovered`: recuperata dopo, in archivio (non da' punti, ma non e' un buco);
    - `missed`: mai giocata.

    Tre letture in tutto - le sfide, lo storico dell'utente, le giornate recuperate - e non
    una per giorno."""
    today = today or today_iso()
    challenges = firebase_service.get_past_daily_paths(limit=days, before_day_iso=today)
    history = {doc.get("day"): doc for doc in firebase_service.get_daily_history(user_id, limit=days)}
    recovered = firebase_service.get_solved_archive_days(user_id)

    calendar = []
    for challenge in challenges:
        day = challenge.get("day")
        if not day:
            continue
        played = history.get(day) or {}
        if played.get("solved"):
            status = "solved"
        elif day in recovered:
            status = "recovered"
        elif played:
            status = "lost"
        else:
            status = "missed"

        calendar.append({
            "day": day,
            "label": to_display(day),
            "number": challenge_number(day),
            "difficulty": challenge.get("difficulty"),
            "difficulty_label": difficulty_label(lang, challenge.get("difficulty")),
            "status": status,
            "attempts": played.get("attempts"),
            "hints": played.get("hints", 0),
            # Rigiocabile solo se non l'ha gia' risolta in un modo o nell'altro.
            "playable": status in ("lost", "missed"),
        })
    return calendar


def build_archive_challenge(user_id, day_iso, lang=DEFAULT_LANGUAGE):
    """Il percorso di una giornata passata, per giocarla dentro la mini app.

    Come per la sfida di oggi: niente `correct_answers`, niente `player_id`."""
    challenge = firebase_service.get_daily_path(day_iso)
    if not challenge:
        return None

    result = firebase_service.get_archive_result(user_id, day_iso) or {}
    attempts_used = result.get("attempts", 0)

    analytics.capture(analytics.Event.DAILY_ARCHIVE_VIEWED, user_id=user_id,
                      properties={"surface": "miniapp"})
    return {
        "day": day_iso,
        "label": to_display(day_iso),
        "number": challenge_number(day_iso),
        "difficulty": challenge.get("difficulty"),
        "difficulty_label": difficulty_label(lang, challenge.get("difficulty")),
        "solved": bool(result.get("solved")),
        "attempts_used": attempts_used,
        "attempts_left": max(MAX_ARCHIVE_ATTEMPTS - attempts_used, 0),
        "max_attempts": MAX_ARCHIVE_ATTEMPTS,
        "career_path": localize_career(order_career(challenge.get("career_path")), lang),
    }


# ---------------------------------------------------------------------------
# Un tentativo dalla mini app
# ---------------------------------------------------------------------------

def is_daily_play(day, today=None):
    """Un tentativo senza `day`, o con la data di oggi, e' la sfida del giorno; altrimenti e'
    l'archivio. Una sola definizione, usata da `play` e dal flag `daily_ui` in bot.py."""
    return not day or day == (today or today_iso())


def play(user_id, user_data, answer, day=None, lang=DEFAULT_LANGUAGE, today=None):
    """Un tentativo: la sfida di oggi, oppure una giornata passata se arriva `day`.

    Le regole sono quelle di services/game.py, cioe' **le stesse** che applica la chat: qui
    si sceglie solo quale delle due partite si sta giocando e si attacca la card da
    condividere quando la partita si chiude."""
    today = today or today_iso()
    symbols = shop.squares_symbols(user_data)
    if not is_daily_play(day, today):
        result = game.play_archive(user_id, day, answer, MAX_ARCHIVE_ATTEMPTS)
        return with_share_card(result, lang, MAX_ARCHIVE_ATTEMPTS, day=day, archive=True, symbols=symbols,
                               link=referrals.invite_link(user_id))

    result = game.play_daily(user_id, user_data, answer, first_name=(user_data or {}).get("first_name"),
                             surface="miniapp")
    if result.get("status") == "correct":
        # `play_daily` lo prende dalla sfida che ha appena giocato: niente seconda lettura.
        result["answer"] = result.get("answer") or firebase_service.get_display_name_for_day(today)
    elif result.get("status") == "wrong":
        # La Daily come la vede adesso chi ha sbagliato (#259): la pagina la disegna subito,
        # invece di chiedere di nuovo il profilo solo per sapere quanti tentativi restano.
        # Dopo un errore cambiano solo tentativi e indizi, e l'esito li ha appena scritti.
        result["today"] = _today_summary({
            **(user_data or {}),
            "last_played_day": today,
            "has_guessed_today": False,
            "daily_attempts": result.get("attempts_used", 0),
            "daily_hints": result.get("hints_used", 0),
        }, today, lang)
    return with_share_card(result, lang, MAX_ATTEMPTS, symbols=symbols, link=referrals.invite_link(user_id))


def with_share_card(result, lang, max_attempts, day=None, archive=False, symbols=None, link=None):
    """Aggiunge la card da condividere quando la partita si e' chiusa.

    La compone il server e non la pagina: cosi' i quadratini, la lampadina degli indizi e la
    riga della striscia restano identici a quelli che escono dalla chat. Due formati diversi
    per lo stesso risultato si noterebbero subito in un gruppo dove qualcuno gioca dall'app e
    qualcuno dal bot."""
    finished = result.get("status") == "correct" or (
        result.get("status") == "wrong" and result.get("attempts_left") == 0
    )
    if not finished:
        return result

    text = share_text(
        lang,
        challenge_number(day),
        result.get("attempts_used", max_attempts),
        max_attempts,
        solved=result["status"] == "correct",
        streak=result.get("streak", 0),
        archive=archive,
        hints=result.get("hints_used", 0),
        symbols=symbols,
        link=link,
    )
    result["share"] = {"text": text, "url": share_url(text, link)}
    return result


# ---------------------------------------------------------------------------
# Today's result card: the figurina (`/app/api/card`) and the native share (#185)
# ---------------------------------------------------------------------------


def todays_result(user_id, today=None):
    """Today's Daily result as the **server** recorded it, never as a page declares it.

    Returns {day, attempts, hints, solved}; raises ResultUnavailable when the game is not
    finished (409) or the stored numbers are out of range (422). The checks live in
    services/daily_result.py, shared with the bot's card button."""
    day = today or today_iso()
    history = firebase_service.get_daily_history(user_id, limit=1)
    return daily_result.checked(history[0] if history else None, day)


def result_card_png(user_data, lang, result):
    """The figurina of `todays_result`, as PNG bytes."""
    solved = result["solved"]
    pinned = trophies.showcase(user_data, lang)
    buffer = card_image(
        user_data, lang, challenge_number(result["day"]), result["attempts"], MAX_ATTEMPTS,
        solved=solved,
        streak=int(user_data.get("current_streak") or 0) if solved else 0,
        hints=result["hints"],
        trophy=pinned[0] if pinned else None,
        day=result["day"],
    )
    return buffer.getvalue()


def result_share(user_id, user_data, lang, result):
    """What the native share sends: the same text as the chat card, the figurina and the
    sharer's invite link (#150), all derived from `todays_result`."""
    link = referrals.invite_link(user_id)
    solved = result["solved"]
    text = share_text(
        lang,
        challenge_number(result["day"]),
        result["attempts"],
        MAX_ATTEMPTS,
        solved=solved,
        streak=int(user_data.get("current_streak") or 0) if solved else 0,
        hints=result["hints"],
        symbols=shop.squares_symbols(user_data),
        link=link,
    )
    return {"text": text, "image": result_card_png(user_data, lang, result), "link": link}


def recap_share(user_id, user_data, lang, recap):
    """The monthly recap card (#245) with its text and the sharer's invite link."""
    from services import monthly_recap

    link = referrals.invite_link(user_id)
    month = t(lang, f"recap.month.{int(recap['month'][5:])}")
    text = t(lang, "recap.share_text", month=month, solved=recap["solved"], played=recap["played"])
    if link:
        text += "\n" + link
    name = (user_data or {}).get("first_name") or ""
    look = shop.appearance(user_data or {}, lang)
    return {"text": text, "image": monthly_recap.recap_card_png(recap, name, lang, look), "link": link}


def recap_look(user_data, lang):
    """The equipped cosmetics the recap's final card wears in the Mini App (#245): the same
    card colours, title and shirt number as the shared image, nothing else."""
    look = shop.appearance(user_data or {}, lang)
    card = look.get("card") or {}
    return {
        "card": {key: card[key] for key in ("paper", "ink", "glow", "finish") if card.get(key)},
        "title": (look.get("title") or {}).get("label", ""),
        "number": look.get("number", ""),
    }
