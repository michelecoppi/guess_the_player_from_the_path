# ruff: noqa: E402, F401, I001
"""Accesso a Firestore.

Convenzioni del modello dati (vedi docs/firebase_review.md per il perche'):

- `users/{telegram_id}`: l'id Telegram e' l'id del documento, quindi ogni accesso e' una
  lettura diretta e la creazione e' un upsert atomico (niente utenti duplicati).
- I contatori giornalieri non vengono azzerati da un job notturno: ogni documento porta con
  se' il giorno a cui si riferisce (`last_played_day`), e i contatori valgono zero appena il
  giorno cambia. Costo del reset: nessuno.
- Le date sono salvate in ISO `YYYY-MM-DD` (services/dates.py), cosi' gli id documento sono
  ordinabili e si possono fare query di intervallo.
- Quello che deve essere assegnato "una volta sola" (il bonus al primo che indovina) passa
  da una transazione, non da un controllo seguito da una scrittura.
- Il documento utente ha **tutti** i campi fin dalla creazione, e `/start` completa quelli
  che mancano a chi si era registrato prima che esistessero (`USER_FIELD_DEFAULTS`): un campo
  assente non e' equivalente a uno a zero, perche' una query ordinata o di disuguaglianza
  salta i documenti in cui il campo non c'e'.
- I partecipanti a un evento sono documenti separati (`events/{code}/participants/{id}`), non
  una mappa dentro l'evento: niente limite di 1 MB e niente contesa in scrittura.
"""
import copy
import logging
import os
import time
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core.exceptions import GoogleAPICallError

from config import FIREBASE_CREDENTIALS_PATH
from services.dates import (
    normalize_day,
    now_italy,
    parse_iso,
    shift_iso,
    today_iso,
)
from services.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from services.streak import next_streak, streak_bonus

USERS_COLLECTION = "users"
DAILY_PATH_COLLECTION = "daily_path"
EVENTS_COLLECTION = "events"
PARTICIPANTS_SUBCOLLECTION = "participants"
SEASONS_COLLECTION = "seasons"
ADMIN_SETTINGS_COLLECTION = "admin_settings"
DATASET_OVERRIDES_DOC = "dataset_overrides"
FATHER_SON_COLLECTION = "father_son_pairs"
ARCHIVE_SUBCOLLECTION = "archive"
HISTORY_SUBCOLLECTION = "history"
LEAGUES_COLLECTION = "leagues"
MEMBERS_SUBCOLLECTION = "members"
# Gli acquisti in Stelle stanno in una collection loro, con l'id della transazione Telegram
# come id documento: e' l'unico dato che Telegram ci ridara' se un giorno bisogna rimborsare,
# e cercarlo dentro i documenti utente vorrebbe dire scorrerli tutti.
PURCHASES_COLLECTION = "purchases"
GROUP_ROUNDS_COLLECTION = "group_rounds"
GROUP_PLAYERS_SUBCOLLECTION = "players"


def _credentials():
    """Il file di chiave se c'e', altrimenti le credenziali di default dell'ambiente.

    Il file resta il modo normale (sviluppo e Cloud Run). Il ripiego serve a chi gira senza
    chiave perche' l'identita' gliela da' l'ambiente: il workflow di backup su GitHub
    Actions si autentica con Workload Identity Federation, e una chiave di servizio in un
    secret sarebbe esattamente il file che quel meccanismo esiste per non avere."""
    if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        return credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    logging.info("[FIREBASE] Nessun file di credenziali: uso le credenziali di default dell'ambiente")
    return credentials.ApplicationDefault()


class _LazyFirestoreClient:
    """Inizializza Firebase/Firestore solo al primo utilizzo reale (non all'import del
    modulo). Permette di importare services.firebase_service e i moduli che ne dipendono
    (es. nei test) senza dover avere per forza le credenziali configurate."""

    _client = None
    _lock = Lock()

    def _ensure(self):
        if _LazyFirestoreClient._client is None:
            with _LazyFirestoreClient._lock:
                if _LazyFirestoreClient._client is None:
                    if not firebase_admin._apps:
                        firebase_admin.initialize_app(_credentials())
                    _LazyFirestoreClient._client = firestore.client()
        return _LazyFirestoreClient._client

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


db = _LazyFirestoreClient()


# ---------------------------------------------------------------------------
# Utenti
# ---------------------------------------------------------------------------


