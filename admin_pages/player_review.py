"""Coda di revisione dei candidati calciatori (#15 -> #35).

Interfaccia puramente umana sopra ``services.candidate_review.CandidateReviewService``:
nessuna regola di dominio (FSM, normalizzazione, validazione, conflitti di provenienza,
CAS sulla revisione, blocco/backup del dataset di produzione, retry) viene ricreata qui.
Ogni mutazione passa dal servizio, con la stessa ``expected_revision`` mostrata a schermo.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from admin_pages.shared import (
    CandidateState,
    ReviewStatus,
    ReviewAuthError,
    ReviewForbiddenError,
    flash,
    get_admin_identity,
    get_review_service,
    show_table,
    st,
)

PAGE_SIZE = 20

# Fonti di retry attualmente supportate dal resolver di default del servizio
# (`_default_adapter_resolver` in services/candidate_review.py). Qui è solo l'elenco dei
# nomi ammessi per popolare la scelta: nessun adapter viene mai importato o chiamato
# direttamente dalla Admin, la risoluzione resta interamente dentro il servizio.
SUPPORTED_RETRY_SOURCES = ["wikipedia", "wikidata"]

STATUS_RENDERERS = {
    ReviewStatus.NOT_FOUND: "error",
    ReviewStatus.UNAUTHORIZED: "error",
    ReviewStatus.FORBIDDEN: "error",
    ReviewStatus.INVALID_STATE: "warning",
    ReviewStatus.VALIDATION_FAILED: "error",
    ReviewStatus.UNRESOLVED_CONFLICT: "error",
    ReviewStatus.DUPLICATE_PLAYER: "error",
    ReviewStatus.INVALID_MERGE_TARGET: "error",
    ReviewStatus.PERSISTENCE_FAILURE: "error",
    ReviewStatus.FORBIDDEN_FIELD: "error",
    ReviewStatus.SOURCE_ERROR: "error",
}

STATE_LABELS = {
    CandidateState.REVIEW_REQUIRED.value: "🟠 Da revisionare",
    CandidateState.VALIDATED.value: "🔵 Validato",
    CandidateState.READY.value: "🟢 Pronto",
}


# ---------------------------------------------------------------------------
# Costruzione servizio, identità e cache di lettura
#
# Le letture stanno dietro st.cache_data (come nel resto della dashboard): ogni
# mutazione riuscita o STALE_REVISION svuota la cache e ricarica, così non si può
# mai inviare una expected_revision più vecchia di quella appena mostrata.
# ---------------------------------------------------------------------------

@st.cache_data(ttl=20, show_spinner=False)
def cached_queue(admin_user_id, state, has_warnings, source, search, sort_by, limit, offset):
    service = get_review_service()
    admin = get_admin_identity()
    return service.list_queue(
        admin,
        state=state,
        has_warnings=has_warnings,
        source=source or None,
        search=search or None,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@st.cache_data(ttl=20, show_spinner=False)
def cached_state_total(admin_user_id, state):
    """Conteggio esatto per stato, calcolato dal servizio (campo `total` prima della slice)."""
    service = get_review_service()
    admin = get_admin_identity()
    return service.list_queue(admin, state=state, limit=1, offset=0).total


@st.cache_data(ttl=20, show_spinner=False)
def cached_warning_total(admin_user_id):
    service = get_review_service()
    admin = get_admin_identity()
    return service.list_queue(admin, has_warnings=True, limit=1, offset=0).total


@st.cache_data(ttl=20, show_spinner=False)
def cached_conflict_total(admin_user_id, max_scan=500):
    """Candidati con conflitti di fonte bloccanti irrisolti.

    Il servizio non espone un filtro dedicato ai conflitti, quindi qui si sommano le
    proiezioni già costruite dal servizio (has_source_conflicts) pagina per pagina —
    non si ricalcola nulla, si usa solo il campo che il servizio ha già deciso.
    """
    service = get_review_service()
    admin = get_admin_identity()
    total_conflicts = 0
    offset = 0
    scanned = 0
    while scanned < max_scan:
        page = service.list_queue(admin, limit=100, offset=offset)
        if not page.items:
            break
        total_conflicts += sum(1 for item in page.items if item.has_source_conflicts)
        scanned += len(page.items)
        offset += len(page.items)
        if offset >= page.total:
            break
    return total_conflicts, scanned


@st.cache_data(ttl=20, show_spinner=False)
def cached_detail(admin_user_id, candidate_id):
    service = get_review_service()
    admin = get_admin_identity()
    return service.get_candidate_detail(admin, candidate_id)


def _reload_and_rerun():
    st.cache_data.clear()
    st.rerun()


def _run_action(action_fn, *, success_message: Optional[str] = None):
    """Esegue una mutazione del servizio mappando l'esito tipizzato su messaggi in chiaro.

    Non propaga mai un traceback grezzo al reviewer. STALE_REVISION non viene mai
    ritentato automaticamente: ricarica soltanto la proiezione più recente e richiede
    una nuova decisione esplicita.
    """
    try:
        result = action_fn()
    except (ReviewAuthError, ReviewForbiddenError) as e:
        st.error(f"Accesso negato: {e}")
        return None
    except Exception as e:  # noqa: BLE001 - mai un traceback grezzo nella UI
        st.error(f"Errore imprevisto: {type(e).__name__}")
        return None

    if result.status == ReviewStatus.STALE_REVISION:
        flash("warning", f"{result.message} Proiezione ricaricata: rivedi e riprova.")
        _reload_and_rerun()
        return result

    if result.success:
        msg = success_message or result.message
        flash("success" if result.status == ReviewStatus.SUCCESS else "info", msg)
        _reload_and_rerun()
        return result

    kind = STATUS_RENDERERS.get(result.status, "error")
    getattr(st, kind)(result.message)
    if result.errors:
        st.error("Errori bloccanti: " + "; ".join(result.errors))
    if result.warnings:
        st.warning("Warning: " + "; ".join(result.warnings))
    if result.conflicts:
        st.error("Conflitti tra fonti: " + "; ".join(result.conflicts))
    return result


# ---------------------------------------------------------------------------
# Panoramica coda
# ---------------------------------------------------------------------------

def _render_overview(admin_user_id):
    st.subheader("Panoramica coda")
    total = cached_state_total(admin_user_id, None)
    review_required = cached_state_total(admin_user_id, CandidateState.REVIEW_REQUIRED.value)
    validated = cached_state_total(admin_user_id, CandidateState.VALIDATED.value)
    ready = cached_state_total(admin_user_id, CandidateState.READY.value)
    warnings_total = cached_warning_total(admin_user_id)
    conflicts_total, scanned = cached_conflict_total(admin_user_id)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Totale revisionabili", total)
    col2.metric("Da revisionare", review_required)
    col3.metric("Validati", validated)
    col4.metric("Pronti", ready)
    col5.metric("Con warning/errori", warnings_total)
    col6.metric("Conflitti fonti", conflicts_total)
    if scanned < total:
        st.caption(f"⚠️ Conteggio conflitti calcolato sui primi {scanned} candidati su {total}.")


# ---------------------------------------------------------------------------
# Filtri, tabella e paginazione (lato servizio: nessun filtraggio client-side)
# ---------------------------------------------------------------------------

def _render_filters():
    col1, col2, col3, col4 = st.columns([2, 2, 3, 2])
    state_choice = col1.selectbox(
        "Stato",
        ["Tutti", CandidateState.REVIEW_REQUIRED.value, CandidateState.VALIDATED.value, CandidateState.READY.value],
        key="review_state_filter",
    )
    warnings_choice = col2.selectbox(
        "Warning/errori",
        ["Tutti", "Solo con warning/errori", "Solo puliti"],
        key="review_warnings_filter",
    )
    search = col3.text_input("Cerca (nome, alias, squadra, id)", key="review_search_filter")
    sort_by = col4.selectbox(
        "Ordina per",
        ["newest", "oldest", "urgency"],
        format_func=lambda v: {"newest": "Più recenti", "oldest": "Più vecchi", "urgency": "Urgenza"}[v],
        key="review_sort_filter",
    )
    source = st.text_input("Fonte (es. wikipedia, wikidata)", key="review_source_filter")

    state = None if state_choice == "Tutti" else state_choice
    has_warnings = {"Tutti": None, "Solo con warning/errori": True, "Solo puliti": False}[warnings_choice]

    filters = (state, has_warnings, source.strip() or None, search.strip() or None, sort_by)
    if st.session_state.get("review_last_filters") != filters:
        st.session_state["review_last_filters"] = filters
        st.session_state["review_page"] = 1

    return state, has_warnings, source, search, sort_by


def _render_queue_table(admin_user_id, state, has_warnings, source, search, sort_by):
    page_num = st.session_state.get("review_page", 1)
    offset = (page_num - 1) * PAGE_SIZE

    result = cached_queue(admin_user_id, state, has_warnings, source, search, sort_by, PAGE_SIZE, offset)

    st.caption(f"{result.total} candidati corrispondenti · pagina {page_num}")

    if not result.items:
        st.info("📭 Nessun candidato con questi filtri.")
        return

    rows = []
    for item in result.items:
        rows.append(
            {
                "id": item.candidate_id,
                "nome": item.full_name or "—",
                "stato": STATE_LABELS.get(item.status, item.status),
                "fonte": f"{item.source}:{item.source_id}",
                "anno": item.birth_year or "—",
                "nazionalità": item.nationality or "—",
                "errori": len(item.validation_errors),
                "warning": len(item.validation_warnings),
                "conflitti fonti": "🔴" if item.has_source_conflicts else "—",
                "duplicati": f"⚠️ {len(item.possible_duplicates)}" if item.possible_duplicates else "—",
                "aggiornato": item.updated_at,
                "rev": item.revision,
            }
        )
    show_table(rows)

    st.caption("Apri il dettaglio di un candidato:")
    for item in result.items:
        cols = st.columns([5, 1])
        cols[0].write(f"**{item.full_name or item.candidate_id}** — `{item.candidate_id}` ({STATE_LABELS.get(item.status, item.status)})")
        if cols[1].button("Apri", key=f"open_{item.candidate_id}"):
            st.session_state["review_selected_id"] = item.candidate_id
            st.rerun()

    total_pages = max(1, (result.total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav_cols = st.columns([1, 1, 4])
    if nav_cols[0].button("◀ Precedente", disabled=page_num <= 1, key="review_prev_page"):
        st.session_state["review_page"] = max(1, page_num - 1)
        st.rerun()
    if nav_cols[1].button("Successiva ▶", disabled=page_num >= total_pages, key="review_next_page"):
        st.session_state["review_page"] = min(total_pages, page_num + 1)
        st.rerun()


# ---------------------------------------------------------------------------
# Dettaglio candidato
# ---------------------------------------------------------------------------

def _career_rows(career: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "squadra": stop.get("team", ""),
            "paese": stop.get("country", ""),
            "campionato": stop.get("league", ""),
            "dal": stop.get("start_year"),
            "al": stop.get("end_year"),
            "prestito": bool(stop.get("loan", False)),
            "presenze": stop.get("apps"),
            "gol": stop.get("goals"),
        }
        for stop in career
    ]


def _rows_to_career(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    career = []
    for row in rows:
        team = (row.get("squadra") or "").strip()
        if not team:
            continue
        stop: dict[str, Any] = {"team": team}
        if row.get("paese"):
            stop["country"] = row["paese"]
        if row.get("campionato"):
            stop["league"] = row["campionato"]
        if row.get("dal") not in (None, ""):
            stop["start_year"] = int(row["dal"])
        if row.get("al") not in (None, ""):
            stop["end_year"] = int(row["al"])
        if row.get("prestito"):
            stop["loan"] = True
        if row.get("presenze") not in (None, ""):
            stop["apps"] = int(row["presenze"])
        if row.get("gol") not in (None, ""):
            stop["goals"] = int(row["gol"])
        career.append(stop)
    return career


def _render_identity_and_career(projection):
    st.markdown("#### Identità")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nome", projection.full_name or "—")
    col2.metric("Anno di nascita", projection.birth_year or "—")
    col3.metric("Nazionalità", projection.nationality or "—")
    col4.metric("Ruolo", projection.position or "—")
    st.caption(
        f"Alias: {', '.join(projection.aliases) or '—'} · "
        f"Notorietà: {projection.popularity} · "
        f"One-club: {'sì' if projection.is_one_club_man else 'no'} · "
        f"Ritirato: {'sì' if projection.is_retired else 'no'}"
    )

    st.markdown("#### Carriera")
    show_table(_career_rows(projection.career), "Nessuna tappa di carriera.")


def _render_validation(projection):
    st.markdown("#### Validazione")
    if not projection.validation_errors and not projection.validation_warnings:
        st.success("✅ Nessun errore né warning.")
    if projection.validation_errors:
        st.error("Errori bloccanti (impediscono l'approvazione):")
        for err in projection.validation_errors:
            st.write(f"🔴 {err}")
    if projection.validation_warnings:
        st.warning("Warning (approvabili solo con conferma esplicita):")
        for warn in projection.validation_warnings:
            st.write(f"🟡 {warn}")
    if projection.has_source_conflicts:
        st.error(
            "🔴 Conflitto di provenienza non risolto tra fonti ancora attendibili: "
            "blocca l'approvazione finché non si segnala la fonte errata o si corregge il campo."
        )
    if projection.findings:
        with st.expander("Findings dettagliati"):
            show_table(projection.findings)


def _render_provenance(projection):
    st.markdown("#### Fonte attiva")
    st.write(f"`{projection.source}` — id `{projection.source_id}`")

    rejected = [
        ev for ev in projection.review_history
        if ev.get("action") == "SOURCE_WRONG"
    ]
    if rejected:
        st.markdown("#### Fonti segnalate come errate")
        st.caption(
            "L'evidenza resta visibile qui sotto per ogni campo, ma non è più considerata "
            "autorevole nel calcolo dei conflitti bloccanti."
        )
        show_table(
            [
                {
                    "fonte": ev.get("source"),
                    "id fonte": ev.get("source_id", "—"),
                    "motivo": ev.get("reason", "—"),
                    "quando": ev.get("timestamp", "—"),
                }
                for ev in rejected
            ]
        )

    st.markdown("#### Osservazioni per campo")
    if not projection.field_observations:
        st.caption("Nessuna osservazione di provenienza registrata.")
        return
    for path, obs_list in projection.field_observations.items():
        with st.expander(f"`{path}` ({len(obs_list)} osservazioni)"):
            show_table(
                [
                    {
                        "fonte": obs.get("source"),
                        "id fonte": obs.get("source_id"),
                        "valore": obs.get("raw_value"),
                        "confidenza": obs.get("confidence"),
                        "livello": obs.get("confidence_level"),
                        "rilevato": obs.get("retrieved_at"),
                    }
                    for obs in obs_list
                ]
            )


def _render_duplicates(projection):
    st.markdown("#### Possibili duplicati in produzione")
    if not projection.possible_duplicates:
        st.caption("Nessun duplicato sospetto individuato dal servizio.")
        return
    show_table(
        [
            {
                "player_id": d.player_id,
                "nome": d.player_name,
                "confidenza": d.confidence,
                "motivi": "; ".join(d.match_reasons),
            }
            for d in projection.possible_duplicates
        ]
    )
    st.caption("Il merge con uno di questi giocatori è sempre una scelta esplicita del reviewer, mai automatica.")


def _render_history(projection):
    st.markdown("#### Storico audit")
    if not projection.review_history:
        st.caption("Nessun evento registrato per questo candidato.")
        return
    show_table(
        [
            {
                "azione": ev.get("action"),
                "chi": ev.get("actor"),
                "quando": ev.get("timestamp"),
                "motivo": ev.get("reason", "—"),
                "dettagli": ", ".join(
                    f"{k}={v}" for k, v in ev.items()
                    if k not in ("action", "actor", "timestamp", "reason")
                ),
            }
            for ev in reversed(projection.review_history)
        ]
    )


def _render_edit(admin, candidate_id, projection):
    st.markdown("#### Modifica campi (solo elenco consentito dal servizio)")
    rev = projection.revision
    with st.form(key=f"form_edit_{candidate_id}_{rev}"):
        full_name = st.text_input(
            "Nome completo", value=projection.full_name or "", key=f"edit_full_name_{candidate_id}_{rev}"
        )
        col1, col2, col3 = st.columns(3)
        birth_year = col1.number_input(
            "Anno di nascita",
            value=projection.birth_year or 1990,
            min_value=1900,
            max_value=2100,
            step=1,
            key=f"edit_birth_year_{candidate_id}_{rev}",
        )
        nationality = col2.text_input(
            "Nazionalità", value=projection.nationality or "", key=f"edit_nationality_{candidate_id}_{rev}"
        )
        position = col3.text_input(
            "Ruolo", value=projection.position or "", key=f"edit_position_{candidate_id}_{rev}"
        )
        aliases_text = st.text_input(
            "Alias (separati da virgola)",
            value=", ".join(projection.aliases),
            key=f"edit_aliases_{candidate_id}_{rev}",
        )
        col4, col5, col6 = st.columns(3)
        is_one_club_man = col4.checkbox(
            "One-club man", value=projection.is_one_club_man, key=f"edit_one_club_{candidate_id}_{rev}"
        )
        is_retired = col5.checkbox(
            "Ritirato", value=projection.is_retired, key=f"edit_retired_{candidate_id}_{rev}"
        )
        popularity = col6.select_slider(
            "Notorietà",
            options=[1, 2, 3, 4, 5],
            value=projection.popularity,
            key=f"edit_popularity_{candidate_id}_{rev}",
        )

        st.caption("Tabella carriera (aggiungi/rimuovi righe direttamente):")
        career_rows = st.data_editor(
            _career_rows(projection.career),
            num_rows="dynamic",
            key=f"career_editor_{candidate_id}_{rev}",
            width="stretch",
        )
        with st.expander("Carriera avanzata (JSON, opzionale — sovrascrive la tabella sopra se compilata)"):
            career_json_text = st.text_area(
                "JSON carriera",
                value="",
                placeholder=json.dumps(projection.career, ensure_ascii=False, indent=2),
                key=f"career_json_{candidate_id}_{rev}",
            )

        reason = st.text_input("Motivo della modifica (opzionale)", key=f"edit_reason_{candidate_id}_{rev}")

        st.divider()
        combined_approve = st.checkbox(
            "Salva e approva subito (azione combinata)", key=f"edit_combined_{candidate_id}_{rev}"
        )
        combined_ack_warnings = st.checkbox(
            "Ho rivisto i warning risultanti e voglio approvare comunque",
            key=f"edit_combined_ack_{candidate_id}_{rev}",
            disabled=not combined_approve,
        )
        submitted = st.form_submit_button("💾 Salva modifiche")

    if not submitted:
        return

    updates: dict[str, Any] = {}
    if full_name != (projection.full_name or ""):
        updates["full_name"] = full_name
    if int(birth_year) != (projection.birth_year or 0):
        updates["birth_year"] = int(birth_year)
    if nationality != (projection.nationality or ""):
        updates["nationality"] = nationality
    if position != (projection.position or ""):
        updates["position"] = position
    new_aliases = [a.strip() for a in aliases_text.split(",") if a.strip()]
    if new_aliases != list(projection.aliases):
        updates["aliases"] = new_aliases
    if is_one_club_man != projection.is_one_club_man:
        updates["is_one_club_man"] = is_one_club_man
    if is_retired != projection.is_retired:
        updates["is_retired"] = is_retired
    if popularity != projection.popularity:
        updates["popularity"] = popularity

    if career_json_text.strip():
        try:
            new_career = json.loads(career_json_text)
            if not isinstance(new_career, list):
                raise ValueError("Il JSON carriera deve essere una lista di tappe.")
        except (json.JSONDecodeError, ValueError) as e:
            st.error(f"JSON carriera non valido: {e}")
            return
    else:
        new_career = _rows_to_career(career_rows if isinstance(career_rows, list) else career_rows.to_dict("records"))
    if new_career != projection.career:
        updates["career"] = new_career

    if not updates:
        st.info("Nessuna modifica da salvare.")
        return

    service = get_review_service()
    if combined_approve:
        _run_action(
            lambda: service.edit_and_approve(
                admin,
                candidate_id,
                expected_revision=rev,
                updates=updates,
                allow_warnings=combined_ack_warnings,
                reason=reason or None,
            ),
            success_message="Modifiche salvate e candidato approvato.",
        )
    else:
        _run_action(
            lambda: service.edit(admin, candidate_id, expected_revision=rev, updates=updates, reason=reason or None),
            success_message="Modifiche salvate.",
        )


def _render_approve(admin, candidate_id, projection):
    st.markdown("#### Approva e promuovi in produzione")
    rev = projection.revision
    blocking = bool(projection.validation_errors) or projection.has_source_conflicts
    if blocking:
        st.error("Non approvabile: risolvi prima gli errori bloccanti e/o i conflitti di provenienza.")

    with st.form(key=f"form_approve_{candidate_id}_{rev}"):
        st.write(f"Stato: **{STATE_LABELS.get(projection.status, projection.status)}** · revisione **{rev}**")
        if projection.validation_warnings:
            st.warning(f"{len(projection.validation_warnings)} warning presenti (vedi tab Validazione).")
        if projection.possible_duplicates:
            st.warning(f"{len(projection.possible_duplicates)} possibili duplicati in produzione (vedi tab Duplicati).")

        confirmed = st.checkbox(
            "Confermo di aver rivisto la scheda e voglio approvarla",
            disabled=blocking,
            key=f"approve_confirm_{candidate_id}_{rev}",
        )
        ack_warnings = False
        if projection.validation_warnings:
            ack_warnings = st.checkbox(
                "Ho rivisto i warning e voglio approvare comunque",
                disabled=blocking,
                key=f"approve_ack_warnings_{candidate_id}_{rev}",
            )
        submitted = st.form_submit_button(
            "✅ Approva", disabled=blocking, key=f"approve_submit_{candidate_id}_{rev}"
        )

    if not submitted:
        return
    if not confirmed:
        st.error("Conferma richiesta prima di approvare.")
        return
    if projection.validation_warnings and not ack_warnings:
        st.error("Devi confermare di aver rivisto i warning prima di approvare.")
        return

    service = get_review_service()
    _run_action(
        lambda: service.approve_candidate(
            admin, candidate_id, expected_revision=rev, allow_warnings=ack_warnings
        ),
    )


def _render_reject(admin, candidate_id, projection):
    st.markdown("#### Rifiuta candidato")
    rev = projection.revision
    with st.form(key=f"form_reject_{candidate_id}_{rev}"):
        reason = st.text_input("Motivo del rifiuto (obbligatorio)", key=f"reject_reason_{candidate_id}_{rev}")
        confirmed = st.checkbox(
            "Confermo il rifiuto (non elimina il candidato, resta nello storico)",
            key=f"reject_confirm_{candidate_id}_{rev}",
        )
        submitted = st.form_submit_button("❌ Rifiuta", key=f"reject_submit_{candidate_id}_{rev}")

    if not submitted:
        return
    if not reason.strip():
        st.error("Il motivo del rifiuto è obbligatorio.")
        return
    if not confirmed:
        st.error("Conferma richiesta prima di rifiutare.")
        return

    service = get_review_service()
    _run_action(lambda: service.reject_candidate(admin, candidate_id, expected_revision=rev, reason=reason.strip()))


def _render_merge(admin, candidate_id, projection):
    st.markdown("#### Merge con un giocatore esistente")
    rev = projection.revision

    options: dict[str, str] = {}
    for d in projection.possible_duplicates:
        options[f"⭐ {d.player_name} — {d.player_id} (confidenza {d.confidence})"] = d.player_id

    # Usa lo stesso dataset di produzione configurato sul servizio (non un lettore diverso):
    # deve coincidere esattamente con l'elenco su cui merge_candidate() valida il target.
    service_for_options = get_review_service()
    for p in sorted(service_for_options._load_production_players(), key=lambda p: p.get("full_name", "")):
        label = f"{p.get('full_name', p.get('id'))} — {p['id']}"
        options.setdefault(label, p["id"])

    with st.form(key=f"form_merge_{candidate_id}_{rev}"):
        choice = st.selectbox(
            "Giocatore target in produzione",
            ["—"] + list(options),
            index=0,
            key=f"merge_target_{candidate_id}_{rev}",
        )
        reason = st.text_input("Motivo del merge (obbligatorio)", key=f"merge_reason_{candidate_id}_{rev}")
        confirmed = st.checkbox(
            "Confermo il merge: nessun nuovo giocatore verrà creato", key=f"merge_confirm_{candidate_id}_{rev}"
        )
        submitted = st.form_submit_button("🔀 Esegui merge", key=f"merge_submit_{candidate_id}_{rev}")

    if not submitted:
        return
    if choice == "—":
        st.error("Seleziona un giocatore target.")
        return
    if not reason.strip():
        st.error("Il motivo del merge è obbligatorio.")
        return
    if not confirmed:
        st.error("Conferma richiesta prima del merge.")
        return

    target_id = options[choice]
    service = get_review_service()
    _run_action(
        lambda: service.merge_candidate(
            admin, candidate_id, expected_revision=rev, target_player_id=target_id, reason=reason.strip()
        )
    )


def _render_source_wrong(admin, candidate_id, projection):
    st.markdown("#### Segnala fonte errata")
    rev = projection.revision

    known_pairs = sorted(
        {
            (obs.get("source"), obs.get("source_id"))
            for obs_list in projection.field_observations.values()
            for obs in obs_list
            if obs.get("source")
        }
    )
    default_pair = (projection.source, projection.source_id)
    pair_labels = [f"{s}: {sid}" for s, sid in known_pairs] or [f"{default_pair[0]}: {default_pair[1]}"]
    if not known_pairs:
        known_pairs = [default_pair]

    with st.form(key=f"form_source_wrong_{candidate_id}_{rev}"):
        idx = known_pairs.index(default_pair) if default_pair in known_pairs else 0
        choice = st.selectbox(
            "Fonte da segnalare come errata", pair_labels, index=idx, key=f"sw_choice_{candidate_id}_{rev}"
        )
        reason = st.text_input("Motivo (obbligatorio)", key=f"sw_reason_{candidate_id}_{rev}")
        confirmed = st.checkbox(
            "Confermo: l'evidenza resta nello storico ma non sarà più considerata autorevole",
            key=f"sw_confirm_{candidate_id}_{rev}",
        )
        submitted = st.form_submit_button("⚠️ Segnala fonte errata", key=f"sw_submit_{candidate_id}_{rev}")

    if not submitted:
        return
    if not reason.strip():
        st.error("Il motivo è obbligatorio.")
        return
    if not confirmed:
        st.error("Conferma richiesta.")
        return

    source, source_id = known_pairs[pair_labels.index(choice)]
    service = get_review_service()
    _run_action(
        lambda: service.mark_source_wrong(
            admin, candidate_id, expected_revision=rev, source=source, reason=reason.strip(), source_id=source_id
        )
    )


def _render_retry(admin, candidate_id, projection):
    st.markdown("#### Ritenta ingestione")
    rev = projection.revision

    current_rejected = any(
        ev.get("action") == "SOURCE_WRONG"
        and ev.get("source") == projection.source
        and (ev.get("source_id") in (None, projection.source_id))
        for ev in projection.review_history
    )
    if current_rejected:
        st.warning(
            f"La fonte corrente '{projection.source}' è stata segnalata come errata: "
            "seleziona una fonte alternativa e il relativo ID."
        )
    else:
        st.caption(f"Fonte corrente attendibile: `{projection.source}` (id `{projection.source_id}`).")

    with st.form(key=f"form_retry_{candidate_id}_{rev}"):
        use_current = st.checkbox(
            "Usa la fonte corrente",
            value=not current_rejected,
            disabled=current_rejected,
            key=f"retry_use_current_{candidate_id}_{rev}",
        )
        alt_source = st.selectbox(
            "Fonte alternativa", SUPPORTED_RETRY_SOURCES, index=0, key=f"retry_alt_source_{candidate_id}_{rev}"
        )
        alt_source_id = st.text_input(
            "ID nella fonte alternativa (es. titolo pagina Wikipedia, QID Wikidata)",
            key=f"retry_alt_source_id_{candidate_id}_{rev}",
        )
        submitted = st.form_submit_button("🔄 Ritenta ingestione", key=f"retry_submit_{candidate_id}_{rev}")

    if not submitted:
        return

    if use_current and not current_rejected:
        retry_source, retry_source_id = None, None
    else:
        if not alt_source_id.strip():
            st.error("Serve l'ID dell'entità nella fonte alternativa.")
            return
        retry_source, retry_source_id = alt_source, alt_source_id.strip()

    service = get_review_service()
    _run_action(
        lambda: service.retry_ingestion(
            admin, candidate_id, expected_revision=rev, retry_source=retry_source, retry_source_id=retry_source_id
        )
    )


def _render_detail(admin, admin_user_id, candidate_id):
    if st.button("← Torna alla coda"):
        st.session_state["review_selected_id"] = None
        st.rerun()

    projection = cached_detail(admin_user_id, candidate_id)
    if projection is None:
        st.error(f"Candidato '{candidate_id}' non trovato (potrebbe essere stato appena approvato o rifiutato).")
        return

    st.subheader(f"{projection.full_name or projection.candidate_id}")
    st.caption(
        f"`{projection.candidate_id}` · stato {STATE_LABELS.get(projection.status, projection.status)} · "
        f"revisione {projection.revision} · aggiornato {projection.updated_at}"
    )
    if projection.status not in (
        CandidateState.REVIEW_REQUIRED.value,
        CandidateState.VALIDATED.value,
        CandidateState.READY.value,
    ):
        st.warning("Questo candidato non è più in uno stato revisionabile: le azioni sono disabilitate.")

    tabs = st.tabs(
        ["📋 Panoramica", "🔗 Fonti", "👥 Duplicati", "🕘 Storico", "✏️ Modifica", "✅ Approva", "❌ Rifiuta", "🔀 Merge", "⚠️ Fonte errata", "🔄 Retry"]
    )
    with tabs[0]:
        _render_identity_and_career(projection)
        _render_validation(projection)
    with tabs[1]:
        _render_provenance(projection)
    with tabs[2]:
        _render_duplicates(projection)
    with tabs[3]:
        _render_history(projection)
    with tabs[4]:
        _render_edit(admin, candidate_id, projection)
    with tabs[5]:
        _render_approve(admin, candidate_id, projection)
    with tabs[6]:
        _render_reject(admin, candidate_id, projection)
    with tabs[7]:
        _render_merge(admin, candidate_id, projection)
    with tabs[8]:
        _render_source_wrong(admin, candidate_id, projection)
    with tabs[9]:
        _render_retry(admin, candidate_id, projection)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render(today, now_italy):
    st.header("🔎 Review giocatori")
    st.caption(
        "Coda umana di revisione dei candidati acquisiti dalla pipeline (#15): approvazione, "
        "modifica, rifiuto, merge, segnalazione fonte errata e retry passano tutti da "
        "`CandidateReviewService`, mai da scritture dirette su `data/players.json`."
    )

    admin = get_admin_identity()
    if admin is None:
        st.error(
            "ADMIN_TELEGRAM_IDS non configurato: nessuna identità amministrativa disponibile. "
            "Imposta ADMIN_TELEGRAM_IDS nel `.env` per abilitare le mutazioni sulla coda di revisione."
        )
        return

    st.caption(f"Operi come amministratore `{admin.user_id}`. ⚠️ Approvazioni e merge scrivono su `data/players.json` di produzione.")

    _render_overview(admin.user_id)
    st.divider()

    selected_id = st.session_state.get("review_selected_id")
    if selected_id:
        _render_detail(admin, admin.user_id, selected_id)
        return

    state, has_warnings, source, search, sort_by = _render_filters()
    _render_queue_table(admin.user_id, state, has_warnings, source, search, sort_by)
