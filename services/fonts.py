"""Risoluzione dei font usati dalle immagini generate con Pillow.

`ImageFont.load_default()` e' un font bitmap: leggibile, ma e' il motivo per cui le card
generate sembravano "da terminale". Qui si cerca un TrueType vero, in quest'ordine:

1. `assets/fonts/` nel repo, se un font ci viene messo (ha la precedenza su tutto: e' il
   modo per avere la stessa resa identica ovunque);
2. `FONT_REGULAR_PATH` / `FONT_BOLD_PATH` da variabile d'ambiente, per cambiarlo senza
   ridistribuire il codice;
3. i font di sistema: DejaVu sul container (`fonts-dejavu-core` nel Dockerfile), Arial o
   Segoe UI su Windows, Helvetica su macOS;
4. `load_default()` come rete di sicurezza: l'immagine esce comunque, solo piu' brutta.

I font caricati sono in cache per (percorso, dimensione): `truetype()` rilegge il file ogni
volta, e un'immagine ne chiede una decina.
"""
import os
from typing import Any

from PIL import ImageFont

ASSETS_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

_REGULAR_CANDIDATES = (
    os.path.join(ASSETS_FONT_DIR, "Inter-Regular.ttf"),
    os.path.join(ASSETS_FONT_DIR, "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)

_BOLD_CANDIDATES = (
    os.path.join(ASSETS_FONT_DIR, "Inter-Bold.ttf"),
    os.path.join(ASSETS_FONT_DIR, "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)

_cache: dict = {}


def _first_existing(candidates, env_var):
    override = os.getenv(env_var)
    if override and os.path.exists(override):
        return override
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def font_path(bold=False):
    """Percorso del font scelto, o None se sul sistema non ce n'e' nessuno."""
    key = ("path", bold)
    if key not in _cache:
        _cache[key] = (
            _first_existing(_BOLD_CANDIDATES, "FONT_BOLD_PATH")
            if bold
            else _first_existing(_REGULAR_CANDIDATES, "FONT_REGULAR_PATH")
        )
    return _cache[key]


def get_font(size, bold=False):
    key = (size, bold)
    if key in _cache:
        return _cache[key]

    path = font_path(bold) or font_path(not bold)
    font: Any = None
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except OSError:
            font = None
    if font is None:
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:  # Pillow < 9.2: load_default() non accetta size
            font = ImageFont.load_default()

    _cache[key] = font
    return font


def has_truetype():
    """Vero se stiamo davvero disegnando con un TrueType (usato dai test e da /admin_status
    per accorgersi che sul container manca il pacchetto dei font)."""
    return font_path() is not None


def reset_cache():
    _cache.clear()
