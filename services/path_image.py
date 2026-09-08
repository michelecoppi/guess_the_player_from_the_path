"""Immagini generate a runtime con Pillow: nessuna immagine da ospitare da nessuna parte.

Le card sono disegnate come una **timeline verticale**: una linea collega le tappe, ogni
tappa ha un nodo del colore del club, e una barra proporzionale agli anni passati li' rende
leggibile a colpo d'occhio dove il calciatore e' rimasto a lungo. Il testo e' volutamente
senza emoji: il font che usiamo (vedi services/fonts.py) non ha i glifi emoji e li
disegnerebbe come quadratini.

Il nome del calciatore non compare mai: e' la risposta.
"""
import colorsys
import hashlib
import io

from PIL import Image, ImageDraw

from services.fonts import get_font

WIDTH = 900
ROW_HEIGHT = 104
ROW_GAP = 14
HEADER_HEIGHT = 150
FOOTER_HEIGHT = 58
PADDING = 34

# Oltre questa soglia la card passa al layout compatto. Serve perche' Telegram scala
# l'immagine alla larghezza della bolla: con le righe piene, una carriera da 20 tappe
# diventa alta 2588 px e in chat si legge male. Il tetto e' ~1950 px, che scalato resta
# leggibile su un telefono senza costringere a ingrandire.
COMPACT_FROM_ROWS = 13
MAX_ROWS = 20

TIMELINE_X = 60
CARD_X = 104
CARD_RIGHT = WIDTH - PADDING

BG_TOP = (10, 19, 30)
BG_BOTTOM = (19, 36, 55)
HEADER_COLOR = (7, 14, 23)
CARD_COLOR = (26, 44, 64)
CARD_EDGE = (39, 62, 86)
TEXT_COLOR = (236, 242, 248)
MUTED_COLOR = (142, 162, 182)
ACCENT_COLOR = (56, 189, 130)
TRACK_COLOR = (44, 68, 92)


def _color_for_team(team_name):
    """Colore stabile per squadra: la tinta viene dall'hash del nome, saturazione e
    luminosita' sono fisse. Cosi' i colori sono sempre gli stessi per lo stesso club e non
    escono mai fango o fluorescenti come con un hash usato direttamente su RGB."""
    digest = hashlib.md5(team_name.encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) / 65535
    r, g, b = colorsys.hsv_to_rgb(hue, 0.58, 0.88)
    return (int(r * 255), int(g * 255), int(b * 255))


def _vertical_gradient(width, height, top, bottom):
    column = [
        tuple(int(top[channel] + (bottom[channel] - top[channel]) * y / max(height - 1, 1)) for channel in range(3))
        for y in range(height)
    ]
    base = Image.new("RGB", (1, height))
    base.putdata(column)
    return base.resize((width, height))


