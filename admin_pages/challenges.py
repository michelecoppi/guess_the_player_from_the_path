"""challenges administration page."""
from admin_pages.shared import (
    DIFFICULTY_ORDER,
    MAX_ATTEMPTS,
    STATUS_ICON,
    cached_buffer_health,
    cached_daily_window,
    career_rows,
    compute_difficulty,
    compute_difficulty_score,
    confirm_button,
    content_admin,
    fmt_bool,
    fmt_dt,
    get_player_by_id,
    guarded,
    player_picker,
    render_career_path_image,
    show_table,
    st,
    to_display,
    to_iso,
)


def render(today, now_italy):
    st.header("📅 Sfide giornaliere pianificate")
    st.caption(
        "Ogni giorno della finestra, comprese le giornate **senza** sfida. "
        f"{STATUS_ICON[content_admin.STATUS_PAST]} passata · "
        f"{STATUS_ICON[content_admin.STATUS_TODAY]} oggi · "
        f"{STATUS_ICON[content_admin.STATUS_PLANNED]} programmata · "
        f"{STATUS_ICON[content_admin.STATUS_MISSING]} mancante"
    )

    col1, col2 = st.columns(2)
    days_back = col1.slider("Giorni passati da mostrare", 0, 30, 3)
    days_ahead = col2.slider("Giorni futuri da mostrare", 1, 60, 14)

    try:
        window = cached_daily_window(days_back, days_ahead, today)
        health = cached_buffer_health(today)
    except Exception as e:
        window, health = [], None
        st.error(f"Errore leggendo le sfide: {e}")

    if health:
        col1, col2, col3 = st.columns(3)
        col1.metric("Giorni coperti da oggi", health["covered_days"])
        col2.metric("Buffer previsto", f"{health['target_days']} giorni")
        col3.metric(
            "Coperto fino al",
            to_display(health["last_covered_day"]) if health["last_covered_day"] else "—",
        )

    show_table(
        [
            {
                "": STATUS_ICON[row["status"]],
                "giorno": f"{row['weekday']} {row['day_display']}",
                "#": row["challenge_number"],
                "soluzione": row["player_name"] or row["player_id"] or "—",
                "difficoltà": row["difficulty"] or "—",
                "punti": str(row["points"]) if row["exists"] else "—",
                "tappe": str(row["teams_count"]) if row["exists"] else "—",
                "origine": row["source"] or "—",
                "bonus primo": "assegnato" if row["first_correct_taken"] else ("libero" if row["exists"] else "—"),
                "verificato": fmt_bool(row["verified"]),
            }
            for row in window
        ],
        "Nessun giorno nella finestra.",
    )

    st.divider()
    st.subheader("🔧 Dettaglio e modifica")
    st.caption(f"Tentativi giornalieri per utente: {MAX_ATTEMPTS} (services/daily_challenge.py)")

    for row in window:
        day = row["day"]
        icon = STATUS_ICON[row["status"]]
        title = (
            f"{icon} {row['weekday']} {row['day_display']} · #{row['challenge_number']} · "
            + (f"{row['player_name'] or row['player_id']} ({row['difficulty']})" if row["exists"] else "nessuna sfida")
        )
        with st.expander(title, expanded=(day == today)):
            if not row["exists"]:
                st.warning("Nessuna sfida per questo giorno: gli utenti non avrebbero niente da giocare.")
                gen_col, pick_col = st.columns([1, 2])
                with gen_col:
                    if st.button("🎲 Genera automaticamente", key=f"gen_{day}"):
                        guarded(
                            lambda d=day: content_admin.regenerate_daily(d, avoid_current=False),
                            lambda r: f"Sfida del {to_display(r['day'])} generata: {r['player_name']} ({r['difficulty']}).",
                        )
                with pick_col:
                    chosen = player_picker(f"pick_missing_{day}", "Oppure scegli il giocatore")
                    if st.button("💾 Imposta questo giocatore", key=f"set_missing_{day}", disabled=not chosen):
                        guarded(
                            lambda d=day, p=chosen: content_admin.set_daily_player(d, p),
                            lambda r: f"Sfida del {to_display(r['day'])} impostata su {r['player_name']}.",
                        )
                continue

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Difficoltà", row["difficulty"] or "—", help=f"Punteggio calcolato: {row['difficulty_score']}")
            m2.metric("Punti in palio", row["points"])
            m3.metric("Tappe di carriera", row["teams_count"])
            m4.metric("Bonus primo", "assegnato" if row["first_correct_taken"] else "libero")

            st.caption(
                f"player_id `{row['player_id']}` · origine `{row['source']}` · "
                f"generata il {fmt_dt(row['generated_at'])} · "
                f"scheda verificata: {fmt_bool(row['verified'])}"
            )
            if not row["player_in_dataset"]:
                st.warning(
                    f"Il giocatore `{row['player_id']}` non esiste più in data/players.json: "
                    "la sfida funziona lo stesso (il percorso è salvato nel documento) ma il dataset è disallineato."
                )

            st.markdown("**Risposte accettate:** " + ", ".join(f"`{a}`" for a in row["answers"]))
            show_table(career_rows(row["career"]), "Percorso vuoto: la sfida non è giocabile.")

            if st.checkbox("🖼️ Anteprima immagine inviata agli utenti", key=f"img_{day}"):
                try:
                    image = render_career_path_image(
                        row["career"],
                        title="Percorso misterioso",
                        subtitle=f"Sfida #{row['challenge_number']}",
                        badge=(row["difficulty"] or "").upper(),
                    )
                    st.image(image, width=520)
                except Exception as e:
                    st.error(f"Impossibile generare l'anteprima: {e}")

            st.markdown("---")
            tab_player, tab_answers, tab_difficulty, tab_bonus, tab_delete = st.tabs(
                ["Cambia giocatore", "Risposte", "Difficoltà", "Bonus primo", "Elimina"]
            )

            with tab_player:
                if row["status"] == content_admin.STATUS_TODAY:
                    st.warning(
                        "Stai modificando la sfida **in corso**: chi ha già usato i tentativi non li recupera."
                    )
                chosen = player_picker(f"pick_{day}", "Nuovo giocatore")
                col_a, col_b = st.columns(2)
                if col_a.button("💾 Sostituisci", key=f"replace_{day}", disabled=not chosen):
                    guarded(
                        lambda d=day, p=chosen: content_admin.set_daily_player(d, p),
                        lambda r: f"Sfida del {to_display(r['day'])} impostata su {r['player_name']}.",
                    )
                if col_b.button("🎲 Rigenera (altro giocatore)", key=f"regen_{day}"):
                    guarded(
                        lambda d=day: content_admin.regenerate_daily(d, avoid_current=True),
                        lambda r: f"Sfida del {to_display(r['day'])} rigenerata: {r['player_name']} ({r['difficulty']}).",
                    )

            with tab_answers:
                st.caption(
                    "Separate da virgola. Vengono salvate in minuscolo: il confronto con la risposta "
                    "dell'utente ignora maiuscole e accenti (services/matching.py)."
                )
                answers_text = st.text_input(
                    "Risposte accettate", value=", ".join(row["answers"]), key=f"answers_{day}"
                )
                if st.button("💾 Salva risposte", key=f"save_answers_{day}"):
                    parsed = content_admin.parse_answers_list(answers_text)
                    guarded(
                        lambda d=day, a=parsed: content_admin.update_daily_answers(d, a),
                        lambda r: f"Risposte del {to_display(day)} aggiornate: {', '.join(r)}.",
                    )

            with tab_difficulty:
                suggested = None
                player = get_player_by_id(row["player_id"] or "")
                if player:
                    suggested = compute_difficulty(player)
                    st.caption(
                        f"Calcolata dal dataset: **{suggested}** "
                        f"(punteggio {round(compute_difficulty_score(player), 2)})"
                    )
                current_index = DIFFICULTY_ORDER.index(row["difficulty"]) if row["difficulty"] in DIFFICULTY_ORDER else 0
                new_difficulty = st.selectbox(
                    "Difficoltà (decide i punti assegnati)", DIFFICULTY_ORDER, index=current_index, key=f"diff_{day}"
                )
                if st.button("💾 Salva difficoltà", key=f"save_diff_{day}"):
                    guarded(
                        lambda d=day, v=new_difficulty: content_admin.update_daily_difficulty(d, v),
                        lambda r: f"Difficoltà del {to_display(day)} impostata su {r}.",
                    )

            with tab_bonus:
                st.caption(
                    "Il bonus del primo che indovina si assegna una volta sola. Riaprirlo ha senso "
                    "solo se la sfida è stata sostituita in corsa."
                )
                st.write(f"Stato attuale: **{'assegnato' if row['first_correct_taken'] else 'libero'}**")
                if row["first_correct_taken"]:
                    if st.button("🔓 Riapri il bonus", key=f"reopen_{day}"):
                        guarded(
                            lambda d=day: content_admin.set_daily_first_correct(d, False),
                            f"Bonus del {to_display(day)} riaperto.",
                        )
                else:
                    if st.button("🔒 Marca come già assegnato", key=f"close_{day}"):
                        guarded(
                            lambda d=day: content_admin.set_daily_first_correct(d, True),
                            f"Bonus del {to_display(day)} chiuso.",
                        )

            with tab_delete:
                if row["status"] == content_admin.STATUS_TODAY:
                    st.info("La sfida di oggi non si elimina: è in gioco. Sostituisci il giocatore o rigenerala.")
                else:
                    st.caption("Il documento `daily_path/" + day + "` viene eliminato definitivamente.")
                    if confirm_button("🗑️ Elimina la sfida", key=f"del_daily_{day}"):
                        guarded(
                            lambda d=day: content_admin.delete_daily(d),
                            f"Sfida del {to_display(day)} eliminata.",
                        )

    st.divider()
    st.subheader("➕ Programma una sfida in una data specifica")
    col1, col2 = st.columns(2)
    target_date = col1.date_input("Giorno", value=None, format="DD/MM/YYYY", key="new_day")
    chosen_new = player_picker("pick_new_day", "Giocatore")
    if col2.button("💾 Programma", type="primary", disabled=not (target_date and chosen_new)):
        guarded(
            lambda d=to_iso(target_date), p=chosen_new: content_admin.set_daily_player(d, p),
            lambda r: f"Sfida del {to_display(r['day'])} programmata su {r['player_name']}.",
        )
