"""Daily planner administration page (#30)."""
from datetime import date

from admin_pages.shared import (
    cached_daily_plan,
    cached_planner_exclusions,
    confirm_button,
    content_admin,
    count_label,
    daily_planner,
    get_player_by_id,
    guarded,
    load_config,
    parse_iso,
    player_picker,
    show_table,
    st,
    to_display,
    to_iso,
)

MODE_LABELS = {
    daily_planner.MODE_FILL: "Riempi solo i giorni vuoti",
    daily_planner.MODE_REPLAN: "Ripianifica i giorni futuri non bloccati (le scelte a mano restano)",
}


def render(today, now_italy):
    st.header("🗓️ Planner delle sfide giornaliere")
    settings = daily_planner.planner_settings(load_config())
    st.caption(
        "Propone un calendario fino a 90 giorni con le stesse regole del job notturno e del bottone "
        f"*Rigenera*: nessun giocatore ripetuto entro {settings['player_cooldown_days']} giorni (prima e dopo), "
        f"fascia dalla rotazione `{' → '.join(settings['rotation'])}` con al massimo "
        f"{settings['max_same_band_streak']} giorni di fila nella stessa fascia, nessun club in comune entro "
        f"{settings['club_cooldown_days']} giorni e nessuna nazionalità ripetuta entro "
        f"{settings['nationality_cooldown_days']}. Quando non basta, una regola si allenta e **l'audit lo dice**. "
        "Niente viene scritto finché non premi *Applica*. Regole in `data/config.json` → `daily_planner`, "
        "dettagli in `docs/game-modes.md`."
    )

    col1, col2 = st.columns([1, 2])
    start = col1.date_input("Primo giorno", value=parse_iso(today).date(), format="DD/MM/YYYY", key="planner_start")
    days = col2.slider(
        "Giorni da pianificare", 7, daily_planner.MAX_HORIZON_DAYS, settings["horizon_days"], key="planner_days"
    )
    mode = st.radio(
        "Cosa può cambiare", list(MODE_LABELS), format_func=MODE_LABELS.get, horizontal=True, key="planner_mode"
    )

    variants = st.session_state.setdefault("planner_variants", {})
    start_iso = to_iso(start if isinstance(start, date) else parse_iso(today))
    try:
        plan = cached_daily_plan(start_iso, days, mode, tuple(sorted(variants.items())), today)
    except daily_planner.PlannerError as e:
        st.error(str(e))
        return
    except Exception as e:  # noqa: BLE001 - in dashboard l'errore va mostrato
        st.error(f"Errore costruendo il piano: {e}")
        return

    summary = plan["summary"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Da creare", summary["actions"][daily_planner.ACTION_CREATE])
    m2.metric("Da sostituire", summary["actions"][daily_planner.ACTION_REPLACE])
    m3.metric("Restano come sono", summary["actions"][daily_planner.ACTION_KEEP])
    m4.metric("Serie più lunga nella stessa fascia", summary["longest_band_streak"])

    if summary["relaxed"]:
        st.warning(
            "Regole allentate per mancanza di candidati: "
            + ", ".join(f"{rule} × {n}" for rule, n in sorted(summary["relaxed"].items()))
            + ". Guarda l'audit dei giorni interessati, o riduci le esclusioni."
        )
    if summary["repeated_players"]:
        st.warning("Giocatori che compaiono più volte nel calendario: " + ", ".join(summary["repeated_players"]))
    if summary["missing_days"]:
        st.info(
            "Giorni passati senza sfida (non si creano più): "
            + ", ".join(to_display(day) for day in summary["missing_days"])
        )

    show_table(
        [{"fascia": band, "giorni": n} for band, n in summary["bands"].items()],
    )

    st.subheader("Calendario proposto")
    show_table([_plan_row(row) for row in plan["days"]], "Nessun giorno nella finestra.")

    _render_day_review(plan, variants, today)

    st.divider()
    st.subheader("💾 Applica")
    changes = summary["actions"][daily_planner.ACTION_CREATE] + summary["actions"][daily_planner.ACTION_REPLACE]
    if not changes:
        st.caption("Niente da scrivere: il calendario è già come proposto.")
    else:
        st.caption(
            "Ogni giorno viene ricontrollato subito prima di scriverlo: se nel frattempo è stato bloccato, "
            "creato o cambiato da qualcun altro, si salta. Ogni sfida scritta porta il suo audit (`planner_audit`)."
        )
        if confirm_button(
            f"💾 Applica il piano ({count_label(changes, 'giorno', 'giorni')})", "apply_planner",
            "Scrive le sfide sul database di produzione.",
        ):
            def _apply():
                result = daily_planner.apply_plan(plan)
                st.session_state["planner_variants"] = {}
                return result

            guarded(
                _apply,
                lambda r: f"Piano applicato: {count_label(len(r['written']), 'sfida scritta', 'sfide scritte')}"
                + (
                    "; saltati " + ", ".join(f"{to_display(s['day'])} ({s['reason']})" for s in r["skipped"])
                    if r["skipped"] else "."
                ),
            )

    st.divider()
    _render_exclusions(today)


def _plan_row(row):
    audit = row["audit"] or {}
    return {
        "giorno": f"{content_admin.WEEKDAYS_IT[parse_iso(row['day']).weekday()]} {to_display(row['day'])}",
        "azione": row["action"],
        "motivo": row["reason"] or "",
        "giocatore": row["player_name"] or row["player_id"] or "—",
        "nazionalità": row["nationality"] or "—",
        "fascia": row["band"] or "—",
        "fascia prevista": audit.get("target_band", "—"),
        "regole allentate": ", ".join(audit.get("relaxed", [])) if audit else "—",
        "candidati": audit.get("candidates", "—"),
        "🔒": "sì" if row["locked"] else "",
    }


def _render_day_review(plan, variants, today):
    st.subheader("🔍 Rivedi un giorno")
    options = {
        f"{to_display(row['day'])} — {row['player_name'] or row['player_id'] or 'nessuna sfida'} ({row['action']})": row
        for row in plan["days"]
    }
    choice = st.selectbox("Giorno", list(options), index=None, placeholder="Scegli un giorno…", key="planner_day_pick")
    if not choice:
        return
    row = options[choice]
    audit = row["audit"] or {}

    if audit:
        st.caption(
            "Da quanti candidati è partita la scelta e quanti ne restavano dopo ogni regola: "
            "un imbuto che si svuota dice quale regola ha deciso."
        )
        show_table([
            {"passaggio": "schede selezionabili (non sospese)", "candidati": audit.get("pool")},
            {"passaggio": "non escluse dal planner", "candidati": audit.get("eligible")},
            {"passaggio": "non usate a ridosso", "candidati": audit.get("after_player_cooldown")},
            {"passaggio": "senza club in comune coi vicini", "candidati": audit.get("after_club")},
            {"passaggio": "nazionalità diversa dai vicini", "candidati": audit.get("after_nationality")},
            {"passaggio": f"nella fascia scelta ({audit.get('band')})", "candidati": audit.get("candidates")},
        ])
        if audit.get("relaxed"):
            st.warning("Regole allentate per questo giorno: " + ", ".join(audit["relaxed"]))
    else:
        st.caption("Nessun audit: la sfida è stata creata prima del planner o a mano.")

    day = row["day"]
    if row["action"] != daily_planner.ACTION_KEEP:
        col1, col2 = st.columns(2)
        if col1.button("🎲 Un altro giocatore per questo giorno", key=f"planner_variant_{day}"):
            variants[day] = variants.get(day, 0) + 1
            st.rerun()
        if variants.get(day) and col2.button("↩️ Torna alla prima proposta", key=f"planner_reset_{day}"):
            variants.pop(day, None)
            st.rerun()

        if row["player_id"]:
            with st.expander(f"🙅 Escludi {row['player_name'] or row['player_id']} dal planner"):
                reason = st.text_input("Motivo", key=f"planner_excl_reason_{day}")
                until = st.date_input("Fino al (vuoto = finché non lo riammetti)", value=None,
                                      format="DD/MM/YYYY", key=f"planner_excl_until_{day}")
                if st.button("🙅 Escludi e ricalcola", key=f"planner_exclude_{day}"):
                    guarded(
                        lambda pid=row["player_id"], r=reason, u=until: daily_planner.exclude_player(
                            pid, r, to_iso(u) if u else None
                        ),
                        lambda pid: f"'{pid}' escluso dal planner: il calendario è stato ricalcolato.",
                    )
    elif day > today and row["previous_player_id"]:
        label = "🔓 Sblocca il giorno" if row["locked"] else "🔒 Blocca il giorno (il planner non lo toccherà)"
        if st.button(label, key=f"planner_lock_{day}"):
            guarded(
                lambda d=day, locked=not row["locked"]: content_admin.set_daily_locked(d, locked),
                f"Sfida del {to_display(day)} {'sbloccata' if row['locked'] else 'bloccata'}.",
            )
    else:
        st.caption("Giorno in gioco o passato: non si modifica da qui (vedi *Sfide giornaliere*).")


def _render_exclusions(today):
    st.subheader("🙅 Esclusi dal planner")
    st.caption(
        "Scelta editoriale sul calendario (es. \"appena uscito in tendenza\"), con scadenza facoltativa. "
        "Diverso da *Giocatori sospesi*, che toglie una scheda con un dato sbagliato da tutto il gioco. "
        "Le sfide già scritte non cambiano: ripianifica per applicare l'esclusione."
    )
    try:
        exclusions = cached_planner_exclusions()
    except Exception as e:  # noqa: BLE001
        st.error(f"Errore leggendo le esclusioni: {e}")
        exclusions = {}

    if not exclusions:
        st.caption("Nessun giocatore escluso.")
    for player_id, info in sorted(exclusions.items()):
        player = get_player_by_id(player_id)
        active = daily_planner.exclusion_active(info, today)
        col1, col2 = st.columns([4, 1])
        col1.write(
            f"`{player_id}` — {(player or {}).get('full_name', 'non più nel dataset')} · "
            + (f"fino al {to_display(info['until'])}" if info.get("until") else "senza scadenza")
            + ("" if active else " (scaduta)")
            + (f" · _{info['reason']}_" if info.get("reason") else "")
        )
        if col2.button("Riammetti", key=f"planner_include_{player_id}"):
            guarded(
                lambda pid=player_id: daily_planner.include_player(pid),
                f"'{player_id}' riammesso nel planner.",
            )

    chosen = player_picker("planner_pick_exclude", "Escludi un altro giocatore")
    col1, col2 = st.columns(2)
    reason = col1.text_input("Motivo", key="planner_exclude_reason")
    until = col2.date_input("Fino al", value=None, format="DD/MM/YYYY", key="planner_exclude_until")
    if st.button("🙅 Escludi", disabled=not chosen, key="planner_exclude_btn"):
        guarded(
            lambda: daily_planner.exclude_player(chosen, reason, to_iso(until) if until else None),
            lambda pid: f"'{pid}' escluso dal planner.",
        )
