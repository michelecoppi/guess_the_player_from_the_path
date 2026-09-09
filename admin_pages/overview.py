"""overview administration page."""
from admin_pages.shared import (
    STATUS_ICON,
    after_write,
    cached_blocked_ids,
    cached_buffer_health,
    cached_daily_window,
    cached_dataset_report,
    cached_overview,
    content_admin,
    ensure_daily_buffer,
    firebase_service,
    maybe_generate_event,
    show_table,
    st,
    to_display,
)


def render(today, now_italy):
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
