"""leagues administration page."""
from admin_pages.shared import (
    cached_leagues,
    firebase_service,
    fmt_dt,
    show_table,
    st,
)


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
