import hashlib
import io

from PIL import Image, ImageDraw, ImageFont

WIDTH = 900
ROW_HEIGHT = 110
HEADER_HEIGHT = 130
PADDING = 30

BG_COLOR = (18, 32, 47)
HEADER_COLOR = (10, 20, 32)
ROW_COLORS = [(28, 48, 68), (22, 40, 58)]
TEXT_COLOR = (235, 240, 245)
ACCENT_COLOR = (56, 189, 130)
MUTED_COLOR = (150, 165, 180)


def _font(size, bold=False):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _color_for_team(team_name):
    digest = hashlib.md5(team_name.encode("utf-8")).hexdigest()
    r = 90 + int(digest[0:2], 16) % 120
    g = 90 + int(digest[2:4], 16) % 120
    b = 90 + int(digest[4:6], 16) % 120
    return (r, g, b)


def render_career_path_image(career, title="Percorso misterioso", subtitle=None):
    """Genera un'immagine PNG (bytes) che mostra il percorso di squadre/anni SENZA rivelare
    il nome del calciatore. 'career' e' la lista di tappe come in players.json."""
    n = len(career)
    height = HEADER_HEIGHT + n * ROW_HEIGHT + PADDING

    img = Image.new("RGB", (WIDTH, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=HEADER_COLOR)
    title_font = _font(38)
    subtitle_font = _font(22)
    draw.text((PADDING, 28), title, font=title_font, fill=TEXT_COLOR)
    if subtitle:
        draw.text((PADDING, 78), subtitle, font=subtitle_font, fill=MUTED_COLOR)

    team_font = _font(30)
    meta_font = _font(22)

    for i, stop in enumerate(career):
        y0 = HEADER_HEIGHT + i * ROW_HEIGHT
        y1 = y0 + ROW_HEIGHT
        draw.rectangle([0, y0, WIDTH, y1], fill=ROW_COLORS[i % 2])

        badge_size = 60
        badge_x, badge_y = PADDING, y0 + (ROW_HEIGHT - badge_size) // 2
        team_name = stop.get("team", "?")
        badge_color = _color_for_team(team_name)
        draw.ellipse(
            [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
            fill=badge_color,
        )
        initials = "".join(w[0].upper() for w in team_name.split()[:2]) or "?"
        initials_font = _font(24)
        draw.text(
            (badge_x + badge_size / 2, badge_y + badge_size / 2),
            initials,
            font=initials_font,
            fill=(20, 20, 20),
            anchor="mm",
        )

        text_x = badge_x + badge_size + 24
        start_year = stop.get("start_year", "?")
        end_year = stop.get("end_year") or "oggi"
        years_label = f"{start_year} - {end_year}"

        draw.text((text_x, y0 + 20), team_name, font=team_font, fill=TEXT_COLOR)
        league = stop.get("league", "")
        country = stop.get("country", "")
        meta_line = f"{years_label}"
        if league or country:
            meta_line += f"  ·  {league}{' (' + country + ')' if country else ''}"
        draw.text((text_x, y0 + 62), meta_line, font=meta_font, fill=MUTED_COLOR)

        draw.line([0, y1, WIDTH, y1], fill=(0, 0, 0), width=1)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = "path.png"
    return buffer


def render_event_banner(name, description="", badge_text="EVENTO"):
    """Banner generico per un evento tematico quando non e' stata caricata un'immagine
    dedicata (event_img). Evita che un evento generato automaticamente resti senza foto."""
    height = 360
    img = Image.new("RGB", (WIDTH, height), HEADER_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, 70], fill=ACCENT_COLOR)
    badge_font = _font(28)
    draw.text((PADDING, 18), badge_text, font=badge_font, fill=(10, 20, 15))

    name_font = _font(46)
    desc_font = _font(24)
    draw.text((PADDING, 130), name, font=name_font, fill=TEXT_COLOR)

    if description:
        words = description.split()
        lines, current = [], ""
        for word in words:
            trial = f"{current} {word}".strip()
            if len(trial) > 60:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        for i, line in enumerate(lines[:3]):
            draw.text((PADDING, 210 + i * 32), line, font=desc_font, fill=MUTED_COLOR)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = "event_banner.png"
    return buffer


def render_transfer_image(stop_from, stop_to, title="Trasferimento misterioso"):
    """Immagine dedicata all'evento transfer_guess: mostra solo la singola tappa (squadra di
    arrivo) con anno, per far indovinare il giocatore dal trasferimento."""
    return render_career_path_image([stop_to], title=title, subtitle="Chi si e' trasferito qui?")
