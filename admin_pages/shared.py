"""Shared widgets, queries and dataset editor helpers."""
import asyncio as asyncio
import os as os
from datetime import datetime

import streamlit as st

from config import ADMIN_TELEGRAM_IDS as ADMIN_TELEGRAM_IDS
from config import BOT_TOKEN as BOT_TOKEN
from services import content_admin as content_admin
from services import dataset_editor as dataset_editor
from services import firebase_service as firebase_service
from services.content_admin import ContentAdminError as ContentAdminError
from services.daily_challenge import MAX_ATTEMPTS as MAX_ATTEMPTS
from services.daily_generator import ensure_daily_buffer as ensure_daily_buffer
from services.dataset_editor import DatasetEditError as DatasetEditError
from services.dataset_health import build_report
from services.dates import ITALY_TZ as ITALY_TZ
from services.dates import to_display as to_display
from services.dates import to_iso as to_iso
from services.dates import today_iso as today_iso
from services.difficulty import DIFFICULTY_ORDER as DIFFICULTY_ORDER
from services.difficulty import compute_difficulty as compute_difficulty
from services.difficulty import compute_difficulty_score as compute_difficulty_score
from services.difficulty import explain_difficulty as explain_difficulty
from services.event_generator import load_templates as load_templates
from services.event_generator import maybe_generate_event as maybe_generate_event
from services.i18n import SUPPORTED_LANGUAGES as SUPPORTED_LANGUAGES
from services.manual_event_service import (
    ManualEventError,
)
from services.manual_event_service import create_manual_event as create_manual_event
from services.manual_event_service import parse_answers as parse_answers
from services.manual_event_service import parse_start_date as parse_start_date
from services.path_image import render_career_path_image as render_career_path_image
from services.player_pool import (
    get_all_players,
)
from services.player_pool import get_incomplete_or_unverified_players as get_incomplete_or_unverified_players
from services.player_pool import get_player_by_id as get_player_by_id
from services.player_pool import load_config as load_config

CACHE_TTL_SECONDS = 45

STATUS_ICON = {
    content_admin.STATUS_PAST: "⚪",
    content_admin.STATUS_TODAY: "🟢",
    content_admin.STATUS_PLANNED: "🔵",
    content_admin.STATUS_MISSING: "🔴",
}
EVENT_STATUS_ICON = {
    content_admin.EVENT_STATUS_RUNNING: "🟢",
    content_admin.EVENT_STATUS_PLANNED: "🔵",
    content_admin.EVENT_STATUS_ENDED: "⚪",
}


# ---------------------------------------------------------------------------
# Utilità comuni: cache delle letture, messaggi, conferme
#
# Ogni interazione con un widget fa ripartire lo script dall'inizio: senza cache, ogni
# click rileggerebbe da capo Firestore (letture fatturate). Le letture stanno quindi dietro
# st.cache_data, e ogni scrittura svuota la cache e ricarica la pagina.
# ---------------------------------------------------------------------------

def flash(kind, message):
    st.session_state["flash"] = (kind, message)


def render_flash():
    kind, message = st.session_state.pop("flash", (None, None))
    if kind:
        getattr(st, kind)(message)


def after_write(message):
    st.cache_data.clear()
    flash("success", message)
    st.rerun()


def guarded(action, success_message):
    """Esegue una modifica mostrando l'errore in chiaro invece del traceback di Streamlit."""
    try:
        result = action()
    except ContentAdminError as e:
        st.error(str(e))
    except ManualEventError as e:
        st.error(str(e))
    except DatasetEditError as e:
        st.error(str(e))
    except Exception as e:  # noqa: BLE001 - in dashboard l'errore va mostrato, non nascosto
        st.error(f"Errore: {type(e).__name__}: {e}")
    else:
        after_write(success_message(result) if callable(success_message) else success_message)


def confirm_button(label, key, help_text="Operazione non reversibile."):
    """Bottone distruttivo: si attiva solo dopo aver spuntato la conferma."""
    confirmed = st.checkbox("Confermo", key=f"confirm_{key}", help=help_text)
    return st.button(label, key=f"btn_{key}", type="primary", disabled=not confirmed)


# ---------------------------------------------------------------------------
# Dataset: dalla tabella modificata all'elenco delle modifiche
#
# st.data_editor restituisce la tabella intera, non le celle toccate: il "cosa e'
# cambiato" si ricava confrontando riga per riga con quella di partenza. Le regole di
# validita' e la scrittura del file stanno in services/dataset_editor.py.
# ---------------------------------------------------------------------------