# Il documento utente "completo", campo per campo, con il valore che vale come "non ha mai
# fatto niente". E' la sola definizione: la usano sia la creazione (/start di chi arriva
# adesso) sia il ripristino dei documenti vecchi, cosi' non possono divergere.
#
# Perche' serve un ripristino: i campi si sono aggiunti col tempo (la lingua, la striscia,
# le sessioni di archivio/allenamento/evento) e chi si era registrato prima e' rimasto senza.
# `save_user` sul documento gia' esistente non scriveva niente, quindi quei campi non
# comparivano **mai**: /start rispondeva in italiano a un utente inglese (lingua assente ->
# ripiego sul default) mentre i bottoni del menu uscivano nella lingua del client, e la
# lingua rilevata non veniva salvata nemmeno allora.
# L'annotazione serve a mypy: da quando c'e' `cosmetics` i valori non sono piu' tutti
# dello stesso tipo, e senza tipo esplicito l'inferenza si ferma.
USER_FIELD_DEFAULTS: dict[str, Any] = {
    "referral_qualified": 0,
    "chat_id": -1,
    "notifications_enabled": False,
    "monthly_points": 0,
    "points_totali": 0,
    "daily_attempts": 0,
    "daily_hints": 0,
    "has_guessed_today": False,
    "last_played_day": None,
    "trophies": [],
    "players_guessed": 0,
    "bonus_first_guessed": 0,
    "solved_in": {},
    "last_correct_day": None,
    "current_streak": 0,
    "best_streak": 0,
    "archive_day": None,
    "archive_solved": 0,
    "training_key": None,
    "training_attempts": 0,
    "training_solved": 0,
    "event_key": None,
    "leagues": [],
    # Cosmetici comprati in Stelle, traguardi guadagnati giocando, trofei appesi al profilo,
    # e cosa ha addosso adesso.
    # `owned` non elenca gli oggetti gratuiti: quelli li hanno tutti per definizione
    # (services/shop.py), e scriverli qui vorrebbe dire ripassare su ogni utente ogni volta
    # che se ne aggiunge uno. `earned` invece si scrive, ed e' separato da `owned` perche' i
    # due rispondono a domande diverse: da `owned` si ritira quando si rimborsa un acquisto.
    "cosmetics": {"owned": [], "earned": [], "pinned": [], "equipped": {}},
}


# ---------------------------------------------------------------------------
# I traguardi del negozio
#
# Un traguardo (services/shop.py, gli oggetti con `achievement`) si ricava da un contatore.
# Finche' resta solo un calcolo e' anche reversibile: basta alzare un obiettivo in
# data/shop.json, o rinominare un id, e chi stava sotto la soglia nuova si ritrova senza un
# distintivo che aveva gia' guadagnato - senza aver fatto niente, e senza che nessuno se ne
# accorga, perche' e' una modifica a un file di dati e non a una riga di codice.
#
# Quindi si scrivono. Una volta sola, nel momento in cui il contatore che li fa scattare si
# muove: e' l'unico istante in cui puo' succedere, e in quell'istante stiamo gia' scrivendo.
# Vanno in `cosmetics.earned` e non in `cosmetics.owned` perche' i due elenchi rispondono a
# domande diverse: da `owned` si ritira quando si rimborsa un acquisto (`revoke_purchase`),
# e da un traguardo non c'e' niente da ritirare.
# ---------------------------------------------------------------------------

# I contatori su cui un traguardo puo' appoggiarsi: quelli che una delle scritture qui sotto
# raccoglie. Un obiettivo appeso a un campo che non e' in questa lista non verrebbe mai messo
# al sicuro, e resterebbe per sempre alla merce' del calcolo. C'e' un test che lo verifica.
HARVESTED_FIELDS = frozenset({
    "referral_qualified",
    "points_totali", "monthly_points", "players_guessed", "current_streak", "best_streak",
    "bonus_first_guessed", "archive_solved", "training_solved",
})