def _truncate(draw, text, font, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    while text and draw.textlength(text + ellipsis, font=font) > max_width:
        text = text[:-1]
    return text + ellipsis


def _initials(name):
    words = [w for w in name.split() if w]
    return "".join(w[0].upper() for w in words[:2]) or "?"


def _stint_years(stop):
    start = stop.get("start_year")
    end = stop.get("end_year")
    if not isinstance(start, int):
        return 0
    if not isinstance(end, int):
        return 1
    return max(end - start, 1)


def _years_label(stop):
    """Etichetta degli anni, senza parole: l'immagine e' la stessa per utenti italiani,
    spagnoli e inglesi, quindi niente "oggi" o "present" dentro il disegno.

    Per lo stesso motivo un prestito e' marcato con la freccia davanti agli anni (la
    convenzione di Wikipedia e dei siti di calciomercato) invece che con la parola
    "prestito". La tappa ancora in corso finisce con i puntini e non con una freccia:
    altrimenti in una carriera piena di prestiti le due frecce si confonderebbero.

    Sono glifi scelti anche per il font di produzione (DejaVu nel Dockerfile, non lo stesso
    di uno sviluppatore su Windows): niente frecce esotiche che diventerebbero un
    rettangolo vuoto sul server."""
    start = stop.get("start_year", "?")
    end = stop.get("end_year")
    span = f"{start} – {end}" if end else f"{start} – …"
    return f"→ {span}" if stop.get("loan") else span


def _layout_for(rows):
    """Misure delle righe in base a quante tappe ci sono.

    Una carriera corta merita righe generose; una da 15-20 tappe (esistono: Kevin-Prince
    Boateng ne ha 15) va compattata, altrimenti l'immagine diventa una colonna altissima che
    Telegram rimpicciolisce fino a renderla illeggibile."""
    if rows >= COMPACT_FROM_ROWS:
        return {
            "row_height": 76, "row_gap": 10, "badge": 46,
            "team_size": 25, "meta_size": 17, "years_size": 19,
            "bar_max": 130, "show_meta": True,
        }
    return {
        "row_height": ROW_HEIGHT, "row_gap": ROW_GAP, "badge": 58,
        "team_size": 30, "meta_size": 21, "years_size": 23,
        "bar_max": 170, "show_meta": True,
    }


def _stats_label(stop):
    """Presenze e gol come "33 (22)", la convenzione di Wikipedia e dei siti di statistiche.

    Niente parole ("pres.", "gol") per lo stesso motivo degli anni: la stessa PNG va a
    utenti italiani, inglesi e spagnoli. Se mancano i gol (o non hanno senso, come per un
    portiere) si mostrano le sole presenze."""
    apps = stop.get("apps")
    goals = stop.get("goals")
    if not isinstance(apps, int):
        return None
    if isinstance(goals, int):
        return f"{apps} ({goals})"
    return str(apps)


def _draw_header(draw, title, subtitle, badge=None):
    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=HEADER_COLOR)
    draw.rectangle([0, HEADER_HEIGHT - 3, WIDTH, HEADER_HEIGHT], fill=ACCENT_COLOR)

    title_font = get_font(40, bold=True)
    draw.text((PADDING, 44), _truncate(draw, title, title_font, WIDTH - 2 * PADDING - 220), font=title_font, fill=TEXT_COLOR)
    if subtitle:
        subtitle_font = get_font(23)
        draw.text((PADDING, 96), _truncate(draw, subtitle, subtitle_font, WIDTH - 2 * PADDING - 220), font=subtitle_font, fill=MUTED_COLOR)

    if badge:
        badge_font = get_font(22, bold=True)
        text_width = draw.textlength(badge, font=badge_font)
        pill_width = text_width + 40
        x1 = WIDTH - PADDING
        x0 = x1 - pill_width
        draw.rounded_rectangle([x0, 42, x1, 86], radius=22, fill=ACCENT_COLOR)
        draw.text(((x0 + x1) / 2, 64), badge, font=badge_font, fill=(8, 24, 16), anchor="mm")


def _draw_footer(draw, y, text):
    if not text:
        return
    draw.text((PADDING, y + 18), text, font=get_font(20), fill=(96, 116, 136))


