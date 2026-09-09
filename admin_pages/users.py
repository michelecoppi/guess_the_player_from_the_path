"""users administration page."""
from admin_pages.shared import (
    SUPPORTED_LANGUAGES,
    cached_overview,
    cached_top_users,
    firebase_service,
    fmt_bool,
    fmt_dt,
    guarded,
    show_table,
    st,
    to_display,
)


def render(today, now_italy):
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
