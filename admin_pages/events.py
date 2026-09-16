"""events administration page."""
from admin_pages.shared import (
    EVENT_STATUS_ICON,
    STATUS_ICON,
    cached_events,
    cached_participants,
    confirm_button,
    content_admin,
    create_manual_event,
    event_config,
    event_template_editor,
    fmt_bool,
    fmt_dt,
    guarded,
    load_templates,
    parse_start_date,
    show_table,
    st,
    to_display,
    to_iso,
)


def render(today, now_italy):
    st.header("🎊 Eventi")
    st.caption(
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_RUNNING]} in corso · "
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_PLANNED]} programmato · "
        f"{EVENT_STATUS_ICON[content_admin.EVENT_STATUS_ENDED]} concluso"
    )

    limit = st.slider("Quanti eventi mostrare", 1, 30, 8)
    try:
        events = cached_events(limit)
    except Exception as e:
        events = []
        st.error(f"Errore leggendo gli eventi: {e}")

    details = [content_admin.describe_event(event, today=today) for event in events]

    show_table(
        [
            {
                "": EVENT_STATUS_ICON[d["status"]],
                "codice": d["code"],
                "nome": d["name"],
                "periodo": d["period"],
                "giorno": f"{d['current_index']}/{d['days_total']}" if d["current_index"] else f"—/{d['days_total']}",
                "tipo": d["type"],
                "origine": d["source"],
                "attivo": fmt_bool(d["active"]),
                "partecipanti": d["participants_count"],
                "trofei il": to_display(d["trophy_day"]),
            }
            for d in details
        ],
        "Nessun evento presente.",
    )

    for detail in details:
        code = detail["code"]
        icon = EVENT_STATUS_ICON[detail["status"]]
        with st.expander(
            f"{icon} {detail['name']} [{code}] — {detail['status']} — {detail['period']}",
            expanded=(detail["status"] == content_admin.EVENT_STATUS_RUNNING),
        ):
            st.write(detail["description"] or "_nessuna descrizione_")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Stato", detail["status"])
            m2.metric(
                "Giorno",
                f"{detail['current_index']}/{detail['days_total']}" if detail["current_index"]
                else f"—/{detail['days_total']}",
            )
            m3.metric("Partecipanti", detail["participants_count"] or 0)
            m4.metric("Trofei il", to_display(detail["trophy_day"]) or "—")

            st.caption(
                f"template `{detail['template_id']}` · tipo `{detail['type']}` · "
                f"categoria `{detail['category']}` · difficoltà `{detail['difficulty']}` · "
                f"origine `{detail['source']}` · attivo: {fmt_bool(detail['active'])} · "
                f"creato il {fmt_dt(detail['generated_at'])}"
            )
            if detail["days_without_content"]:
                st.error(
                    "Giorni dell'evento **senza contenuto**: "
                    + ", ".join(detail["days_without_content"])
                    + ". Chi gioca in quei giorni non trova niente."
                )

            st.markdown("**Giorni dell'evento**")
            show_table(
                [
                    {
                        "": STATUS_ICON[d["status"]],
                        "g.": d["index"],
                        "giorno": f"{d['weekday']} {d['day_display']}",
                        "contenuto": d["player_name"] or d["pair_id"] or ("foto" if d["image_url"] else "—"),
                        "risposte": ", ".join(d["answers"]) if d["answers"] else "— VUOTO —",
                        "min. giuste": str(d["min_correct"]) if d["min_correct"] else "—",
                        "punti": str(d["points"]) if d["points"] is not None else "—",
                        "bonus primo": "assegnato" if d["first_correct_taken"] else "libero",
                    }
                    for d in detail["days"]
                ],
                "L'evento non ha giorni.",
            )

            st.markdown("**Classifica partecipanti**")
            try:
                participants = cached_participants(code)
            except Exception as e:
                participants = []
                st.error(f"Errore leggendo i partecipanti: {e}")
            show_table(
                [
                    {
                        "pos.": i,
                        "telegram_id": str(p.get("telegram_id") or p.get("id") or "—"),
                        "nome": p.get("name", "—"),
                        "punti": p.get("points", 0),
                        "ultimo giorno giocato": to_display(p.get("last_played_day")),
                        "ha indovinato": fmt_bool(p.get("has_guessed_today")),
                        "tentativi oggi": p.get("daily_attempts", 0),
                    }
                    for i, p in enumerate(participants, start=1)
                ],
                "Ancora nessun partecipante.",
            )

            st.markdown("---")
            tab_state, tab_dates, tab_answers, tab_bonus, tab_delete = st.tabs(
                ["Attivazione", "Sposta date", "Risposte di un giorno", "Bonus di giornata", "Elimina"]
            )

            with tab_state:
                st.caption(
                    "Disattivare un evento è il modo pulito per fermarlo: resta lo storico e restano i punti "
                    "già assegnati."
                )
                if detail["active"]:
                    if st.button("⏸️ Disattiva", key=f"deact_{code}"):
                        guarded(lambda c=code: content_admin.set_event_active(c, False), f"Evento {code} disattivato.")
                else:
                    if st.button("▶️ Riattiva", key=f"act_{code}"):
                        guarded(lambda c=code: content_admin.set_event_active(c, True), f"Evento {code} riattivato.")

            with tab_dates:
                st.caption(
                    "Sposta insieme date, contenuti di ogni giorno e giorno dei trofei. "
                    "Un evento già concluso non si sposta."
                )
                new_start = st.date_input(
                    "Nuova data di inizio", value=None, format="DD/MM/YYYY", key=f"shift_{code}"
                )
                if st.button("📆 Sposta l'evento", key=f"do_shift_{code}", disabled=not new_start):
                    guarded(
                        lambda c=code, d=(to_iso(new_start) if new_start else ""): content_admin.shift_event(c, d),
                        lambda r: f"Evento {code} spostato: {to_display(r['dates'][0])} → {to_display(r['dates'][-1])}.",
                    )

            with tab_answers:
                day_options = {f"{d['day_display']} (g. {d['index']})": d for d in detail["days"]}
                if not day_options:
                    st.caption("L'evento non ha giorni.")
                else:
                    picked_label = st.selectbox("Giorno", list(day_options), key=f"day_pick_{code}")
                    picked = day_options[picked_label]
                    text = st.text_input(
                        "Risposte accettate (separate da virgola)",
                        value=", ".join(picked["answers"]),
                        key=f"ev_answers_{code}",
                    )
                    if st.button("💾 Salva risposte", key=f"save_ev_answers_{code}"):
                        parsed = content_admin.parse_answers_list(text)
                        guarded(
                            lambda c=code, d=picked["day"], a=parsed: content_admin.update_event_day_answers(c, d, a),
                            lambda r: f"Risposte del {picked['day_display']} aggiornate: {', '.join(r)}.",
                        )

            with tab_bonus:
                day_options = {f"{d['day_display']} (g. {d['index']})": d for d in detail["days"]}
                if not day_options:
                    st.caption("L'evento non ha giorni.")
                else:
                    picked_label = st.selectbox("Giorno", list(day_options), key=f"bonus_pick_{code}")
                    picked = day_options[picked_label]
                    st.write(f"Stato: **{'assegnato' if picked['first_correct_taken'] else 'libero'}**")
                    col_a, col_b = st.columns(2)
                    if col_a.button("🔓 Riapri", key=f"ev_reopen_{code}"):
                        guarded(
                            lambda c=code, d=picked["day"]: content_admin.set_event_day_first_correct(c, d, False),
                            f"Bonus del {picked['day_display']} riaperto.",
                        )
                    if col_b.button("🔒 Chiudi", key=f"ev_close_{code}"):
                        guarded(
                            lambda c=code, d=picked["day"]: content_admin.set_event_day_first_correct(c, d, True),
                            f"Bonus del {picked['day_display']} chiuso.",
                        )

            with tab_delete:
                if detail["status"] == content_admin.EVENT_STATUS_RUNNING:
                    st.info("L'evento è in corso: disattivalo invece di eliminarlo.")
                else:
                    st.caption("Elimina l'evento **e tutti i suoi partecipanti** (classifica compresa).")
                    if confirm_button("🗑️ Elimina l'evento", key=f"del_event_{code}"):
                        guarded(lambda c=code: content_admin.delete_event(c), f"Evento {code} eliminato.")

    st.divider()
    st.subheader("➕ Crea evento manuale")
    templates = load_templates()
    template_by_id = {t["id"]: t for t in templates}
    template_id = st.selectbox("Template", list(template_by_id))
    template = template_by_id[template_id]
    st.caption(
        f"**{template['name']}** — {template['description']}\n\n"
        f"tipo `{template['type']}` · durata {template['duration_days']} giorni · "
        f"{template['rewards']['points_per_day']} punti/giorno · "
        f"filtri: {template['filters'] or 'nessuno'} · calendario: {event_config.schedule_label(template)}"
    )

    col1, col2 = st.columns(2)
    start_text = col1.text_input("Data inizio (gg/mm/aa, vuoto = oggi)")
    duration = col2.number_input("Durata (giorni, 0 = default template)", min_value=0, value=0)

    if st.button("✅ Crea evento", type="primary"):
        def _create():
            start_date = parse_start_date(start_text or None)
            return create_manual_event(template_id, start_date=start_date, duration_days=duration or None)

        guarded(
            _create,
            lambda s: (
                f"Evento creato: {s['name']} [{s['code']}] — {s['days']} giorni "
                f"({to_display(s['dates'][0])} → {to_display(s['dates'][-1])}), trofei il {to_display(s['trophy_day'])}."
            ),
        )

    st.divider()
    _render_templates(now_italy)


