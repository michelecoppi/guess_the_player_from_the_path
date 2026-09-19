"""Refresh carriera/attivita' dei giocatori di produzione da fonte collegata (#81 follow-up).

Interfaccia sopra `domains.players.career_refresh` e `domains.players.production_dataset`:
nessuna scrittura diretta su `data/players.json` qui, tutto passa dalle stesse funzioni
sicure (lock di processo, backup, scrittura atomica) usate da `CandidateReviewService`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from admin_pages.shared import confirm_button, flash, show_table, st
from domains.players.career_refresh import refresh_all_active_players, refresh_player_career
from domains.players.production_dataset import load_production_players_strict
from services import observability

_BASE_DIR = Path(__file__).resolve().parent.parent
_PLAYERS_PATH = _BASE_DIR / "data" / "players.json"
_BACKUP_DIR = _BASE_DIR / "backup"


def _load_players() -> list[dict]:
    players, err = load_production_players_strict(_PLAYERS_PATH)
    if players is None:
        st.error(err or "Dataset di produzione non accessibile.")
        return []
    return players


def _render_single_player_section():
    st.subheader("Singolo player")
    players = _load_players()
    if not players:
        return

    query = st.text_input("Cerca per nome o id", key="career_refresh_search")
    q = query.strip().lower()
    matches = [
        p for p in players
        if not q or q in str(p.get("full_name", "")).lower() or q in str(p.get("id", "")).lower()
    ][:30]

    labels = [f"{p.get('full_name')} ({p.get('id')})" for p in matches]
    if not labels:
        st.caption("Nessun giocatore corrisponde alla ricerca.")
        return

    selected_label = st.selectbox("Giocatore", labels, key="career_refresh_selected")
    selected = matches[labels.index(selected_label)]
    player_id = selected["id"]

    st.write(
        f"**Attivo:** {selected.get('active', 'n/d')} · "
        f"**Fonte:** `{selected.get('source', '—')}` · "
        f"**ID fonte:** `{selected.get('source_id', '—')}` · "
        f"**Ultimo controllo:** {selected.get('career_last_checked_at', '—')}"
    )

    if not selected.get("source_id"):
        st.warning("Nessuna fonte collegata a questo giocatore.")
        if st.button("🔍 Cerca su Wikipedia", key=f"search_wiki_{player_id}"):
            from domains.players.adapters.wikipedia import WikipediaAdapter

            search_result = WikipediaAdapter().search_player(selected.get("full_name", ""))
            if not search_result.success or not search_result.identifiers:
                st.error("Nessun risultato trovato su Wikipedia.")
            else:
                st.session_state[f"wiki_candidates_{player_id}"] = search_result.identifiers

        candidates = st.session_state.get(f"wiki_candidates_{player_id}")
        if candidates:
            chosen = st.selectbox("Risultati Wikipedia", candidates, key=f"wiki_choice_{player_id}")
            if st.button("🔗 Collega questa fonte", key=f"link_wiki_{player_id}"):
                all_players = _load_players()
                idx = next((i for i, p in enumerate(all_players) if p.get("id") == player_id), None)
                if idx is None:
                    st.error("Giocatore non trovato (dataset cambiato nel frattempo).")
                else:
                    from domains.players.production_dataset import atomic_write_production_dataset

                    all_players[idx]["source"] = "wikipedia"
                    all_players[idx]["source_id"] = chosen
                    atomic_write_production_dataset(_PLAYERS_PATH, all_players)
                    flash("success", f"Fonte collegata: wikipedia/{chosen}. Ora puoi aggiornare la carriera.")
                    st.session_state.pop(f"wiki_candidates_{player_id}", None)
                    st.rerun()
        return

    if st.button("🔄 Aggiorna carriera", key=f"refresh_career_{player_id}"):
        try:
            result = refresh_player_career(player_id, players_path=_PLAYERS_PATH, backup_dir=_BACKUP_DIR)
        except Exception as e:  # noqa: BLE001 - mai un traceback grezzo in dashboard
            observability.log_event(
                "admin.career_refresh.failed", logging.ERROR, exc_info=e,
                component="admin", surface="streamlit", page="career_refresh", error_type=type(e).__name__,
            )
            st.error(f"Errore imprevisto: {type(e).__name__}")
            return

        if not result.success:
            st.error(result.message)
        elif result.changed:
            st.success(result.message)
            st.json(result.diff)
            st.cache_data.clear()
        else:
            st.info(result.message)


def _render_batch_section():
    st.divider()
    st.subheader("Batch: aggiorna tutti i giocatori attivi")
    st.caption(
        "Contatta la fonte collegata di ogni giocatore marcato `active` con un ritardo tra "
        "una richiesta e l'altra, aggiorna carriera/stato attività e scrive subito ogni "
        "modifica (backup + scrittura atomica, come per l'approvazione candidati)."
    )

    if confirm_button("🔄 Avvia refresh batch", key="career_refresh_batch", help_text="Contatta fonti esterne per ogni giocatore attivo con source_id."):
        with st.spinner("Aggiornamento in corso..."):
            try:
                results, without_source = refresh_all_active_players(
                    players_path=_PLAYERS_PATH, backup_dir=_BACKUP_DIR,
                )
            except Exception as e:  # noqa: BLE001
                observability.log_event(
                    "admin.career_refresh_batch.failed", logging.ERROR, exc_info=e,
                    component="admin", surface="streamlit", page="career_refresh", error_type=type(e).__name__,
                )
                st.error(f"Errore imprevisto: {type(e).__name__}")
                return

        st.success(f"Completato: {len(results)} giocatori contattati.")
        show_table(
            [
                {
                    "player_id": r.player_id,
                    "esito": "✅ ok" if r.success else "❌ errore",
                    "modificato": "sì" if r.changed else "no",
                    "messaggio": r.message,
                }
                for r in results
            ]
        )

        if without_source:
            st.warning(f"{len(without_source)} giocatori attivi senza fonte collegata:")
            show_table(
                [{"player_id": p.get("id"), "nome": p.get("full_name")} for p in without_source]
            )
        st.cache_data.clear()


def render(today, now_italy):
    st.header("🔄 Refresh carriera & attività")
    st.caption(
        "Ricontrolla la fonte collegata (Wikipedia/Wikidata) dei giocatori di produzione per "
        "rilevare trasferimenti, ritiri e statistiche aggiornate dopo il calciomercato. Le "
        "scritture passano sempre da `domains.players.career_refresh` con lock, backup e "
        "scrittura atomica, mai da modifiche dirette a `data/players.json`."
    )

    _render_single_player_section()
    _render_batch_section()
