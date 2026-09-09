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
from services import firebase_service, game, shop, trophies
from services.career_order import order_career
from services.content_i18n import localize_career
from services.daily_challenge import MAX_ATTEMPTS, challenge_number
from services.dates import normalize_day, to_display, today_iso
from services.difficulty import points_for_difficulty
from services.hints import MAX_HINTS, build_hints
from services.i18n import DEFAULT_LANGUAGE, difficulty_label
from services.player_pool import _load_raw_players, get_player_by_id
from services.share import share_text, share_url

MAX_LEAGUES_SHOWN = 5
LEADERBOARD_SIZE = 10
CALENDAR_DAYS = 30

# Tentativi su una sfida d'archivio giocata dalla mini app: gli stessi della chat
# (handlers/archive_handler.py), perche' e' la stessa partita vista da un'altra finestra.
MAX_ARCHIVE_ATTEMPTS = 3


def build_profile(user_id, day_iso=None, lang=None):
    """Tutto quello che serve alla schermata principale, in una risposta sola. None se
    l'utente non esiste ancora (non ha mai fatto /start)."""
    user = firebase_service.get_user_data(user_id)
    if not user:
        return None

    day_iso = day_iso or today_iso()
    lang = lang or user.get("language") or DEFAULT_LANGUAGE

    return {
        "language": lang,
        "user": _user_summary(user),
        # I cosmetici comprati in negozio: colori del tema, cornice, titolo, distintivo.
        # Stanno nel profilo e non dietro la scheda del negozio perche' la pagina si deve
        # disegnare gia' giusta alla prima apertura (services/shop.py, `appearance`).
        "cosmetics": shop.appearance(user, lang),
        # I trofei vinti, scelti da chi li ha vinti (services/trophies.py). Viaggiano col
        # profilo e non dietro una scheda loro per la stessa ragione dei cosmetici: la
        # prima schermata deve gia' essere quella giusta.
        "trophies": {"pinned": trophies.showcase(user, lang), "all": trophies.cabinet(user, lang),
                     "max": trophies.MAX_PINNED},
        "today": _today_summary(user, day_iso, lang),
        "distribution": _distribution(user),
        "leaderboard": _leaderboard(user_id),
        "leagues": _leagues(user, user_id),
    }


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
        # Solo quelli appesi: la bacheca intera e' roba di chi la possiede, il profilo
        # pubblico mostra quello che ha scelto di far vedere.
        "trophies": trophies.showcase(user, lang),
        "wearing": [{"kind": kind, "name": shop.localize(shop.get_item(item_id), lang)[0]}
                    for kind, item_id in appearance["equipped"].items()],
    }


def _distribution(user):
    """In quanti tentativi risolve di solito: un valore per tentativo possibile.

    E' l'istogramma alla Wordle. I contatori li scrive `register_correct_guess`, quindi qui
    non c'e' nessuna lettura in piu': stanno gia' sul documento utente."""
    counters = user.get("solved_in") or {}
    return [{"attempts": n, "count": int(counters.get(str(n), 0))} for n in range(1, MAX_ATTEMPTS + 1)]


def _today_summary(user, day_iso, lang):
    """La sfida di oggi come la vede questo utente.

    `career_path` c'e' perche' la mini app disegna il percorso in HTML invece di ricevere la
    PNG: le tappe si possono aprire al tocco, e soprattutto il paese arriva gia' tradotto
    invece che cotto dentro l'immagine.

    `hints` riporta **solo gli indizi gia' pagati**: quelli non ancora presi non si mandano
    al client, altrimenti basterebbe guardare la risposta di rete per averli gratis."""
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


def _leaderboard(user_id):
    top = firebase_service.get_top_users(limit=LEADERBOARD_SIZE)
    return [
        {
            "position": position,
            "profile_id": entry.get("telegram_id"),
            "name": entry.get("username", "?"),
            "badge": shop.badge_emoji(entry) or entry.get("badge", ""),
            "points": entry.get("points", 0),
            "me": entry.get("telegram_id") == user_id,
        }
        for position, entry in enumerate(top, start=1)
    ]


def _leagues(user, user_id):
    leagues = []
    for code in (user.get("leagues") or [])[:MAX_LEAGUES_SHOWN]:
        league = firebase_service.get_league(code)
        if not league:
            continue
        members = firebase_service.get_league_leaderboard(code, limit=20)
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

def play(user_id, user_data, answer, day=None, lang=DEFAULT_LANGUAGE, today=None):
    """Un tentativo: la sfida di oggi, oppure una giornata passata se arriva `day`.

    Le regole sono quelle di services/game.py, cioe' **le stesse** che applica la chat: qui
    si sceglie solo quale delle due partite si sta giocando e si attacca la card da
    condividere quando la partita si chiude."""
    today = today or today_iso()
    symbols = shop.squares_symbols(user_data)
    if day and day != today:
        result = game.play_archive(user_id, day, answer, MAX_ARCHIVE_ATTEMPTS)
        return with_share_card(result, lang, MAX_ARCHIVE_ATTEMPTS, day=day, archive=True, symbols=symbols)

    result = game.play_daily(user_id, user_data, answer, first_name=(user_data or {}).get("first_name"))
    return with_share_card(result, lang, MAX_ATTEMPTS, symbols=symbols)


def with_share_card(result, lang, max_attempts, day=None, archive=False, symbols=None):
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
    )
    result["share"] = {"text": text, "url": share_url(text)}
    return result


# ---------------------------------------------------------------------------
# Nomi per il completamento automatico
# ---------------------------------------------------------------------------

def player_names():
    """I nomi del dataset, per il campo con i suggerimenti.

    E' la cosa che nella mini app cambia di piu' la partita: sparisce il "l'ho scritto
    giusto?" e sparisce il tentativo bruciato su un nome che il bot non conosce.

    Non regala niente: sono **tutte** le schede, comprese quelle riservate all'allenamento e
    quelle non verificate, quindi sapere che un nome e' nell'elenco non dice che sia la
    risposta di oggi. Ordinati e senza duplicati per rendere la lista comprimibile e stabile
    fra una chiamata e l'altra."""
    return sorted({player["full_name"] for player in _load_raw_players() if player.get("full_name")})
