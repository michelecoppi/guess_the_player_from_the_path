"""leagues administration page."""
from admin_pages.shared import (
    ContentAdminError,
    cached_leagues,
    confirm_button,
    firebase_service,
    fmt_dt,
    guarded,
    show_table,
    st,
)


def _kick_member(code, user_id):
    if not firebase_service.leave_league(code, user_id):
        raise ContentAdminError(f"'{user_id}' non e' membro della lega {code}.")


def render(today, now_italy):
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
        code = lg["code"]
        with st.expander(f"🏆 {lg.get('name', '—')} [{code}] — {lg.get('members_count', 0)} membri"):
            try:
                members = firebase_service.get_league_leaderboard(code, limit=50)
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

            st.markdown("**Modera**")
            kick_col, kick_button_col = st.columns([2, 1])
            kick_id = kick_col.text_input("Espelli un membro (telegram id)", key=f"kick_{code}")
            if kick_button_col.button("👋 Espelli", key=f"kick_btn_{code}", disabled=not kick_id.strip()):
                guarded(
                    lambda c=code, uid=kick_id.strip(): _kick_member(c, uid),
                    f"Utente espulso dalla lega {code}.",
                )
            if confirm_button("🗑️ Elimina lega", key=f"del_league_{code}", help_text="Elimina la lega e tutti i suoi membri, in modo irreversibile."):
                guarded(
                    lambda c=code: firebase_service.delete_league(c),
                    f"Lega {code} eliminata.",
                )
