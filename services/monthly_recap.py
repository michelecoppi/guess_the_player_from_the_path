"""Il recap mensile ("Wrapped", #245): il mese di un giocatore raccontato in poche schermate.

Tutto viene da dati che il gioco salva gia':

- `users/{id}/history/{giorno}`: com'e' andata ogni sfida del giorno (presa, tentativi, indizi
  e, da #245, se si e' stati i primi a rispondere);
- `daily_path/{giorno}`: il calciatore, il suo percorso e quanti l'hanno risolto;
- `monthly_closures/{mese}`: la distribuzione anonima dei punti del mese, e
  `users.monthly_totals.{mese}`: i punti del giocatore prima dell'azzeramento.

Il recap e' solo per i mesi chiusi, e solo con almeno `MIN_PLAYED` giornate giocate: con tre
partite i numeri sarebbero tristi, non divertenti. Le parti senza dati (nessuna chiusura
salvata, nessuna squadra ricorrente) mancano dal risultato e la mini app salta la loro
schermata.

Si calcola alla prima apertura e si salva sul documento utente (`recaps.{mese}`): le aperture
successive costano la lettura del documento che l'API fa comunque. Non si salva finche' manca
la chiusura del mese, cosi' la percentuale arriva appena la chiusura c'e'.
"""
import calendar
from collections import Counter

from services import firebase_service as fs
from services.dates import parse_iso, today_iso
from services.player_pool import get_player_by_id

MIN_PLAYED = 8
# La "perla" ha senso solo se l'hanno giocata abbastanza persone da fare una percentuale.
MIN_PLAYERS_FOR_RATE = 5
RECAP_VERSION = 1
MONTHS_BACK = 3
HISTORY_LIMIT = 100


def previous_month(today=None):
    day = parse_iso(today or today_iso())
    year, month = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def recent_months(today=None, count=MONTHS_BACK):
    months, current = [], today or today_iso()
    for _ in range(count):
        month = previous_month(current)
        months.append(month)
        current = f"{month}-01"
    return months


def _days_in(month):
    year, number = (int(part) for part in month.split("-"))
    return calendar.monthrange(year, number)[1]


def _best_streak(solved_days, month):
    best = run = 0
    for day in range(1, _days_in(month) + 1):
        run = run + 1 if f"{month}-{day:02d}" in solved_days else 0
        best = max(best, run)
    return best


def _style(played, days, solved_rows, firsts, hints_total):
    """Il titolo della schermata "stile di gioco", dal piu' raro al piu' comune."""
    solved = len(solved_rows)
    first_try = sum(1 for row in solved_rows if row.get("attempts") == 1)
    last_try = sum(1 for row in solved_rows if row.get("attempts", 0) >= 3)
    if firsts is not None and firsts >= 3:
        return {"key": "professor", "value": firsts}
    if solved and first_try * 2 >= solved:
        return {"key": "sniper", "value": first_try}
    if solved >= MIN_PLAYED and hints_total == 0:
        return {"key": "purist", "value": solved}
    if solved and last_try * 100 >= solved * 35:
        return {"key": "last_minute", "value": last_try}
    if played * 10 >= days * 9:
        return {"key": "marathon", "value": played}
    return {"key": "playmaker", "value": solved}


def _player_name(challenge):
    player = get_player_by_id(challenge.get("player_id")) or {}
    if player.get("full_name"):
        return player["full_name"]
    answers = [answer for answer in challenge.get("correct_answers", []) if " " in answer]
    return (max(answers, key=len) if answers else (challenge.get("correct_answers") or ["?"])[0]).title()


