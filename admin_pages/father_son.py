"""father_son administration page."""
from admin_pages.shared import (
    ADMIN_TELEGRAM_IDS,
    BOT_TOKEN,
    asyncio,
    firebase_service,
    guarded,
    parse_answers,
    st,
)


def render(today, now_italy):
    st.header("👨‍👦 Coppie padre/figlio")
    try:
        pairs = firebase_service.list_father_son_pairs()
    except Exception as e:
        pairs = []
        st.error(f"Errore: {e}")

    st.subheader("Coppie salvate")
    if not pairs:
        st.info("📭 Nessuna coppia padre/figlio salvata.")
    else:
        st.caption(f"{len(pairs)} coppie · {sum(1 for p in pairs if not p.get('used_in_events'))} ancora da usare")
        for pair in pairs:
            used = ", ".join(pair.get("used_in_events", [])) or "mai usata"
            col1, col2 = st.columns([5, 1])
            col1.write(f"`{pair['id']}` — {', '.join(pair.get('answers', []))} ({used})")
            if col2.button("Elimina", key=f"del_pair_{pair['id']}"):
                guarded(
                    lambda pid=pair["id"]: firebase_service.delete_father_son_pair(pid),
                    f"Coppia {pair['id']} eliminata.",
                )

    st.divider()
    st.subheader("Aggiungi coppia")
    st.caption(
        "La foto viene inviata al bot (serve un ADMIN_TELEGRAM_IDS già avviato in chat con il bot) "
        "per ottenere il file_id da Telegram: nessuna copia dell'immagine viene salvata altrove."
    )
    photo = st.file_uploader("Foto della coppia", type=["jpg", "jpeg", "png"])
    answers_text = st.text_input("Risposte accettate (separate da virgola)", placeholder="Maldini, Paolo e Cesare Maldini")
    admin_chat_id = st.number_input(
        "Chat id admin a cui inviare la foto",
        value=ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else 0,
        step=1,
    )

    if st.button("➕ Salva coppia", type="primary"):
        answers = parse_answers(answers_text)
        if not photo:
            st.error("Serve una foto.")
        elif not answers:
            st.error("Servono le risposte accettate.")
        elif not admin_chat_id:
            st.error("Serve una chat id admin valida.")
        else:
            def _save():
                from telegram import Bot

                async def _send():
                    bot = Bot(token=BOT_TOKEN)
                    return await bot.send_photo(chat_id=int(admin_chat_id), photo=photo.getvalue())

                message = asyncio.run(_send())
                file_id = message.photo[-1].file_id
                return firebase_service.add_father_son_pair(
                    {"file_id": file_id, "answers": answers, "added_by": "admin_ui"}
                )

            guarded(_save, lambda pid: f"Coppia salvata (id {pid}). Risposte: {', '.join(answers)}")