# Compatibility exports: preserve imports and monkeypatch seams during migration.
from services.repos.admin import _count_collection as _count_collection
from services.repos.admin import add_father_son_pair as add_father_son_pair
from services.repos.admin import block_player_id as block_player_id
from services.repos.admin import delete_father_son_pair as delete_father_son_pair
from services.repos.admin import get_admin_overview as get_admin_overview
from services.repos.admin import get_blocked_player_ids as get_blocked_player_ids
from services.repos.admin import list_father_son_pairs as list_father_son_pairs
from services.repos.admin import mark_father_son_pairs_used as mark_father_son_pairs_used
from services.repos.admin import unblock_player_id as unblock_player_id
from services.repos.archive import archive_ref as archive_ref
from services.repos.archive import begin_archive_attempt as begin_archive_attempt
from services.repos.archive import get_archive_days as get_archive_days
from services.repos.archive import get_archive_result as get_archive_result
from services.repos.archive import get_daily_history as get_daily_history
from services.repos.archive import get_solved_archive_days as get_solved_archive_days
from services.repos.archive import get_upcoming_daily_paths as get_upcoming_daily_paths
from services.repos.archive import history_ref as history_ref
from services.repos.archive import record_daily_history as record_daily_history
from services.repos.archive import register_archive_solved as register_archive_solved
from services.repos.archive import set_archive_day as set_archive_day
from services.repos.challenges import claim_daily_first_correct as claim_daily_first_correct
from services.repos.challenges import count_day_winners as count_day_winners
from services.repos.challenges import daily_path_exists as daily_path_exists
from services.repos.challenges import daily_path_ref as daily_path_ref
from services.repos.challenges import delete_daily_path as delete_daily_path
from services.repos.challenges import get_daily_path as get_daily_path
from services.repos.challenges import get_daily_paths_range as get_daily_paths_range
from services.repos.challenges import get_daily_stats as get_daily_stats
from services.repos.challenges import get_display_name_for_day as get_display_name_for_day
from services.repos.challenges import get_past_daily_paths as get_past_daily_paths
from services.repos.challenges import get_recent_player_ids as get_recent_player_ids
from services.repos.challenges import register_daily_outcome as register_daily_outcome
from services.repos.challenges import save_daily_path as save_daily_path
from services.repos.challenges import update_daily_path as update_daily_path
from services.repos.events import begin_event_attempt as begin_event_attempt
from services.repos.events import claim_event_first_correct as claim_event_first_correct
from services.repos.events import delete_event as delete_event
from services.repos.events import event_exists as event_exists
from services.repos.events import event_ref as event_ref
from services.repos.events import get_active_events as get_active_events
from services.repos.events import get_current_event as get_current_event
from services.repos.events import get_event as get_event
from services.repos.events import get_event_leaderboard as get_event_leaderboard
from services.repos.events import get_event_participant as get_event_participant
from services.repos.events import get_event_participants as get_event_participants
from services.repos.events import get_event_trophy_day as get_event_trophy_day
from services.repos.events import get_last_event_end_date as get_last_event_end_date
from services.repos.events import get_recent_event_template_ids as get_recent_event_template_ids
from services.repos.events import get_recent_events as get_recent_events
from services.repos.events import participant_ref as participant_ref
from services.repos.events import register_event_correct_guess as register_event_correct_guess
from services.repos.events import save_event as save_event
from services.repos.events import update_event as update_event
from services.repos.events import update_users_trophies as update_users_trophies
from services.repos.groups import add_group_points as add_group_points
from services.repos.groups import begin_group_attempt as begin_group_attempt
from services.repos.groups import claim_group_round as claim_group_round
from services.repos.groups import get_group_leaderboard as get_group_leaderboard
from services.repos.groups import get_group_round as get_group_round
from services.repos.groups import group_player_ref as group_player_ref
from services.repos.groups import group_round_ref as group_round_ref
from services.repos.groups import start_group_round as start_group_round
from services.repos.leagues import add_points_to_leagues as add_points_to_leagues
from services.repos.leagues import create_league as create_league
from services.repos.leagues import get_league as get_league
from services.repos.leagues import get_league_leaderboard as get_league_leaderboard
from services.repos.leagues import join_league as join_league
from services.repos.leagues import league_ref as league_ref
from services.repos.leagues import leave_league as leave_league
from services.repos.leagues import list_leagues as list_leagues
from services.repos.leagues import member_ref as member_ref
from services.repos.seasons import get_or_create_season as get_or_create_season
from services.repos.shop import deliver_purchase as deliver_purchase
from services.repos.shop import equip_cosmetic as equip_cosmetic
from services.repos.shop import equip_look as equip_look
from services.repos.shop import get_purchase as get_purchase
from services.repos.shop import get_user_purchases as get_user_purchases
from services.repos.shop import pin_trophies as pin_trophies
from services.repos.shop import purchase_ref as purchase_ref
from services.repos.shop import reserve_checkout as reserve_checkout
from services.repos.shop import revoke_purchase as revoke_purchase
from services.repos.shop import save_looks as save_looks
from services.repos.users import _bump_counters as _bump_counters
from services.repos.users import _newly_earned as _newly_earned
from services.repos.users import _public_user as _public_user
from services.repos.users import add_user_trophy as add_user_trophy
from services.repos.users import begin_guess_attempt as begin_guess_attempt
from services.repos.users import clear_event_key as clear_event_key
from services.repos.users import clear_training_key as clear_training_key
from services.repos.users import count_users_ahead as count_users_ahead
from services.repos.users import delete_user_data as delete_user_data
from services.repos.users import find_users_by_first_name as find_users_by_first_name
from services.repos.users import get_broadcast_users as get_broadcast_users
from services.repos.users import get_top_users as get_top_users
from services.repos.users import get_user_daily_status as get_user_daily_status
from services.repos.users import get_user_data as get_user_data
from services.repos.users import get_user_language as get_user_language
from services.repos.users import missing_user_fields as missing_user_fields
from services.repos.users import new_user_document as new_user_document
from services.repos.users import register_correct_guess as register_correct_guess
from services.repos.users import register_training_attempt as register_training_attempt
from services.repos.users import register_training_solved as register_training_solved
from services.repos.users import reset_monthly_points as reset_monthly_points
from services.repos.users import save_user as save_user
from services.repos.users import set_event_key as set_event_key
from services.repos.users import set_training_key as set_training_key
from services.repos.users import set_user_language as set_user_language
from services.repos.users import set_user_notifications as set_user_notifications
from services.repos.users import take_daily_hint as take_daily_hint
from services.repos.users import update_user_fields as update_user_fields
from services.repos.users import user_ref as user_ref
