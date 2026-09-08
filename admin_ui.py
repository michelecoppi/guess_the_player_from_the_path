"""Dashboard locale per gestire il bot da PC, senza Telegram e senza hosting aggiuntivo.

Riusa esattamente gli stessi servizi (Firestore, dataset, generatori) usati da
handlers/admin_handler.py: nessuna logica duplicata, solo un'interfaccia diversa. Le
modifiche ai documenti passano da services/content_admin.py, che applica le regole del
gioco (anti-ripetizione, coerenza fra date e contenuti, bonus gia' assegnati) invece di
scrivere campi a caso.

Va lanciata in locale con le stesse credenziali del bot (.env, firebase-key.json).

Uso: streamlit run admin_ui.py
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Sotto lo script runner di Streamlit, la ricerca automatica di python-dotenv (che risale
# dal frame del chiamante) parte dalla cartella sbagliata e non trova l'.env: lo carichiamo
# esplicitamente da qui prima di importare config, cosi' FIREBASE_CREDENTIALS_PATH & co.
# risultano gia' in os.environ quando config.py fa il suo load_dotenv().
_PROJECT_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH)

st.set_page_config(page_title="Guess the Player — Admin", layout="wide")

if not os.getenv("FIREBASE_CREDENTIALS_PATH") or not os.getenv("BOT_TOKEN"):
    st.error(
        "Configurazione mancante: FIREBASE_CREDENTIALS_PATH e/o BOT_TOKEN non sono impostati.\n\n"
        f"File .env cercato in: `{_ENV_PATH}`\n"
        f"Esiste: **{_ENV_PATH.exists()}**\n\n"
        "Verifica che il file `.env` sia proprio in questa cartella (non in una sottocartella "
        "o nella cartella da cui lanci il comando) e che contenga le righe "
        "`FIREBASE_CREDENTIALS_PATH=...` e `BOT_TOKEN=...` senza virgolette."
    )
    st.stop()

credentials_path = Path(os.environ["FIREBASE_CREDENTIALS_PATH"])
if not credentials_path.is_absolute():
    credentials_path = _PROJECT_ROOT / credentials_path
if not credentials_path.exists():
    st.error(
        f"Il file delle credenziali Firebase non esiste: `{credentials_path}`\n\n"
        "Controlla il valore di FIREBASE_CREDENTIALS_PATH nel .env: se è un percorso "
        "relativo (es. `firebase-key.json`) deve essere relativo alla cartella del progetto."
    )
    st.stop()
# firebase_service legge FIREBASE_CREDENTIALS_PATH da config.py al momento dell'uso:
# qui lo normalizziamo ad assoluto cosi' funziona indipendentemente dalla cwd da cui parte streamlit.
os.environ["FIREBASE_CREDENTIALS_PATH"] = str(credentials_path)

from config import ADMIN_TELEGRAM_IDS, BOT_TOKEN
from services import content_admin, firebase_service
from services.content_admin import ContentAdminError
from services.daily_challenge import MAX_ATTEMPTS
from services.daily_generator import ensure_daily_buffer
from services.dataset_health import build_report
from services.dates import ITALY_TZ, to_display, to_iso, today_iso
from services.difficulty import (
    DIFFICULTY_ORDER,
    compute_difficulty,
    compute_difficulty_score,
    explain_difficulty,
)
from services.event_generator import load_templates, maybe_generate_event
from services.i18n import SUPPORTED_LANGUAGES
from services.manual_event_service import (
    ManualEventError,
    create_manual_event,
    parse_answers,
    parse_start_date,
)
from services.path_image import render_career_path_image
from services.player_pool import (
    get_all_players,
    get_incomplete_or_unverified_players,
    get_player_by_id,
    load_config,
)

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
    except Exception as e:  # noqa: BLE001 - in dashboard l'errore va mostrato, non nascosto
        st.error(f"Errore: {type(e).__name__}: {e}")
    else:
        after_write(success_message(result) if callable(success_message) else success_message)


def confirm_button(label, key, help_text="Operazione non reversibile."):
    """Bottone distruttivo: si attiva solo dopo aver spuntato la conferma."""
    confirmed = st.checkbox("Confermo", key=f"confirm_{key}", help=help_text)
    return st.button(label, key=f"btn_{key}", type="primary", disabled=not confirmed)


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


# ---------------------------------------------------------------------------
# Intestazione e navigazione
# ---------------------------------------------------------------------------

st.title("🛠️ Guess the Player — Pannello admin locale")

today = today_iso()
now_italy = datetime.now(ITALY_TZ)

PAGES = [
    "📊 Stato generale",
    "📅 Sfide giornaliere",
    "🎊 Eventi",
    "👤 Utenti",
    "🏆 Leghe",
    "📚 Dataset",
    "🚫 Giocatori sospesi",
    "👨‍👦 Coppie padre/figlio",
]
page = st.sidebar.radio("Sezione", PAGES)

st.sidebar.divider()
if st.sidebar.button("🔄 Ricarica dati", width="stretch"):
    st.cache_data.clear()
    st.rerun()
try:
    project_id = firebase_service.db.project
except Exception:  # noqa: BLE001 - il nome del progetto è solo informativo
    project_id = "?"
st.sidebar.caption(
    f"Progetto Firestore: `{project_id}`\n\n"
    f"{now_italy.strftime('%d/%m/%y %H:%M')} (Europe/Rome)\n\n"
    f"Le letture sono in cache per {CACHE_TTL_SECONDS}s."
)
st.sidebar.caption("⚠️ Le modifiche scrivono sul database **di produzione**.")

render_flash()


# ---------------------------------------------------------------------------
# Stato generale
# ---------------------------------------------------------------------------
if page == "📊 Stato generale":
    st.caption(f"Oggi è {to_display(today)} — {now_italy.strftime('%H:%M')} (Europe/Rome)")

    try:
        window = cached_daily_window(1, 7, today)
        health = cached_buffer_health(today)
    except Exception as e:
        window, health = [], None
        st.error(f"Errore leggendo le sfide: {e}")

    by_day = {row["day"]: row for row in window}
    today_row = by_day.get(today)

    col1, col2, col3, col4 = st.columns(4)
    if today_row and today_row["exists"]:
        col1.metric(
            f"Sfida di oggi (#{today_row['challenge_number']})",
            today_row["player_name"] or today_row["player_id"] or "?",
            help="La soluzione della sfida in corso.",
        )
    else:
        col1.metric("Sfida di oggi", "MANCANTE ⚠️")

    if health:
        col2.metric(
            "Giorni coperti da oggi",
            health["covered_days"],
            delta=health["covered_days"] - health["target_days"],
            help=f"Il buffer previsto in data/config.json è di {health['target_days']} giorni.",
        )

    try:
        overview = cached_overview()
        total = overview["users_total"] or 1
        col3.metric("Utenti registrati", overview["users_total"])
        col4.metric(
            "Hanno indovinato oggi",
            f"{overview['users_guessed_today']} ({overview['users_guessed_today'] * 100 // total}%)",
        )
    except Exception as e:
        st.error(f"Errore leggendo gli utenti: {e}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("📅 Prossime sfide")
        show_table(
            [
                {
                    "": STATUS_ICON[row["status"]],
                    "giorno": f"{row['weekday']} {row['day_display']}",
                    "#": row["challenge_number"],
                    "soluzione": row["player_name"] or row["player_id"] or "— nessuna sfida —",
                    "difficoltà": row["difficulty"] or "—",
                }
                for row in window
            ],
            "Nessuna sfida nella finestra.",
        )
        if health and health["missing_days"]:
            st.warning(f"Giorni scoperti nei prossimi 30: {', '.join(to_display(d) for d in health['missing_days'][:10])}")

    with right:
        st.subheader("🎊 Evento")
        try:
            current_event = firebase_service.get_current_event()
        except Exception as e:
            current_event = None
            st.error(f"Errore leggendo gli eventi: {e}")

        if current_event:
            detail = content_admin.describe_event(current_event, today=today)
            st.success(f"**{detail['name']}** [{detail['code']}]")
            st.write(
                f"{detail['period']} — giorno **{detail['current_index'] or '?'} di {detail['days_total']}** — "
                f"tipo `{detail['type']}` — origine `{detail['source']}`"
            )
            st.write(f"Trofei il **{to_display(detail['trophy_day'])}**")
            if not detail["active"]:
                st.warning("L'evento è marcato come non attivo.")
        else:
            st.info("Nessun evento attivo oggi.")

        st.subheader("📚 Dataset")
        try:
            report = cached_dataset_report(tuple(cached_blocked_ids()))
            st.write(
                f"Selezionabili **{report['selectable']}** su {report['total']} — "
                f"autonomia **{report['autonomy_days']} giorni** senza ripetizioni"
            )
            if report["warnings"]:
                st.warning(f"🚨 {len(report['warnings'])} avvisi — vedi la sezione Dataset")
            else:
                st.success("✅ Dataset senza avvisi")
        except Exception as e:
            st.error(f"Errore sul dataset: {e}")

    st.divider()
    if st.button("⏳ Genera subito sfide/eventi mancanti", type="primary"):
        with st.spinner("Generazione in corso..."):
            try:
                generated_days = ensure_daily_buffer()
                event_code = maybe_generate_event()
            except Exception as e:
                st.error(f"Errore: {e}")
            else:
                lines = [f"- {to_display(d['day'])}: {d['player_id']} ({d['difficulty']})" for d in generated_days]
                message = "Nessuna sfida mancante." if not lines else "Sfide generate:\n" + "\n".join(lines)
                message += f"\n\nEventi: {'creato ' + event_code if event_code else 'nessun nuovo evento'}"
                after_write(message)


# ---------------------------------------------------------------------------
# Sfide giornaliere
# ---------------------------------------------------------------------------
elif page == "📅 Sfide giornaliere":
    st.header("📅 Sfide giornaliere pianificate")
    st.caption(
        "Ogni giorno della finestra, comprese le giornate **senza** sfida. "
        f"{STATUS_ICON[content_admin.STATUS_PAST]} passata · "
        f"{STATUS_ICON[content_admin.STATUS_TODAY]} oggi · "
        f"{STATUS_ICON[content_admin.STATUS_PLANNED]} programmata · "
        f"{STATUS_ICON[content_admin.STATUS_MISSING]} mancante"
    )

    col1, col2 = st.columns(2)
    days_back = col1.slider("Giorni passati da mostrare", 0, 30, 3)
    days_ahead = col2.slider("Giorni futuri da mostrare", 1, 60, 14)

    try:
        window = cached_daily_window(days_back, days_ahead, today)
        health = cached_buffer_health(today)
    except Exception as e:
        window, health = [], None
        st.error(f"Errore leggendo le sfide: {e}")

    if health:
        col1, col2, col3 = st.columns(3)
        col1.metric("Giorni coperti da oggi", health["covered_days"])
        col2.metric("Buffer previsto", f"{health['target_days']} giorni")
        col3.metric(
            "Coperto fino al",
            to_display(health["last_covered_day"]) if health["last_covered_day"] else "—",
        )

    show_table(
        [
            {
                "": STATUS_ICON[row["status"]],
                "giorno": f"{row['weekday']} {row['day_display']}",
                "#": row["challenge_number"],
                "soluzione": row["player_name"] or row["player_id"] or "—",
                "difficoltà": row["difficulty"] or "—",
                "punti": str(row["points"]) if row["exists"] else "—",
                "tappe": str(row["teams_count"]) if row["exists"] else "—",
                "origine": row["source"] or "—",
                "bonus primo": "assegnato" if row["first_correct_taken"] else ("libero" if row["exists"] else "—"),
                "verificato": fmt_bool(row["verified"]),
            }
            for row in window
        ],
        "Nessun giorno nella finestra.",
    )

    st.divider()
    st.subheader("🔧 Dettaglio e modifica")
    st.caption(f"Tentativi giornalieri per utente: {MAX_ATTEMPTS} (services/daily_challenge.py)")

    for row in window:
        day = row["day"]
        icon = STATUS_ICON[row["status"]]
        title = (
            f"{icon} {row['weekday']} {row['day_display']} · #{row['challenge_number']} · "
            + (f"{row['player_name'] or row['player_id']} ({row['difficulty']})" if row["exists"] else "nessuna sfida")
        )
        with st.expander(title, expanded=(day == today)):
            if not row["exists"]:
                st.warning("Nessuna sfida per questo giorno: gli utenti non avrebbero niente da giocare.")
                gen_col, pick_col = st.columns([1, 2])
                with gen_col:
                    if st.button("🎲 Genera automaticamente", key=f"gen_{day}"):
                        guarded(
                            lambda d=day: content_admin.regenerate_daily(d, avoid_current=False),
                            lambda r: f"Sfida del {to_display(r['day'])} generata: {r['player_name']} ({r['difficulty']}).",
                        )
                with pick_col:
                    chosen = player_picker(f"pick_missing_{day}", "Oppure scegli il giocatore")
                    if st.button("💾 Imposta questo giocatore", key=f"set_missing_{day}", disabled=not chosen):
                        guarded(
                            lambda d=day, p=chosen: content_admin.set_daily_player(d, p),
                            lambda r: f"Sfida del {to_display(r['day'])} impostata su {r['player_name']}.",
                        )
                continue

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Difficoltà", row["difficulty"] or "—", help=f"Punteggio calcolato: {row['difficulty_score']}")
            m2.metric("Punti in palio", row["points"])
            m3.metric("Tappe di carriera", row["teams_count"])
            m4.metric("Bonus primo", "assegnato" if row["first_correct_taken"] else "libero")

            st.caption(
                f"player_id `{row['player_id']}` · origine `{row['source']}` · "
                f"generata il {fmt_dt(row['generated_at'])} · "
                f"scheda verificata: {fmt_bool(row['verified'])}"
            )
            if not row["player_in_dataset"]:
                st.warning(
                    f"Il giocatore `{row['player_id']}` non esiste più in data/players.json: "
                    "la sfida funziona lo stesso (il percorso è salvato nel documento) ma il dataset è disallineato."
                )

            st.markdown("**Risposte accettate:** " + ", ".join(f"`{a}`" for a in row["answers"]))
            show_table(career_rows(row["career"]), "Percorso vuoto: la sfida non è giocabile.")

            if st.checkbox("🖼️ Anteprima immagine inviata agli utenti", key=f"img_{day}"):
                try:
                    image = render_career_path_image(
                        row["career"],
                        title="Percorso misterioso",
                        subtitle=f"Sfida #{row['challenge_number']}",
                        badge=(row["difficulty"] or "").upper(),
                    )
                    st.image(image, width=520)
                except Exception as e:
                    st.error(f"Impossibile generare l'anteprima: {e}")

            st.markdown("---")
            tab_player, tab_answers, tab_difficulty, tab_bonus, tab_delete = st.tabs(
                ["Cambia giocatore", "Risposte", "Difficoltà", "Bonus primo", "Elimina"]
            )

            with tab_player:
                if row["status"] == content_admin.STATUS_TODAY:
                    st.warning(
                        "Stai modificando la sfida **in corso**: chi ha già usato i tentativi non li recupera."
                    )
                chosen = player_picker(f"pick_{day}", "Nuovo giocatore")
                col_a, col_b = st.columns(2)
                if col_a.button("💾 Sostituisci", key=f"replace_{day}", disabled=not chosen):
                    guarded(
                        lambda d=day, p=chosen: content_admin.set_daily_player(d, p),
                        lambda r: f"Sfida del {to_display(r['day'])} impostata su {r['player_name']}.",
                    )
                if col_b.button("🎲 Rigenera (altro giocatore)", key=f"regen_{day}"):
                    guarded(
                        lambda d=day: content_admin.regenerate_daily(d, avoid_current=True),
                        lambda r: f"Sfida del {to_display(r['day'])} rigenerata: {r['player_name']} ({r['difficulty']}).",
                    )

            with tab_answers:
                st.caption(
                    "Separate da virgola. Vengono salvate in minuscolo: il confronto con la risposta "
                    "dell'utente ignora maiuscole e accenti (services/matching.py)."
                )
                answers_text = st.text_input(
                    "Risposte accettate", value=", ".join(row["answers"]), key=f"answers_{day}"
                )
                if st.button("💾 Salva risposte", key=f"save_answers_{day}"):
                    parsed = content_admin.parse_answers_list(answers_text)
                    guarded(
                        lambda d=day, a=parsed: content_admin.update_daily_answers(d, a),
                        lambda r: f"Risposte del {to_display(day)} aggiornate: {', '.join(r)}.",
                    )

            with tab_difficulty:
                suggested = None
                player = get_player_by_id(row["player_id"] or "")
                if player:
                    suggested = compute_difficulty(player)
                    st.caption(
                        f"Calcolata dal dataset: **{suggested}** "
                        f"(punteggio {round(compute_difficulty_score(player), 2)})"
                    )
                current_index = DIFFICULTY_ORDER.index(row["difficulty"]) if row["difficulty"] in DIFFICULTY_ORDER else 0
                new_difficulty = st.selectbox(
                    "Difficoltà (decide i punti assegnati)", DIFFICULTY_ORDER, index=current_index, key=f"diff_{day}"
                )
                if st.button("💾 Salva difficoltà", key=f"save_diff_{day}"):
                    guarded(
                        lambda d=day, v=new_difficulty: content_admin.update_daily_difficulty(d, v),
                        lambda r: f"Difficoltà del {to_display(day)} impostata su {r}.",
                    )

            with tab_bonus:
                st.caption(
                    "Il bonus del primo che indovina si assegna una volta sola. Riaprirlo ha senso "
                    "solo se la sfida è stata sostituita in corsa."
                )
                st.write(f"Stato attuale: **{'assegnato' if row['first_correct_taken'] else 'libero'}**")
                if row["first_correct_taken"]:
                    if st.button("🔓 Riapri il bonus", key=f"reopen_{day}"):
                        guarded(
                            lambda d=day: content_admin.set_daily_first_correct(d, False),
                            f"Bonus del {to_display(day)} riaperto.",
                        )
                else:
                    if st.button("🔒 Marca come già assegnato", key=f"close_{day}"):
                        guarded(
                            lambda d=day: content_admin.set_daily_first_correct(d, True),
                            f"Bonus del {to_display(day)} chiuso.",
                        )

            with tab_delete:
                if row["status"] == content_admin.STATUS_TODAY:
                    st.info("La sfida di oggi non si elimina: è in gioco. Sostituisci il giocatore o rigenerala.")
                else:
                    st.caption("Il documento `daily_path/" + day + "` viene eliminato definitivamente.")
                    if confirm_button("🗑️ Elimina la sfida", key=f"del_daily_{day}"):
                        guarded(
                            lambda d=day: content_admin.delete_daily(d),
                            f"Sfida del {to_display(day)} eliminata.",
                        )

    st.divider()
    st.subheader("➕ Programma una sfida in una data specifica")
    col1, col2 = st.columns(2)
    target_date = col1.date_input("Giorno", value=None, format="DD/MM/YYYY", key="new_day")
    chosen_new = player_picker("pick_new_day", "Giocatore")
    if col2.button("💾 Programma", type="primary", disabled=not (target_date and chosen_new)):
        guarded(
            lambda d=to_iso(target_date), p=chosen_new: content_admin.set_daily_player(d, p),
            lambda r: f"Sfida del {to_display(r['day'])} programmata su {r['player_name']}.",
        )


# ---------------------------------------------------------------------------
# Eventi
# ---------------------------------------------------------------------------
elif page == "🎊 Eventi":
    st.header("🎊 Eventi")
    st.caption(
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_RUNNING]} in corso · "
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_PLANNED]} programmato · "
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_ENDED]} concluso"
    )

    limit = st.slider("Quanti eventi mostrare", 1, 30, 8)
    try:
        events = cached_events(limit)
    except Exception as e:
        events = []
        st.error(f"Errore leggendo gli eventi: {e}")

    details = [content_admin.describe_event(event, today=today) for event in events]

    show_table(
        [
            {
                "": EVENT_STATUS_ICON[d["status"]],
                "codice": d["code"],
                "nome": d["name"],
                "periodo": d["period"],
                "giorno": f"{d['current_index']}/{d['days_total']}" if d["current_index"] else f"—/{d['days_total']}",
                "tipo": d["type"],
                "origine": d["source"],
                "attivo": fmt_bool(d["active"]),
                "partecipanti": d["participants_count"],
                "trofei il": to_display(d["trophy_day"]),
            }
            for d in details
        ],
        "Nessun evento presente.",
    )

    for detail in details:
        code = detail["code"]
        icon = EVENT_STATUS_ICON[detail["status"]]
        with st.expander(
            f"{icon} {detail['name']} [{code}] — {detail['status']} — {detail['period']}",
            expanded=(detail["status"] == content_admin.EVENT_STATUS_RUNNING),
        ):
            st.write(detail["description"] or "_nessuna descrizione_")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Stato", detail["status"])
            m2.metric(
                "Giorno",
                f"{detail['current_index']}/{detail['days_total']}" if detail["current_index"]
                else f"—/{detail['days_total']}",
            )
            m3.metric("Partecipanti", detail["participants_count"] or 0)
            m4.metric("Trofei il", to_display(detail["trophy_day"]) or "—")

            st.caption(
                f"template `{detail['template_id']}` · tipo `{detail['type']}` · "
                f"categoria `{detail['category']}` · difficoltà `{detail['difficulty']}` · "
                f"origine `{detail['source']}` · attivo: {fmt_bool(detail['active'])} · "
                f"creato il {fmt_dt(detail['generated_at'])}"
            )
            if detail["days_without_content"]:
                st.error(
                    "Giorni dell'evento **senza contenuto**: "
                    + ", ".join(detail["days_without_content"])
                    + ". Chi gioca in quei giorni non trova niente."
                )

            st.markdown("**Giorni dell'evento**")
            show_table(
                [
                    {
                        "": STATUS_ICON[d["status"]],
                        "g.": d["index"],
                        "giorno": f"{d['weekday']} {d['day_display']}",
                        "contenuto": d["player_name"] or d["pair_id"] or ("foto" if d["image_url"] else "—"),
                        "risposte": ", ".join(d["answers"]) if d["answers"] else "— VUOTO —",
                        "min. giuste": str(d["min_correct"]) if d["min_correct"] else "—",
                        "punti": str(d["points"]) if d["points"] is not None else "—",
                        "bonus primo": "assegnato" if d["first_correct_taken"] else "libero",
                    }
                    for d in detail["days"]
                ],
                "L'evento non ha giorni.",
            )

            st.markdown("**Classifica partecipanti**")
            try:
                participants = cached_participants(code)
            except Exception as e:
                participants = []
                st.error(f"Errore leggendo i partecipanti: {e}")
            show_table(
                [
                    {
                        "pos.": i,
                        "telegram_id": str(p.get("telegram_id") or p.get("id") or "—"),
                        "nome": p.get("name", "—"),
                        "punti": p.get("points", 0),
                        "ultimo giorno giocato": to_display(p.get("last_played_day")),
                        "ha indovinato": fmt_bool(p.get("has_guessed_today")),
                        "tentativi oggi": p.get("daily_attempts", 0),
                    }
                    for i, p in enumerate(participants, start=1)
                ],
                "Ancora nessun partecipante.",
            )

            st.markdown("---")
            tab_state, tab_dates, tab_answers, tab_bonus, tab_delete = st.tabs(
                ["Attivazione", "Sposta date", "Risposte di un giorno", "Bonus di giornata", "Elimina"]
            )

            with tab_state:
                st.caption(
                    "Disattivare un evento è il modo pulito per fermarlo: resta lo storico e restano i punti "
                    "già assegnati."
                )
                if detail["active"]:
                    if st.button("⏸️ Disattiva", key=f"deact_{code}"):
                        guarded(lambda c=code: content_admin.set_event_active(c, False), f"Evento {code} disattivato.")
                else:
                    if st.button("▶️ Riattiva", key=f"act_{code}"):
                        guarded(lambda c=code: content_admin.set_event_active(c, True), f"Evento {code} riattivato.")

            with tab_dates:
                st.caption(
                    "Sposta insieme date, contenuti di ogni giorno e giorno dei trofei. "
                    "Un evento già concluso non si sposta."
                )
                new_start = st.date_input(
                    "Nuova data di inizio", value=None, format="DD/MM/YYYY", key=f"shift_{code}"
                )
                if st.button("📆 Sposta l'evento", key=f"do_shift_{code}", disabled=not new_start):
                    guarded(
                        lambda c=code, d=(to_iso(new_start) if new_start else ""): content_admin.shift_event(c, d),
                        lambda r: f"Evento {code} spostato: {to_display(r['dates'][0])} → {to_display(r['dates'][-1])}.",
                    )

            with tab_answers:
                day_options = {f"{d['day_display']} (g. {d['index']})": d for d in detail["days"]}
                if not day_options:
                    st.caption("L'evento non ha giorni.")
                else:
                    picked_label = st.selectbox("Giorno", list(day_options), key=f"day_pick_{code}")
                    picked = day_options[picked_label]
                    text = st.text_input(
                        "Risposte accettate (separate da virgola)",
                        value=", ".join(picked["answers"]),
                        key=f"ev_answers_{code}",
                    )
                    if st.button("💾 Salva risposte", key=f"save_ev_answers_{code}"):
                        parsed = content_admin.parse_answers_list(text)
                        guarded(
                            lambda c=code, d=picked["day"], a=parsed: content_admin.update_event_day_answers(c, d, a),
                            lambda r: f"Risposte del {picked['day_display']} aggiornate: {', '.join(r)}.",
                        )

            with tab_bonus:
                day_options = {f"{d['day_display']} (g. {d['index']})": d for d in detail["days"]}
                if not day_options:
                    st.caption("L'evento non ha giorni.")
                else:
                    picked_label = st.selectbox("Giorno", list(day_options), key=f"bonus_pick_{code}")
                    picked = day_options[picked_label]
                    st.write(f"Stato: **{'assegnato' if picked['first_correct_taken'] else 'libero'}**")
                    col_a, col_b = st.columns(2)
                    if col_a.button("🔓 Riapri", key=f"ev_reopen_{code}"):
                        guarded(
                            lambda c=code, d=picked["day"]: content_admin.set_event_day_first_correct(c, d, False),
                            f"Bonus del {picked['day_display']} riaperto.",
                        )
                    if col_b.button("🔒 Chiudi", key=f"ev_close_{code}"):
                        guarded(
                            lambda c=code, d=picked["day"]: content_admin.set_event_day_first_correct(c, d, True),
                            f"Bonus del {picked['day_display']} chiuso.",
                        )

            with tab_delete:
                if detail["status"] == content_admin.EVENT_STATUS_RUNNING:
                    st.info("L'evento è in corso: disattivalo invece di eliminarlo.")
                else:
                    st.caption("Elimina l'evento **e tutti i suoi partecipanti** (classifica compresa).")
                    if confirm_button("🗑️ Elimina l'evento", key=f"del_event_{code}"):
                        guarded(lambda c=code: content_admin.delete_event(c), f"Evento {code} eliminato.")

    st.divider()
    st.subheader("➕ Crea evento manuale")
    templates = load_templates()
    template_by_id = {t["id"]: t for t in templates}
    template_id = st.selectbox("Template", list(template_by_id))
    template = template_by_id[template_id]
    st.caption(
        f"**{template['name']}** — {template['description']}\n\n"
        f"tipo `{template['type']}` · durata {template.get('duration_days', 5)} giorni · "
        f"{template.get('points_per_day', 1)} punti/giorno · "
        f"regole: {template.get('rules') or 'nessuna'}"
        + (" · **solo manuale**" if template.get("manual_only") else "")
    )

    col1, col2 = st.columns(2)
    start_text = col1.text_input("Data inizio (gg/mm/aa, vuoto = oggi)")
    duration = col2.number_input("Durata (giorni, 0 = default template)", min_value=0, value=0)

    if st.button("✅ Crea evento", type="primary"):
        def _create():
            start_date = parse_start_date(start_text or None)
            return create_manual_event(template_id, start_date=start_date, duration_days=duration or None)

        guarded(
            _create,
            lambda s: (
                f"Evento creato: {s['name']} [{s['code']}] — {s['days']} giorni "
                f"({to_display(s['dates'][0])} → {to_display(s['dates'][-1])}), trofei il {to_display(s['trophy_day'])}."
            ),
        )


# ---------------------------------------------------------------------------
# Utenti
# ---------------------------------------------------------------------------
elif page == "👤 Utenti":
    st.header("👤 Utenti")

    try:
        overview = cached_overview()
        total = overview["users_total"] or 1
        col1, col2, col3 = st.columns(3)
        col1.metric("Registrati", overview["users_total"])
        col2.metric("Con notifiche attive", overview["users_with_notifications"])
        col3.metric(
            "Hanno indovinato oggi",
            f"{overview['users_guessed_today']} ({overview['users_guessed_today'] * 100 // total}%)",
        )
    except Exception as e:
        st.error(f"Errore: {e}")

    st.subheader("🏅 Classifiche")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Punti totali")
        try:
            show_table(
                [
                    {"pos.": i, "id": u["telegram_id"], "nome": u["username"], "punti": u["points"]}
                    for i, u in enumerate(cached_top_users("points_totali", 10), start=1)
                ]
            )
        except Exception as e:
            st.error(f"Errore: {e}")
    with col2:
        st.caption("Punti del mese")
        try:
            show_table(
                [
                    {"pos.": i, "id": u["telegram_id"], "nome": u["username"], "punti": u["monthly_points"]}
                    for i, u in enumerate(cached_top_users("monthly_points", 10), start=1)
                ]
            )
        except Exception as e:
            st.error(f"Errore: {e}")

    st.divider()
    st.subheader("🔎 Cerca e modifica un utente")
    col1, col2 = st.columns(2)
    user_id_text = col1.text_input("Telegram id", placeholder="es. 123456789")
    name_prefix = col2.text_input("…oppure cerca per nome (inizio del nome)")

    selected_id = user_id_text.strip() or None
    if name_prefix.strip():
        try:
            matches = firebase_service.find_users_by_first_name(name_prefix.strip(), limit=20)
        except Exception as e:
            matches = []
            st.error(f"Errore nella ricerca: {e}")
        if not matches:
            st.info("Nessun utente con quel nome.")
        else:
            labels = {
                f"{m.get('first_name', '?')} — {m.get('telegram_id')} ({m.get('points_totali', 0)} punti)": str(
                    m.get("telegram_id")
                )
                for m in matches
            }
            picked = st.selectbox("Risultati", list(labels))
            selected_id = labels[picked]

    if selected_id:
        try:
            user = firebase_service.get_user_data(selected_id)
        except Exception as e:
            user = None
            st.error(f"Errore: {e}")

        if not user:
            st.warning(f"Nessun utente con id `{selected_id}`.")
        else:
            st.markdown(f"### {user.get('first_name', '?')} — `{selected_id}`")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Punti totali", user.get("points_totali") or 0)
            m2.metric("Punti del mese", user.get("monthly_points") or 0)
            m3.metric("Striscia", f"{user.get('current_streak') or 0} (max {user.get('best_streak') or 0})")
            m4.metric("Sfide indovinate", user.get("players_guessed") or 0)

            st.caption(
                f"lingua `{user.get('language')}` · notifiche {fmt_bool(user.get('notifications_enabled'))} · "
                f"chat_id `{user.get('chat_id')}` · iscritto il {fmt_dt(user.get('date_created'))} · "
                f"ultimo giorno giocato {to_display(user.get('last_played_day')) or '—'} · "
                f"tentativi oggi {user.get('daily_attempts') or 0} · "
                f"ha indovinato oggi: {fmt_bool(user.get('has_guessed_today'))} · "
                f"bonus primo: {user.get('bonus_first_guessed') or 0} · "
                f"archivio risolto: {user.get('archive_solved') or 0}"
            )
            if user.get("trophies"):
                st.write("🏆 Trofei: " + ", ".join(f"`{t}`" for t in user["trophies"]))
            if user.get("leagues"):
                st.write("🏆 Leghe: " + ", ".join(f"`{c}`" for c in user["leagues"]))

            with st.expander("📜 Sfide d'archivio giocate"):
                try:
                    show_table(
                        [
                            {
                                "giorno": to_display(a.get("day")),
                                "tentativi": a.get("attempts", 0),
                                "risolta": fmt_bool(a.get("solved")),
                            }
                            for a in firebase_service.get_archive_days(selected_id)
                        ],
                        "Nessuna sfida d'archivio giocata.",
                    )
                except Exception as e:
                    st.error(f"Errore: {e}")

            st.markdown("---")
            st.markdown("**Modifica**")
            st.caption("I valori vengono scritti così come sono (non sommati).")
            with st.form(f"user_form_{selected_id}"):
                col1, col2, col3 = st.columns(3)
                new_points = col1.number_input("Punti totali", value=int(user.get("points_totali") or 0), step=1)
                new_monthly = col2.number_input("Punti del mese", value=int(user.get("monthly_points") or 0), step=1)
                new_streak = col3.number_input("Striscia attuale", value=int(user.get("current_streak") or 0), min_value=0, step=1)

                col4, col5, col6 = st.columns(3)
                new_best = col4.number_input("Striscia migliore", value=int(user.get("best_streak") or 0), min_value=0, step=1)
                languages = list(SUPPORTED_LANGUAGES)
                current_lang = user.get("language") if user.get("language") in languages else languages[0]
                new_language = col5.selectbox("Lingua", languages, index=languages.index(current_lang))
                new_notifications = col6.checkbox(
                    "Notifiche attive", value=bool(user.get("notifications_enabled"))
                )
                reset_today = st.checkbox(
                    "Azzera i tentativi di oggi (rimette in gioco l'utente sulla sfida odierna)"
                )

                if st.form_submit_button("💾 Salva", type="primary"):
                    fields = {
                        "points_totali": int(new_points),
                        "monthly_points": int(new_monthly),
                        "current_streak": int(new_streak),
                        "best_streak": int(new_best),
                        "language": new_language,
                        "notifications_enabled": bool(new_notifications),
                    }
                    if reset_today:
                        fields.update({"daily_attempts": 0, "has_guessed_today": False})
                    guarded(
                        lambda uid=selected_id, f=fields: firebase_service.update_user_fields(uid, f),
                        f"Utente {selected_id} aggiornato.",
                    )


# ---------------------------------------------------------------------------
# Leghe
# ---------------------------------------------------------------------------
elif page == "🏆 Leghe":
    st.header("🏆 Leghe private")
    limit = st.slider("Quante leghe mostrare", 1, 100, 20)
    try:
        leagues = cached_leagues(limit)
    except Exception as e:
        leagues = []
        st.error(f"Errore leggendo le leghe: {e}")

    show_table(
        [
            {
                "codice": lg["code"],
                "nome": lg.get("name", "—"),
                "membri": lg.get("members_count", 0),
                "proprietario": lg.get("owner_id"),
                "creata il": fmt_dt(lg.get("created_at")),
            }
            for lg in leagues
        ],
        "Nessuna lega creata.",
    )

    for lg in leagues:
        with st.expander(f"🏆 {lg.get('name', '—')} [{lg['code']}] — {lg.get('members_count', 0)} membri"):
            try:
                members = firebase_service.get_league_leaderboard(lg["code"], limit=50)
            except Exception as e:
                members = []
                st.error(f"Errore: {e}")
            show_table(
                [
                    {
                        "pos.": i,
                        "telegram_id": m.get("telegram_id"),
                        "nome": m.get("name", "—"),
                        "punti nella lega": m.get("points", 0),
                    }
                    for i, m in enumerate(members, start=1)
                ],
                "Nessun membro.",
            )


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
elif page == "📚 Dataset":
    st.header("📚 Dataset dei calciatori")
    try:
        blocked = cached_blocked_ids()
    except Exception as e:
        blocked = []
        st.error(f"Errore: {e}")

    try:
        report = cached_dataset_report(tuple(blocked))
    except Exception as e:
        report = None
        st.error(f"Errore costruendo il report: {e}")

    if report:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Totale", report["total"])
        col2.metric("Verificati", report["verified"])
        col3.metric("Selezionabili", report["selectable"])
        col4.metric("Autonomia", f"{report['autonomy_days']} giorni")

        st.subheader("Per difficoltà")
        st.bar_chart(report["by_difficulty"])

        st.subheader("Eventi tematici")
        show_table(
            [
                {
                    "template": t["id"],
                    "candidati": t["candidates"],
                    "durata (giorni)": t["duration_days"],
                    "stato": "manuale" if t["manual_only"] else ("ok" if t["ok"] else "POCHI CANDIDATI"),
                }
                for t in report["templates"]
            ]
        )

        if report["warnings"]:
            st.subheader("⚠️ Avvisi")
            for w in report["warnings"]:
                st.warning(w)

    st.divider()
    st.subheader("🔎 Sfoglia i giocatori selezionabili")
    col1, col2 = st.columns(2)
    search = col1.text_input("Cerca per nome o id")
    difficulty_filter = col2.multiselect("Difficoltà", DIFFICULTY_ORDER, default=DIFFICULTY_ORDER)

    rows = []
    for player in get_all_players():
        difficulty = compute_difficulty(player)
        if difficulty not in difficulty_filter:
            continue
        if search and search.lower() not in f"{player['id']} {player.get('full_name', '')}".lower():
            continue
        # La scomposizione dice a colpo d'occhio se una difficoltà che non torna dipende
        # dalla notorietà o dal percorso (vedi docs/difficolta.md, sezione 5).
        explained = explain_difficulty(player)
        rows.append({
            "id": player["id"],
            "nome": player.get("full_name"),
            "difficoltà": difficulty,
            "punteggio": round(explained["score"], 2),
            "da notorietà": round(explained["components"]["popularity"], 2),
            "dal percorso": round(explained["score"] - explained["components"]["popularity"], 2),
            "tappe": len(player.get("career", [])),
            "popolarità": player.get("popularity"),
            "nazionalità": player.get("nationality"),
            "sospeso": "sì" if player["id"] in blocked else "",
        })
    st.caption(f"{len(rows)} giocatori")
    show_table(sorted(rows, key=lambda r: r["punteggio"]))

    st.subheader("Giocatori esclusi dalla selezione automatica")
    incomplete = get_incomplete_or_unverified_players()
    if not incomplete:
        st.success("✅ Nessun giocatore da rivedere: dataset pulito.")
    else:
        show_table(
            [
                {"id": item["id"], "nome": item["full_name"], "problemi": "; ".join(item["problems"])}
                for item in incomplete
            ]
        )

    st.divider()
    st.subheader("⚙️ Configurazione in uso (data/config.json)")
    st.json(load_config(), expanded=False)


# ---------------------------------------------------------------------------
# Giocatori sospesi
# ---------------------------------------------------------------------------
elif page == "🚫 Giocatori sospesi":
    st.header("🚫 Giocatori sospesi")
    st.caption(
        "I giocatori sospesi restano fuori dalla selezione automatica finché non vengono riammessi. "
        "Le sfide già in buffer non cambiano: controllale nella sezione Sfide giornaliere."
    )

    try:
        blocked = cached_blocked_ids()
    except Exception as e:
        blocked = []
        st.error(f"Errore: {e}")

    if not blocked:
        st.success("✅ Nessun giocatore sospeso.")
    else:
        for player_id in blocked:
            player = get_player_by_id(player_id)
            col1, col2 = st.columns([4, 1])
            col1.write(f"`{player_id}` — {(player or {}).get('full_name', 'non più nel dataset')}")
            if col2.button("Riammetti", key=f"unblock_{player_id}"):
                guarded(
                    lambda pid=player_id: firebase_service.unblock_player_id(pid),
                    f"'{player_id}' riammesso nella selezione automatica.",
                )

    st.divider()
    st.subheader("Sospendi un giocatore")
    chosen = player_picker("pick_block", "Giocatore da sospendere")
    if st.button("🚫 Sospendi", disabled=not chosen):
        def _block():
            if not get_player_by_id(chosen):
                raise ContentAdminError(f"Nessun giocatore con id '{chosen}' nel dataset.")
            firebase_service.block_player_id(chosen)

        guarded(_block, f"'{chosen}' sospeso dalla selezione automatica.")


# ---------------------------------------------------------------------------
# Coppie padre/figlio
# ---------------------------------------------------------------------------
elif page == "👨‍👦 Coppie padre/figlio":
    st.header("👨‍👦 Coppie padre/figlio")
    try:
        pairs = firebase_service.list_father_son_pairs()
    except Exception as e:
        pairs = []
        st.error(f"Errore: {e}")

    st.subheader("Coppie salvate")
    if not pairs:
        st.info("📭 Nessuna coppia padre/figlio salvata.")
    else:
        st.caption(f"{len(pairs)} coppie · {sum(1 for p in pairs if not p.get('used_in_events'))} ancora da usare")
        for pair in pairs:
            used = ", ".join(pair.get("used_in_events", [])) or "mai usata"
            col1, col2 = st.columns([5, 1])
            col1.write(f"`{pair['id']}` — {', '.join(pair.get('answers', []))} ({used})")
            if col2.button("Elimina", key=f"del_pair_{pair['id']}"):
                guarded(
                    lambda pid=pair["id"]: firebase_service.delete_father_son_pair(pid),
                    f"Coppia {pair['id']} eliminata.",
                )

    st.divider()
    st.subheader("Aggiungi coppia")
    st.caption(
        "La foto viene inviata al bot (serve un ADMIN_TELEGRAM_IDS già avviato in chat con il bot) "
        "per ottenere il file_id da Telegram: nessuna copia dell'immagine viene salvata altrove."
    )
    photo = st.file_uploader("Foto della coppia", type=["jpg", "jpeg", "png"])
    answers_text = st.text_input("Risposte accettate (separate da virgola)", placeholder="Maldini, Paolo e Cesare Maldini")
    admin_chat_id = st.number_input(
        "Chat id admin a cui inviare la foto",
        value=ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else 0,
        step=1,
    )

    if st.button("➕ Salva coppia", type="primary"):
        answers = parse_answers(answers_text)
        if not photo:
            st.error("Serve una foto.")
        elif not answers:
            st.error("Servono le risposte accettate.")
        elif not admin_chat_id:
            st.error("Serve una chat id admin valida.")
        else:
            def _save():
                from telegram import Bot

                async def _send():
                    bot = Bot(token=BOT_TOKEN)
                    return await bot.send_photo(chat_id=int(admin_chat_id), photo=photo.getvalue())

                message = asyncio.run(_send())
                file_id = message.photo[-1].file_id
                return firebase_service.add_father_son_pair(
                    {"file_id": file_id, "answers": answers, "added_by": "admin_ui"}
                )

            guarded(_save, lambda pid: f"Coppia salvata (id {pid}). Risposte: {', '.join(answers)}")
