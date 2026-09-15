"""groups administration page."""
from admin_pages.shared import (
    cached_groups,
    confirm_button,
    firebase_service,
    fmt_dt,
    get_player_by_id,
    guarded,
    show_table,
    st,
)


def render(today, now_italy):
    st.header("👥 Gruppi Telegram")
    st.caption(
        "Gruppi in cui e' stata avviata almeno una sfida di gruppo (/sfida): un round per "
        "volta, con la sua classifica interna, separata dai punti generali e dalle leghe."
    )
    limit = st.slider("Quanti gruppi mostrare", 1, 100, 20, key="groups_limit")
    try:
        groups = cached_groups(limit)
    except Exception as e:
        groups = []
        st.error(f"Errore leggendo i gruppi: {e}")

    show_table(
        [
            {
                "chat_id": g.get("chat_id"),
                "round #": g.get("number", 0),
                "giocatore": (get_player_by_id(g.get("player_id") or "") or {}).get("full_name") or g.get("player_id") or "—",
                "difficoltà": g.get("difficulty") or "—",
                "risolto da": g.get("solved_name") or ("nessuno" if g.get("solved_by") is None else g.get("solved_by")),
                "avviato il": fmt_dt(g.get("started_at")),
            }
            for g in groups
        ],
        "Nessun gruppo con una sfida avviata.",
    )

    for g in groups:
        chat_id = g.get("chat_id")
        with st.expander(f"👥 Gruppo `{chat_id}` — round #{g.get('number', 0)}"):
            try:
                members = firebase_service.get_group_leaderboard(chat_id, limit=50)
            except Exception as e:
                members = []
                st.error(f"Errore: {e}")
            show_table(
                [
                    {
                        "pos.": i,
                        "telegram_id": m.get("telegram_id"),
                        "nome": m.get("name", "—"),
                        "punti nel gruppo": m.get("points", 0),
                        "round vinti": m.get("rounds_won", 0),
                    }
                    for i, m in enumerate(members, start=1)
                ],
                "Nessun partecipante ancora.",
            )

            st.markdown("**Modera**")
            st.caption(
                "Chiude il round corrente e azzera la classifica interna del gruppo: il "
                "prossimo /sfida ne apre uno nuovo da zero. Non tocca punti generali o leghe."
            )
            if confirm_button(
                "🗑️ Chiudi round e azzera classifica",
                key=f"reset_group_{chat_id}",
                help_text="Elimina il round corrente e i punteggi interni del gruppo, in modo irreversibile.",
            ):
                guarded(
                    lambda c=chat_id: firebase_service.delete_group_round(c),
                    f"Round e classifica del gruppo {chat_id} azzerati.",
                )