def render_career_path_image(career, title="Percorso misterioso", subtitle=None, badge=None, footer=None):
    """Immagine PNG (bytes) del percorso di squadre/anni, senza mai rivelare il calciatore.
    `career` e' la lista di tappe come in players.json."""
    career = list(career or [])
    rows = len(career)
    layout = _layout_for(rows)
    row_height, row_gap = layout["row_height"], layout["row_gap"]
    body_height = rows * row_height + max(rows - 1, 0) * row_gap
    height = HEADER_HEIGHT + PADDING + body_height + FOOTER_HEIGHT

    img = _vertical_gradient(WIDTH, height, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    if subtitle is None:
        subtitle = f"{rows} tappe" if rows != 1 else "1 tappa"
    _draw_header(draw, title, subtitle, badge)

    longest = max((_stint_years(stop) for stop in career), default=1)
    team_font = get_font(layout["team_size"], bold=True)
    meta_font = get_font(layout["meta_size"])
    years_font = get_font(layout["years_size"], bold=True)

    # La linea della timeline va disegnata prima dei nodi, altrimenti li attraversa.
    centers = [HEADER_HEIGHT + PADDING + i * (row_height + row_gap) + row_height / 2 for i in range(rows)]
    if len(centers) > 1:
        draw.line([TIMELINE_X, centers[0], TIMELINE_X, centers[-1]], fill=TRACK_COLOR, width=3)

    for index, stop in enumerate(career):
        y0 = HEADER_HEIGHT + PADDING + index * (row_height + row_gap)
        y1 = y0 + row_height
        center_y = centers[index]

        team_name = stop.get("team", "?")
        club_color = _color_for_team(team_name)

        is_loan = bool(stop.get("loan"))

        draw.rounded_rectangle([CARD_X, y0, CARD_RIGHT, y1], radius=18, fill=CARD_COLOR, outline=CARD_EDGE)
        # Barretta piena = tappa a titolo definitivo, tratteggiata = prestito. E' il secondo
        # segnale (l'altro e' la freccia sugli anni): a colpo d'occhio si distingue una
        # carriera fatta di prestiti da una fatta di trasferimenti.
        if is_loan:
            dash, gap = 14, 9
            edge_y = y0 + 6
            while edge_y < y1 - 6:
                draw.rounded_rectangle(
                    [CARD_X, edge_y, CARD_X + 8, min(edge_y + dash, y1 - 6)], radius=4, fill=club_color
                )
                edge_y += dash + gap
        else:
            draw.rounded_rectangle([CARD_X, y0, CARD_X + 8, y1], radius=4, fill=club_color)

        badge_size = layout["badge"]
        badge_x = CARD_X + 26
        badge_y = center_y - badge_size / 2
        draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], fill=club_color)
        draw.text(
            (badge_x + badge_size / 2, badge_y + badge_size / 2),
            _initials(team_name),
            font=get_font(int(badge_size * 0.41), bold=True),
            fill=(16, 24, 32),
            anchor="mm",
        )

        years_text = _years_label(stop)
        years_width = draw.textlength(years_text, font=years_font)
        draw.text(
            (CARD_RIGHT - 26, center_y - row_height * 0.13),
            years_text, font=years_font, fill=TEXT_COLOR, anchor="rm",
        )

        text_x = badge_x + badge_size + 22
        text_limit = CARD_RIGHT - 26 - years_width - 30 - text_x

        draw.text(
            (text_x, y0 + row_height * 0.21),
            _truncate(draw, team_name, team_font, text_limit), font=team_font, fill=TEXT_COLOR,
        )

        league = stop.get("league") or ""
        country = stop.get("country") or ""
        meta_line = " · ".join(part for part in (league, country) if part)
        if meta_line:
            draw.text(
                (text_x, y0 + row_height * 0.58),
                _truncate(draw, meta_line, meta_font, text_limit), font=meta_font, fill=MUTED_COLOR,
            )

        # Sotto gli anni: presenze e gol se li abbiamo, altrimenti la barra proporzionale
        # alla durata della tappa. Non entrambi — occupano lo stesso posto, e le due
        # informazioni si sovrapporrebbero. Fra le due vincono i numeri: dicono qualcosa che
        # gli anni non dicono gia' (un titolare e una comparsa possono restare i soliti tre
        # anni), mentre la barra e' solo un altro modo di leggere le date.
        stats_text = _stats_label(stop)
        bar_y = y1 - row_height * 0.19
        bar_max = layout["bar_max"]
        bar_x0 = CARD_RIGHT - 26 - bar_max
        if stats_text:
            draw.text(
                (CARD_RIGHT - 26, bar_y + 3), stats_text,
                font=get_font(layout["meta_size"]), fill=MUTED_COLOR, anchor="rm",
            )
        else:
            draw.rounded_rectangle([bar_x0, bar_y, CARD_RIGHT - 26, bar_y + 6], radius=3, fill=TRACK_COLOR)
            filled = max(int(bar_max * _stint_years(stop) / longest), 8)
            draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + filled, bar_y + 6], radius=3, fill=club_color)

        # Il prestito e' gia' detto due volte (barretta tratteggiata e freccia sugli anni):
        # differenziare anche il nodo con un anello piu' sottile non si distingueva a
        # occhio, quindi sarebbe stato un segnale finto.
        draw.ellipse([TIMELINE_X - 11, center_y - 11, TIMELINE_X + 11, center_y + 11], fill=club_color)
        draw.ellipse([TIMELINE_X - 5, center_y - 5, TIMELINE_X + 5, center_y + 5], fill=HEADER_COLOR)

    _draw_footer(draw, HEADER_HEIGHT + PADDING + body_height, footer or "Guess the Player")

    return _to_buffer(img, "path.png")


