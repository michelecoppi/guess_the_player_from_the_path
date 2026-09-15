"""shop and referral administration page."""
from admin_pages.shared import (
    cached_referral_overview,
    cached_referral_top_inviters,
    collect_shop_changes,
    count_label,
    guarded,
    os,
    save_shop_changes,
    shop,
    shop_editor,
    show_table,
    st,
)


def _render_shop():
    st.subheader("🛍️ Catalogo cosmetici")
    st.caption(
        "Prezzo, nome (italiano) e blocco vendita separata: le altre proprietà (stile, "
        "traduzioni, pacchetti, traguardi) restano in data/shop.json, dove un errore si vede "
        "meglio che in una tabella."
    )

    kind_filter = st.selectbox("Filtra per tipo", ["tutti"] + list(shop.KINDS) + ["bundle"], key="shop_kind_filter")
    items = shop_editor.list_items()
    if kind_filter != "tutti":
        items = [item for item in items if item["kind"] == kind_filter]

    table = [
        {
            "id": item["id"],
            "tipo": item["kind"],
            "nome": item["name"],
            "prezzo": item["price"],
            "bloccato": item["locked"],
            "rarità": item["rarity"],
            "solo guadagnato": "sì" if item["earned_only"] else "",
        }
        for item in items
    ]

    if not table:
        st.info("📭 Nessun oggetto con questo filtro.")
        return

    edited = st.data_editor(
        table,
        key=f"shop_editor_{st.session_state.get('shop_rev', 0)}",
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=["id", "tipo", "rarità", "solo guadagnato"],
        column_config={
            "prezzo": st.column_config.NumberColumn(
                min_value=0, max_value=shop.MAX_STARS, step=1, format="%d",
                help="In Stelle Telegram (XTR). 0 = gratuito o consegnato solo dentro un pacchetto/traguardo.",
            ),
            "bloccato": st.column_config.CheckboxColumn(
                help="Se attivo, l'oggetto non si compra da solo: arriva solo dentro un pacchetto."
            ),
        },
    )

    changes = collect_shop_changes(table, edited)
    if not changes:
        st.caption("Nessuna modifica in sospeso.")
        return

    st.subheader("✏️ " + count_label(len(changes), "oggetto da salvare", "oggetti da salvare"))
    show_table(
        [{"id": item_id, "campi": ", ".join(f"{k}={v}" for k, v in fields.items())} for item_id, fields in changes.items()]
    )
    if st.button("💾 Salva nel catalogo", type="primary", key="save_shop_rows"):
        guarded(
            lambda: save_shop_changes(changes),
            lambda result: (
                count_label(len(result["changes"]), "oggetto salvato", "oggetti salvati")
                + f" in data/shop.json (copia di sicurezza: {os.path.basename(result['backup'])})."
            ),
        )


def _render_referrals():
    st.subheader("🤝 Programma referral")
    try:
        overview = cached_referral_overview()
        col1, col2, col3 = st.columns(3)
        col1.metric("Inviti totali", overview["total"])
        col2.metric("In corso", overview["pending"])
        col3.metric("Qualificati", overview["qualified"])
    except Exception as e:
        st.error(f"Errore leggendo i referral: {e}")

    st.markdown("**Top inviter (referral qualificati)**")
    try:
        show_table(
            [
                {"pos.": i, "telegram_id": u["telegram_id"], "nome": u["username"], "qualificati": u["referral_qualified"]}
                for i, u in enumerate(cached_referral_top_inviters(20), start=1)
                if u["referral_qualified"]
            ],
            "Nessun inviter con almeno un referral qualificato.",
        )
    except Exception as e:
        st.error(f"Errore: {e}")


def render(today, now_italy):
    st.header("🛍️ Shop & Referral")
    tab_shop, tab_referrals = st.tabs(["Catalogo", "Referral"])
    with tab_shop:
        _render_shop()
    with tab_referrals:
        _render_referrals()