DATASET_STATUSES = [
    dataset_editor.STATUS_SELECTABLE,
    dataset_editor.STATUS_PRACTICE,
    dataset_editor.STATUS_BLOCKED,
    dataset_editor.STATUS_UNVERIFIED,
    dataset_editor.STATUS_INCOMPLETE,
]

# Colonna modificabile della tabella -> campo della scheda.
DATASET_COLUMN_FIELDS = {
    "notorietà": "popularity",
    "verificato": "verified",
    "allenamento": "practice_only",
}


def count_label(n, one, many):
    """Contatore al singolare o al plurale: 1 modifica, 3 modifiche."""
    return f"{n} {one if n == 1 else many}"


def as_records(edited):
    """Le righe di st.data_editor come lista di dizionari, qualunque cosa restituisca."""
    if hasattr(edited, "to_dict"):
        return edited.to_dict("records")
    return list(edited)


def collect_player_changes(before_rows, edited):
    changes = {}
    for before, after in zip(before_rows, as_records(edited)):
        fields = {}
        for column, field in DATASET_COLUMN_FIELDS.items():
            new_value = after.get(column)
            if new_value is None:
                continue
            if field == "popularity":
                new_value = int(new_value)
            else:
                new_value = bool(new_value)
            if new_value != before[column]:
                fields[field] = new_value
        if fields:
            changes[before["id"]] = fields
    return changes


def save_player_changes(changes, career_changes=None):
    result = dataset_editor.apply_player_changes(changes, career_changes)
    _reset_dataset_editors()
    return result


def save_difficulty_settings(thresholds, weights):
    result = dataset_editor.update_difficulty_settings(thresholds, weights)
    _reset_dataset_editors()
    return result


def _reset_dataset_editors():
    """Le tabelle modificabili tengono le modifiche per posizione di riga: dopo un
    salvataggio la chiave del widget deve cambiare, altrimenti Streamlit le riapplica alla
    tabella ricaricata e le modifiche appena scritte sembrano ancora in sospeso."""
    st.session_state["dataset_rev"] = st.session_state.get("dataset_rev", 0) + 1


def fmt_dt(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        try:
            return value.astimezone(ITALY_TZ).strftime("%d/%m/%y %H:%M")
        except (ValueError, OSError):
            return value.strftime("%d/%m/%y %H:%M")
    return str(value)


def fmt_bool(value, yes="sì", no="no", unknown="—"):
    if value is None:
        return unknown
    return yes if value else no


def career_rows(career):
    # Gli anni sono numeri, ma "—" e "oggi" no: Streamlit serializza le tabelle con Arrow,
    # che vuole un tipo solo per colonna. Le colonne miste diventano testo.
    return [
        {
            "#": i,
            "squadra": stop.get("team", "?"),
            "paese": stop.get("country", "—"),
            "campionato": stop.get("league", "—"),
            "dal": str(stop.get("start_year") or "—"),
            "al": str(stop.get("end_year") or "oggi"),
        }
        for i, stop in enumerate(career, start=1)
    ]


def show_table(rows, empty_message="Niente da mostrare."):
    if not rows:
        st.caption(empty_message)
        return
    st.dataframe(rows, width="stretch", hide_index=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_daily_window(days_back, days_ahead, today):
    return content_admin.list_daily_window(days_back, days_ahead, today=today)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_buffer_health(today):
    return content_admin.buffer_health(today=today)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_events(limit):
    return firebase_service.get_recent_events(limit=limit)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_participants(event_code):
    return firebase_service.get_event_participants(event_code)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_overview():
    return firebase_service.get_admin_overview()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_blocked_ids():
    return firebase_service.get_blocked_player_ids()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_top_users(field, limit):
    return firebase_service.get_top_users(field=field, limit=limit)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_leagues(limit):
    return firebase_service.list_leagues(limit=limit)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_dataset_report(blocked_ids):
    return build_report(exclude_ids=list(blocked_ids))


@st.cache_data(ttl=600, show_spinner=False)
def cached_player_options():
    """Etichette dei giocatori per le tendine di scelta: dipendono solo dal dataset locale,
    quindi si possono tenere in cache a lungo."""
    options = {}
    for player in sorted(get_all_players(), key=lambda p: p.get("full_name", "")):
        label = (
            f"{player['full_name']} — {player['id']} "
            f"({compute_difficulty(player)}, {len(player['career'])} tappe)"
        )
        options[label] = player["id"]
    return options


def player_picker(key, label="Giocatore dal dataset"):
    options = cached_player_options()
    if not options:
        st.warning("Nessun giocatore selezionabile nel dataset.")
        return None
    choice = st.selectbox(label, list(options), key=key, index=None, placeholder="Cerca per nome o id…")
    return options.get(choice) if choice else None


