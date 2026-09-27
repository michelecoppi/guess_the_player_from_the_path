"""product analytics administration page."""
from admin_pages.shared import (
    cached_core_metrics,
    product_analytics_query,
    show_table,
    st,
)


def _format(row):
    if row["value"] is None:
        return "—"
    if row["format"] == "percent":
        return f"{row['value'] * 100:.1f}%"
    return f"{row['value']:.2f}"


def render(today, now_italy):
    st.header("📈 Analytics")
    settings = product_analytics_query.settings()

    if not settings.configured:
        st.warning(
            f"PostHog non configurato per la lettura: imposta `{product_analytics_query.ENV_PERSONAL_API_KEY}` "
            f"e `{product_analytics_query.ENV_PROJECT_ID}` nel `.env` (una **Personal API Key**, diversa dalla "
            "chiave di progetto usata per l'invio degli eventi in `services/product_analytics.py`)."
        )
        return

    st.caption(
        "Metriche calcolate al volo su PostHog con una query HogQL sola-lettura per ciascuna "
        "(docs/product-analytics.md §12): niente viene scritto o modificato. I funnel multi-step "
        "(onboarding, referral, shop — docs §11) restano nel proprio insight su PostHog, perché "
        "richiedono di correlare più eventi nella sessione dello stesso utente."
    )
    days = st.select_slider("Finestra temporale", options=[1, 7, 14, 30, 90], value=7, format_func=lambda d: f"{d} giorni")

    try:
        rows = cached_core_metrics(days)
    except Exception as e:
        st.error(f"Errore leggendo le metriche da PostHog: {e}")
        return

    cols = st.columns(3)
    for i, row in enumerate(rows):
        cols[i % 3].metric(row["label"], _format(row))

    errors = [row for row in rows if row["error"]]
    if errors:
        with st.expander(f"⚠️ {len(errors)} metrica/e non disponibile/i"):
            show_table([{"metrica": row["label"], "errore": row["error"]} for row in errors])