def _render_templates(now_italy):
    st.subheader("📐 Template eventi")
    st.caption(
        "Un evento nuovo si crea scrivendo un template, non codice: tipo di gioco, filtri sul pool, "
        "regole della partita, premi e calendario. Schema ed esempi in `docs/event-templates.md`. "
        "Si salva solo un template valido, con copia di sicurezza in `backup/`; la modifica cambia "
        "`data/event_templates.json` in **questa copia locale**: per portarla in produzione va "
        "committata e rilasciata. Gli eventi già creati non cambiano."
    )
    try:
        rows = event_template_editor.list_templates()
    except Exception as e:  # noqa: BLE001 - in dashboard l'errore va mostrato
        st.error(f"Errore leggendo i template: {e}")
        return
    show_table(
        [
            {
                "id": row["id"],
                "nome": row["name"],
                "tipo": row["type"],
                "calendario": row["schedule"],
                "giorni": row["duration_days"],
                "punti/giorno": row.get("points_per_day", "—"),
                "candidati": row["candidates"] if row["candidates"] is not None else "—",
                "valido": "sì" if row["valid"] else "NO: " + "; ".join(row["errors"]),
            }
            for row in rows
        ],
        "Nessun template.",
    )

    new_label = "➕ Nuovo template"
    choice = st.selectbox("Template da modificare", [new_label] + [row["id"] for row in rows], key="tpl_pick")
    original_id = None if choice == new_label else choice
    text_key = f"tpl_text_{choice}"
    if text_key not in st.session_state:
        st.session_state[text_key] = event_template_editor.template_text(original_id)
    text = st.text_area("JSON del template", key=text_key, height=420)

    try:
        template = event_template_editor.parse_template(text)
        preview = event_template_editor.preview_template(template, original_id=original_id, today=now_italy)
    except event_template_editor.TemplateEditError as e:
        st.error(str(e))
        return

    if not preview["valid"]:
        st.error("Template non valido:\n\n" + "\n".join(f"- {error}" for error in preview["errors"]))
        return

    resolved = preview["resolved"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candidati", preview["candidates"] if preview["candidates"] is not None else "—")
    m2.metric("Tentativi al giorno", resolved["rules"]["attempts"])
    m3.metric("Punti + bonus primo", f"{resolved['rewards']['points_per_day']} + {resolved['rewards']['first_correct_bonus']}")
    m4.metric("Trofei", f"primi {resolved['rewards']['podium_trophies']}" if resolved["rewards"]["podium_trophies"] else "nessuno")
    st.caption(
        f"Calendario: {event_config.schedule_label(resolved)}"
        + (f" · prossime partenze possibili: {', '.join(to_display(d) for d in preview['next_starts'])}"
           if preview["next_starts"] else "")
    )
    for warning in preview["warnings"]:
        st.warning(warning)
    if preview["sample_days"]:
        st.markdown("**Evento d'esempio** (non salvato)")
        show_table(
            [
                {
                    "giorno": to_display(day["day"]),
                    "risposta": day["answer"],
                    "risposte accettate": day["answers"],
                    "minimo giuste": day["min_correct"] or "—",
                    "tappe mostrate": day["stops_shown"],
                    "punti": day["points"],
                }
                for day in preview["sample_days"]
            ]
        )

    label = "💾 Crea il template" if original_id is None else f"💾 Salva le modifiche a '{original_id}'"
    if confirm_button(label, f"save_tpl_{choice}", "Scrive data/event_templates.json (con copia di sicurezza)."):
        def _save():
            result = event_template_editor.save_template(template, original_id=original_id)
            st.session_state.pop(text_key, None)
            return result

        guarded(
            _save,
            lambda r: f"Template '{r['id']}' {'creato' if r['created'] else 'aggiornato'} "
            f"(copia di sicurezza: {r['backup']}).",
        )