def _gem(solved_rows, challenges):
    """La sfida piu' difficile risolta: la percentuale di risoluzione piu' bassa."""
    best = None
    for row in solved_rows:
        challenge = challenges.get(row["day"]) or {}
        players = int(challenge.get("players_count") or 0)
        if players < MIN_PLAYERS_FOR_RATE or not challenge.get("career_path"):
            continue
        rate = int(challenge.get("solved_count") or 0) / players
        if best is None or rate < best[0]:
            best = (rate, row, challenge)
    if best is None:
        return None
    rate, row, challenge = best
    return {
        "day": row["day"],
        "rate": max(1, round(rate * 100)),
        "attempts": row.get("attempts"),
        "name": _player_name(challenge),
        "path": [
            {"team": stop.get("team", ""), "start_year": stop.get("start_year"), "end_year": stop.get("end_year")}
            for stop in challenge["career_path"]
        ],
    }


def _lucky_club(solved_rows, challenges):
    counts: Counter[str] = Counter()
    names: dict[str, list[str]] = {}
    for row in solved_rows:
        challenge = challenges.get(row["day"]) or {}
        teams = {stop.get("team") for stop in challenge.get("career_path") or [] if stop.get("team")}
        for team in teams:
            counts[team] += 1
            names.setdefault(team, []).append(_player_name(challenge))
    if not counts:
        return None
    team, count = max(counts.items(), key=lambda item: (item[1], item[0]))
    if count < 2:
        return None
    return {"team": team, "count": count, "players": names[team][:3]}


def _percentile(points, closure):
    distribution = (closure or {}).get("points_distribution")
    if points is None or not distribution:
        return None
    below = sum(1 for value in distribution if value < points)
    return round(100 * below / len(distribution))


def summarize(month, history, challenges, monthly_points=None, closure=None):
    """Il recap di un mese da dati gia' letti: funzione pura, e' quella che si prova."""
    rows = sorted((row for row in history if str(row.get("day", "")).startswith(month + "-")),
                  key=lambda row: row["day"])
    played = len(rows)
    if played < MIN_PLAYED:
        return {"month": month, "available": False, "played": played, "min_played": MIN_PLAYED}

    days = _days_in(month)
    by_day = {row["day"]: row for row in rows}
    calendar_row = []
    for day in range(1, days + 1):
        row = by_day.get(f"{month}-{day:02d}")
        calendar_row.append("skip" if not row else "won" if row.get("solved") else "lost")

    solved_rows = [row for row in rows if row.get("solved")]
    attempts = Counter(min(int(row.get("attempts") or 1), 3) for row in solved_rows)
    # "first" c'e' solo dalle giornate registrate dopo #245: senza, il dato non si inventa.
    firsts = sum(1 for row in rows if row.get("first")) if any("first" in row for row in rows) else None
    hints_total = sum(int(row.get("hints") or 0) for row in rows)

    recap = {
        "month": month,
        "available": True,
        "version": RECAP_VERSION,
        "played": played,
        "days": days,
        "solved": len(solved_rows),
        "calendar": calendar_row,
        "attempts": [attempts.get(1, 0), attempts.get(2, 0), attempts.get(3, 0)],
        "best_streak": _best_streak({row["day"] for row in solved_rows}, month),
        "hints": hints_total,
        "style": _style(played, days, solved_rows, firsts, hints_total),
    }
    optional = {
        "gem": _gem(solved_rows, challenges),
        "lucky_club": _lucky_club(solved_rows, challenges),
        "better_than": _percentile(monthly_points, closure),
        "firsts": firsts,
    }
    recap.update({key: value for key, value in optional.items() if value is not None})
    return recap


