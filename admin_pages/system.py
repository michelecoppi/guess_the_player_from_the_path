"""system health, jobs and backup administration page."""
from datetime import datetime, timezone

from admin_pages.shared import (
    backup_status,
    cached_failed_jobs,
    fmt_dt,
    observability,
    show_table,
    st,
)


def _render_observability():
    st.subheader("🩺 Osservabilità")
    settings = observability.settings()
    col1, col2, col3 = st.columns(3)
    col1.metric("Sentry", "attivo" if observability.sentry_enabled() else "spento")
    col2.metric("Ambiente", settings.environment or "—")
    col3.metric("Release", settings.release or "—")
    if observability.sentry_enabled():
        st.caption(
            "Errori ed eccezioni non gestite finiscono su Sentry con questo ambiente: apri "
            "la dashboard Sentry del progetto per il dettaglio (stack trace, frequenza, utenti coinvolti)."
        )
    else:
        st.warning(
            "Sentry non è configurato (manca `SENTRY_DSN`): le eccezioni finiscono solo nei log "
            "strutturati del processo (Cloud Logging in produzione), senza aggregazione né alert."
        )


def _render_failed_jobs():
    st.subheader("⚙️ Job bloccati")
    st.caption(
        "Un job (sfida giornaliera, pagina di broadcast, chiusura mensile) resta qui quando la "
        "sua lease (`services/work_receipts.py`) scade senza che sia mai arrivata la conferma di "
        "fine lavoro: il segnale di un'esecuzione interrotta a metà, non di un errore applicativo "
        "già gestito."
    )
    limit = st.slider("Quanti mostrarne", 1, 200, 50, key="failed_jobs_limit")
    try:
        jobs = cached_failed_jobs(limit)
    except Exception as e:
        jobs = []
        st.error(f"Errore leggendo i job: {e}")

    if not jobs:
        st.success("✅ Nessun job bloccato al momento.")
        return

    show_table(
        [
            {
                "chiave": job["key"],
                "gruppo seriale": job["serial_key"] or "—",
                "lease scaduta il": fmt_dt(job["expired_at"]),
            }
            for job in jobs
        ]
    )


def _render_backups():
    st.subheader("💾 Backup")
    st.caption(
        "Il backup settimanale (lunedì 03:30 UTC) gira su GitHub Actions e carica il file come "
        "artifact: questo processo non ci arriva, quindi qui sotto ci sono solo le copie prodotte "
        "**su questa macchina** con `scripts/backup_firestore.py` (utile prima di un'operazione "
        "manuale rischiosa). Storico completo ed esito di ogni run settimanale: "
        f"[workflow di backup]({backup_status.BACKUP_WORKFLOW_URL}). Prova di ripristino "
        f"automatica ogni settimana su dati sintetici: [restore-verification]"
        f"({backup_status.RESTORE_VERIFICATION_WORKFLOW_URL}). Procedura completa: "
        "`docs/backup-recovery.md`."
    )
    try:
        backups = backup_status.list_local_backups()
    except Exception as e:
        backups = []
        st.error(f"Errore leggendo backup/: {e}")

    if not backups:
        st.info("📭 Nessun backup locale in `backup/`.")
        return

    show_table(
        [
            {
                "file": b["file"],
                "modificato il": fmt_dt(datetime.fromtimestamp(b["modified_at"], tz=timezone.utc)),
                "valido": "sì" if b.get("valid") else "no",
                "completo": "sì" if b.get("complete") else "no",
                "documenti": b.get("total_documents", "—"),
                "qualità": b.get("quality", "—" if b.get("valid") else "n/d"),
            }
            for b in backups
        ]
    )
    for b in backups:
        if b.get("issues") or b.get("quality_issues"):
            with st.expander(f"⚠️ Avvisi — {b['file']}"):
                for issue in b.get("issues", []):
                    st.write(f"- {issue}")
                for issue in b.get("quality_issues", []):
                    st.write(f"- {issue}")


def render(today, now_italy):
    st.header("🩺 Salute sistema")
    _render_observability()
    st.divider()
    _render_failed_jobs()
    st.divider()
    _render_backups()
