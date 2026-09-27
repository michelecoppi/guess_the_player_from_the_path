"""blocked administration page."""
from admin_pages.shared import (
    ContentAdminError,
    cached_blocked_ids,
    firebase_service,
    get_player_by_id,
    guarded,
    player_picker,
    st,
)


def render(today, now_italy):
    st.header("🚫 Giocatori sospesi")
    st.caption(
        "I giocatori sospesi restano fuori dalla selezione automatica finché non vengono riammessi. "
        "Le sfide già in buffer non cambiano: controllale nella sezione Sfide giornaliere."
    )

    try:
        blocked = cached_blocked_ids()
    except Exception as e:
        blocked = []
        st.error(f"Errore: {e}")

    if not blocked:
        st.success("✅ Nessun giocatore sospeso.")
    else:
        for player_id in blocked:
            player = get_player_by_id(player_id)
            col1, col2 = st.columns([4, 1])
            col1.write(f"`{player_id}` — {(player or {}).get('full_name', 'non più nel dataset')}")
            if col2.button("Riammetti", key=f"unblock_{player_id}"):
                guarded(
                    lambda pid=player_id: firebase_service.unblock_player_id(pid),
                    f"'{player_id}' riammesso nella selezione automatica.",
                )

    st.divider()
    st.subheader("Sospendi un giocatore")
    chosen = player_picker("pick_block", "Giocatore da sospendere")
    if st.button("🚫 Sospendi", disabled=not chosen):
        def _block():
            if not get_player_by_id(chosen):
                raise ContentAdminError(f"Nessun giocatore con id '{chosen}' nel dataset.")
            firebase_service.block_player_id(chosen)

        guarded(_block, f"'{chosen}' sospeso dalla selezione automatica.")