def recap_for(user_id, user_data, month, today=None):
    """Il recap di `month` per un utente: dalla cache sul documento, oppure calcolato."""
    today = today or today_iso()
    if month not in recent_months(today):
        return None
    cached = ((user_data or {}).get("recaps") or {}).get(month)
    if cached and (cached.get("version") == RECAP_VERSION or not cached.get("available")):
        return cached

    closure_snapshot = fs.db.collection("monthly_closures").document(month).get()
    closure = closure_snapshot.to_dict() if closure_snapshot.exists else None
    history = fs.get_daily_history(user_id, limit=HISTORY_LIMIT)
    rows = [row for row in history if str(row.get("day", "")).startswith(month + "-")]
    # Anche "troppe poche giornate" si salva: un mese chiuso non cambia piu', e senza la
    # cache chi ha giocato poco pagherebbe lo storico a ogni apertura.
    challenges = ({row["day"]: fs.get_daily_path(row["day"]) or {} for row in rows if row.get("solved")}
                  if len(rows) >= MIN_PLAYED else {})
    points = ((user_data or {}).get("monthly_totals") or {}).get(month)
    recap = summarize(month, rows, challenges, monthly_points=points, closure=closure)
    if closure is not None:
        fs.user_ref(user_id).update({f"recaps.{month}": recap})
    return recap


# ---------------------------------------------------------------------------
# La card da condividere
#
# Stessi colori della schermata finale della mini app. Solo forme e testo: il font non ha
# i glifi emoji (services/fonts.py), come per la figurina del risultato.
# ---------------------------------------------------------------------------

CARD_SIZE = (860, 1075)
GREEN = (70, 204, 145)
DARK_GREEN = (7, 45, 34)
MINT = (132, 226, 178)
NIGHT = (16, 24, 32)


def recap_card_png(recap, name, lang):
    """La card finale del recap, in PNG. Le parole arrivano tradotte da services/i18n."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    from services.fonts import get_font
    from services.i18n import t
    from services.share import bot_link

    width, height = CARD_SIZE
    image = Image.new("RGB", CARD_SIZE, NIGHT)
    draw = ImageDraw.Draw(image)
    margin = 60
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=40, fill=GREEN)

    small, label = get_font(28, bold=True), get_font(26)
    draw.text((margin + 44, margin + 40), "GUESS THE PLAYER", font=small, fill=DARK_GREEN)
    month_label = t(lang, f"recap.month.{int(recap['month'][5:])}").upper() + " " + recap["month"][:4]
    month_width = draw.textlength(month_label, font=small)
    draw.text((width - margin - 44 - month_width, margin + 40), month_label, font=small, fill=DARK_GREEN)

    draw.text((margin + 44, margin + 110), (name or "?").upper()[:14], font=get_font(120, bold=True), fill=DARK_GREEN)
    subtitle = t(lang, f"recap.style.{recap['style']['key']}")
    if recap.get("lucky_club"):
        subtitle += " · " + recap["lucky_club"]["team"]
    draw.text((margin + 44, margin + 260), subtitle, font=get_font(34), fill=DARK_GREEN)

    tiles = [
        (f"{recap['solved']}/{recap['played']}", t(lang, "recap.card.solved")),
        (str(recap["best_streak"]), t(lang, "recap.card.streak")),
    ]
    if recap.get("gem"):
        tiles.append((f"{recap['gem']['rate']}%", t(lang, "recap.card.gem")))
    if recap.get("better_than") is not None:
        tiles.append((f"TOP {max(1, 100 - recap['better_than'])}%", t(lang, "recap.card.rank")))
    else:
        tiles.append((str(recap["attempts"][0]), t(lang, "recap.card.first_try")))

    tile_w, tile_h, gap = (width - 2 * margin - 88 - 24) // 2, 220, 24
    top = margin + 340
    value_font = get_font(84, bold=True)
    for index, (value, caption) in enumerate(tiles[:4]):
        x = margin + 44 + (index % 2) * (tile_w + gap)
        y = top + (index // 2) * (tile_h + gap)
        draw.rounded_rectangle((x, y, x + tile_w, y + tile_h), radius=24, fill=DARK_GREEN)
        draw.text((x + 28, y + 36), value, font=value_font, fill=MINT)
        draw.text((x + 28, y + 150), caption, font=label, fill=MINT)

    footer = bot_link().replace("https://", "")
    if footer:
        draw.text((margin + 44, height - margin - 70), footer, font=small, fill=DARK_GREEN)

    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