def render_event_banner(name, description="", badge_text="EVENTO"):
    """Banner di un evento tematico quando non c'e' un'immagine dedicata (`event_img`)."""
    height = 340
    img = _vertical_gradient(WIDTH, height, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    badge_font = get_font(22, bold=True)
    badge_width = draw.textlength(badge_text, font=badge_font) + 44
    draw.rounded_rectangle([PADDING, 46, PADDING + badge_width, 92], radius=23, fill=ACCENT_COLOR)
    draw.text((PADDING + badge_width / 2, 69), badge_text, font=badge_font, fill=(8, 24, 16), anchor="mm")

    name_font = get_font(46, bold=True)
    draw.text((PADDING, 128), _truncate(draw, name, name_font, WIDTH - 2 * PADDING), font=name_font, fill=TEXT_COLOR)

    if description:
        desc_font = get_font(24)
        for i, line in enumerate(_wrap(draw, description, desc_font, WIDTH - 2 * PADDING)[:3]):
            draw.text((PADDING, 202 + i * 34), line, font=desc_font, fill=MUTED_COLOR)

    draw.rectangle([0, height - 6, WIDTH, height], fill=ACCENT_COLOR)
    return _to_buffer(img, "event_banner.png")


def render_transfer_image(stop_from, stop_to, title="Trasferimento misterioso"):
    """Evento transfer_guess: si mostra solo la squadra di arrivo con l'anno."""
    return render_career_path_image([stop_to], title=title, subtitle="Chi si è trasferito qui?")


def render_palmares_image(title="Palmarès", subtitle=None, trophies=0):
    """Sfondo della schermata trofei. Prima era un PNG su un hosting esterno: una card
    generata qui non puo' sparire e resta coerente con il resto della grafica."""
    height = 300
    img = _vertical_gradient(WIDTH, height, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, 6], fill=ACCENT_COLOR)

    title_font = get_font(52, bold=True)
    draw.text((WIDTH / 2, 118), title, font=title_font, fill=TEXT_COLOR, anchor="mm")

    if subtitle:
        draw.text((WIDTH / 2, 176), subtitle, font=get_font(24), fill=MUTED_COLOR, anchor="mm")

    # Righino di "medaglie" proporzionale ai trofei, senza usare emoji (il font non le ha).
    shown = min(trophies, 12)
    if shown:
        spacing = 46
        start_x = WIDTH / 2 - (shown - 1) * spacing / 2
        for i in range(shown):
            cx = start_x + i * spacing
            draw.ellipse([cx - 16, 224, cx + 16, 256], fill=ACCENT_COLOR if i < 3 else TRACK_COLOR)

    return _to_buffer(img, "palmares.png")


def render_avatar(name, size=400):
    """Avatar di riserva per chi non ha foto profilo: iniziali su un cerchio del colore
    derivato dal nome. Sostituisce l'icona presa da un sito esterno."""
    img = _vertical_gradient(size, size, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    color = _color_for_team(name or "?")
    margin = size * 0.14
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    draw.text(
        (size / 2, size / 2),
        _initials(name or "?"),
        font=get_font(int(size * 0.34), bold=True),
        fill=(16, 24, 32),
        anchor="mm",
    )
    return _to_buffer(img, "avatar.png")


def _wrap(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _to_buffer(img, name):
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = name
    return buffer
