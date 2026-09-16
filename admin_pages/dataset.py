"""dataset administration page."""
from admin_pages.shared import (
    DATASET_STATUSES,
    DIFFICULTY_ORDER,
    DatasetEditError,
    as_records,
    band_cutoffs_100,
    cached_blocked_ids,
    cached_dataset_report,
    cached_difficulty_calibration,
    collect_player_changes,
    confirm_button,
    count_label,
    dataset_editor,
    explain_difficulty,
    get_incomplete_or_unverified_players,
    get_player_by_id,
    guarded,
    load_config,
    os,
    save_difficulty_settings,
    save_player_changes,
    show_table,
    st,
)


def render(today, now_italy):
    st.header("📚 Dataset dei calciatori")
    st.caption(
        "La difficoltà **non è un campo del dataset**: esce dal calcolo descritto in "
        "`docs/difficolta.md`. Quando una fascia non convince, nell'ordine: si corregge la "
        "**notorietà** della scheda, poi il **campionato** di una tappa scritto male, e solo "
        "se il problema si ripete su molte schede si tocca la **taratura** globale."
    )

    try:
        blocked = cached_blocked_ids()
    except Exception as e:
        blocked = []
        st.error(f"Errore: {e}")

    tab_health, tab_list, tab_card, tab_tuning, tab_calibration = st.tabs(
        ["📈 Salute", "📋 Elenco e modifiche", "🔍 Scheda singola", "🎚️ Taratura difficoltà",
         "🧪 Prevista vs osservata"]
    )

    # -- Salute -------------------------------------------------------------
    with tab_health:
        try:
            report = cached_dataset_report(tuple(blocked))
        except Exception as e:
            report = None
            st.error(f"Errore costruendo il report: {e}")

        if report:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Totale", report["total"])
            col2.metric("Verificati", report["verified"])
            col3.metric("Selezionabili", report["selectable"])
            col4.metric("Autonomia", f"{report['autonomy_days']} giorni")

            st.subheader("Per difficoltà")
            st.bar_chart(report["by_difficulty"])

            st.subheader("Eventi tematici")
            show_table(
                [
                    {
                        "template": t["id"],
                        "candidati": t["candidates"],
                        "durata (giorni)": t["duration_days"],
                        "stato": "manuale" if t["manual_only"] else ("ok" if t["ok"] else "POCHI CANDIDATI"),
                    }
                    for t in report["templates"]
                ]
            )

            if report["warnings"]:
                st.subheader("⚠️ Avvisi")
                for w in report["warnings"]:
                    st.warning(w)

        st.subheader("Giocatori esclusi dalla selezione automatica")
        incomplete = get_incomplete_or_unverified_players()
        if not incomplete:
            st.success("✅ Nessun giocatore da rivedere: dataset pulito.")
        else:
            show_table(
                [
                    {"id": item["id"], "nome": item["full_name"], "problemi": "; ".join(item["problems"])}
                    for item in incomplete
                ]
            )

        st.divider()
        st.subheader("⚙️ Configurazione in uso (data/config.json)")
        st.json(load_config(), expanded=False)

    # -- Elenco completo, modificabile --------------------------------------
    with tab_list:
        st.caption(
            "Tutte le schede del dataset, anche quelle fuori dalla selezione automatica. "
            "**Notorietà**, **verificato** e **allenamento** si modificano qui: le altre colonne "
            "sono il risultato del calcolo. Le modifiche restano nella tabella finché non premi "
            "*Salva*, e vengono scritte in `data/players.json` (con copia di sicurezza in `backup/`)."
        )

        rows = dataset_editor.list_players(blocked_ids=blocked)

        col1, col2, col3 = st.columns([2, 2, 2])
        search = col1.text_input("Cerca per nome o id", key="dataset_search")
        difficulty_filter = col2.multiselect(
            "Fascia", DIFFICULTY_ORDER, default=DIFFICULTY_ORDER, key="dataset_difficulty"
        )
        status_filter = col3.multiselect(
            "Stato",
            DATASET_STATUSES,
            default=[dataset_editor.STATUS_SELECTABLE],
            key="dataset_status",
            help="'selezionabile' è la scheda che può uscire come sfida del giorno. Le altre no, e la colonna dice perché.",
        )
        col4, col5 = st.columns([2, 4])
        popularity_filter = col4.multiselect(
            "Notorietà", list(dataset_editor.POPULARITY_VALUES), default=[], key="dataset_popularity"
        )
        sort_by = col5.radio(
            "Ordina per", ["punteggio", "nome", "notorietà"], horizontal=True, key="dataset_sort"
        )

        def _keep(row):
            if row["status"] not in status_filter:
                return False
            if row["difficulty"] and row["difficulty"] not in difficulty_filter:
                return False
            if popularity_filter and row["popularity"] not in popularity_filter:
                return False
            if search and search.lower() not in f"{row['id']} {row['full_name'] or ''}".lower():
                return False
            return True

        sort_key = {
            "punteggio": lambda r: (r["score"] is None, r["score"]),
            "nome": lambda r: (r["full_name"] or "").lower(),
            "notorietà": lambda r: (r["popularity"] or 0, (r["full_name"] or "").lower()),
        }[sort_by]
        visible = sorted([row for row in rows if _keep(row)], key=sort_key)

        st.caption(f"{len(visible)} schede su {len(rows)}")

        table = [
            {
                "id": row["id"],
                "nome": row["full_name"],
                "notorietà": row["popularity"],
                "fascia": row["difficulty"] or "—",
                "punteggio": row["score"],
                "da notorietà": row["from_popularity"],
                "dal percorso": row["from_path"],
                "verificato": row["verified"],
                "allenamento": row["practice_only"],
                "tappe": row["teams"],
                "nazionalità": row["nationality"],
                "stato": row["status"],
                "problemi": "; ".join(row["problems"]),
            }
            for row in visible
        ]

        if not table:
            st.info("📭 Nessuna scheda con questi filtri.")
        else:
            # La chiave cambia dopo ogni salvataggio: altrimenti Streamlit riapplicherebbe
            # le modifiche vecchie (le tiene per posizione di riga) alla tabella ricaricata.
            edited = st.data_editor(
                table,
                key=f"dataset_editor_{st.session_state.get('dataset_rev', 0)}",
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                disabled=[
                    "id", "nome", "fascia", "punteggio", "da notorietà", "dal percorso",
                    "tappe", "nazionalità", "stato", "problemi",
                ],
                column_config={
                    "notorietà": st.column_config.NumberColumn(
                        min_value=1,
                        max_value=5,
                        step=1,
                        format="%d",
                        help="1 = da aneddoto, 5 = leggenda universale. È la leva principale: "
                             "alzarla rende il giocatore più facile. Scala in docs/difficolta.md.",
                    ),
                    "punteggio": st.column_config.NumberColumn(format="%.2f"),
                    "da notorietà": st.column_config.NumberColumn(format="%.2f"),
                    "dal percorso": st.column_config.NumberColumn(format="%.2f"),
                    "verificato": st.column_config.CheckboxColumn(
                        help="Solo le schede verificate entrano nella selezione automatica."
                    ),
                    "allenamento": st.column_config.CheckboxColumn(
                        help="practice_only: la scheda esce solo in allenamento e nei round di gruppo, "
                             "mai come sfida del giorno (è la regola anti-spoiler)."
                    ),
                },
            )

            changes = collect_player_changes(table, edited)
            if not changes:
                st.caption("Nessuna modifica in sospeso.")
            else:
                try:
                    preview = dataset_editor.preview_player_changes(changes)
                except DatasetEditError as e:
                    preview = None
                    st.error(str(e))

                if preview:
                    st.subheader(
                        "✏️ "
                        + count_label(len(preview["changes"]), "modifica da salvare", "modifiche da salvare")
                    )
                    show_table(
                        [
                            {
                                "id": item["id"],
                                "campo": item["field"],
                                "prima": item["before"],
                                "dopo": item["after"],
                            }
                            for item in preview["changes"]
                        ]
                    )
                    if preview["moves"]:
                        st.subheader("🔀 Cambiano fascia")
                        show_table(
                            [
                                {
                                    "id": move["id"],
                                    "nome": move["full_name"],
                                    "da": move["before"],
                                    "a": move["after"],
                                }
                                for move in preview["moves"]
                            ]
                        )
                    else:
                        st.caption(
                            "Nessun cambio di fascia: il punteggio si muove ma resta dentro la stessa soglia."
                        )

                    if st.button("💾 Salva nel dataset", type="primary", key="save_dataset_rows"):
                        guarded(
                            lambda: save_player_changes(changes),
                            lambda result: (
                                count_label(len(result["changes"]), "modifica salvata", "modifiche salvate")
                                + " in data/players.json (copia di sicurezza: "
                                f"{os.path.basename(result['backup'])})."
                            ),
                        )

    # -- Scheda singola ------------------------------------------------------
    with tab_card:
        st.caption(
            "La stessa scheda vista da vicino: la scomposizione del punteggio dice **se a pesare "
            "è la notorietà o il percorso**, e la tabella delle tappe quale campionato costa quanto."
        )
        rows = dataset_editor.list_players(blocked_ids=blocked)
        options = {
            f"{row['full_name']} — {row['id']} ({row['difficulty'] or 'n/d'}, {row['status']})": row["id"]
            for row in sorted(rows, key=lambda r: (r["full_name"] or "").lower())
        }
        choice = st.selectbox(
            "Giocatore", list(options), index=None, placeholder="Cerca per nome o id…", key="dataset_card_pick"
        )
        player = get_player_by_id(options[choice]) if choice else None

        if player:
            explained = explain_difficulty(player)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Fascia", explained["difficulty"])
            col2.metric(
                "Punteggio",
                f"{explained['score_100']:g}/100",
                help=f"Grezzo {round(explained['score'], 2)}: la scala 0-100 lo divide per il massimo "
                "che la taratura in vigore può produrre.",
            )
            col3.metric("Notorietà", explained["popularity"])
            col4.metric("Tappe / paesi", f"{explained['teams']} / {explained['countries']}")

            show_table(
                [
                    {"addendo": "notorietà (5 - pop) × peso", "punti": round(explained["components"]["popularity"], 2)},
                    {"addendo": "campionati poco noti", "punti": round(explained["components"]["minor_leagues"], 2)},
                    {"addendo": "paesi oltre i primi due", "punti": round(explained["components"]["extra_countries"], 2)},
                    {"addendo": "squadre oltre le prime cinque", "punti": round(explained["components"]["extra_teams"], 2)},
                ]
            )

            st.subheader("Notorietà e flag")
            col1, col2, col3 = st.columns([2, 1, 1])
            new_popularity = col1.select_slider(
                "Notorietà",
                options=list(dataset_editor.POPULARITY_VALUES),
                value=player.get("popularity", 3),
                key=f"card_pop_{player['id']}",
                help="5 = leggenda universale, 3 = titolare solido (livello Jankto), 1 = da aneddoto (livello Constant).",
            )
            new_verified = col2.checkbox(
                "Verificato", value=bool(player.get("verified")), key=f"card_ver_{player['id']}"
            )
            new_practice = col3.checkbox(
                "Solo allenamento", value=bool(player.get("practice_only")), key=f"card_prac_{player['id']}"
            )

            st.subheader("Tappe di carriera")
            st.caption(
                "Il **campionato** è l'unica colonna modificabile: un nome fuori dalle liste di "
                "`config.json` pesa 1.0 invece di 0.5, ed è la seconda causa di una fascia sbagliata. "
                "Squadre, anni e statistiche si correggono nel file o con `scripts/import_players.py`."
            )
            career_table = [
                {
                    "#": stop["index"] + 1,
                    "squadra": stop["team"],
                    "paese": stop["country"],
                    "campionato": stop["league"],
                    "dal": str(stop["start_year"] or "—"),
                    "al": str(stop["end_year"] or "oggi"),
                    "peso": stop["weight"],
                    "livello": stop["tier"],
                }
                for stop in dataset_editor.career_with_weights(player)
            ]
            edited_career = st.data_editor(
                career_table,
                key=f"career_editor_{player['id']}_{st.session_state.get('dataset_rev', 0)}",
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                disabled=["#", "squadra", "paese", "dal", "al", "peso", "livello"],
                column_config={
                    "campionato": st.column_config.SelectboxColumn(
                        options=dataset_editor.known_league_names(), required=True
                    ),
                    "peso": st.column_config.NumberColumn(format="%.1f"),
                },
            )

            fields = {}
            if new_popularity != player.get("popularity"):
                fields["popularity"] = new_popularity
            if new_verified != bool(player.get("verified")):
                fields["verified"] = new_verified
            if new_practice != bool(player.get("practice_only")):
                fields["practice_only"] = new_practice

            career_fields = {
                index: row["campionato"]
                for index, (before, row) in enumerate(zip(career_table, as_records(edited_career)))
                if row["campionato"] != before["campionato"]
            }

            if fields or career_fields:
                changes = {player["id"]: fields} if fields else {}
                career_changes = {player["id"]: career_fields} if career_fields else {}
                try:
                    preview = dataset_editor.preview_player_changes(changes, career_changes)
                except DatasetEditError as e:
                    preview = None
                    st.error(str(e))
                if preview:
                    for move in preview["moves"]:
                        st.info(f"Con questa modifica passa da **{move['before']}** a **{move['after']}**.")
                    if st.button("💾 Salva la scheda", type="primary", key=f"save_card_{player['id']}"):
                        guarded(
                            lambda: save_player_changes(changes, career_changes),
                            lambda result: (
                                f"Scheda '{player['id']}' aggiornata "
                                f"(copia di sicurezza: {os.path.basename(result['backup'])})."
                            ),
                        )
            else:
                st.caption("Nessuna modifica in sospeso.")

            with st.expander("Scheda completa (JSON)"):
                st.json(player, expanded=False)

    # -- Taratura globale ----------------------------------------------------
    with tab_tuning:
        st.caption(
            "Pesi e soglie della formula, cioè `difficulty_weights` e `difficulty_thresholds` di "
            "`data/config.json`. **Non si toccano per sistemare un giocatore**: si sistema uno e se "
            "ne rompono venti. Si toccano quando lo stesso errore torna su molte schede, guardando "
            "la ridistribuzione qui sotto — le quattro fasce devono restare grosso modo bilanciate, "
            "perché la sfida del giorno le pesca a turno."
        )
        current = dataset_editor.difficulty_settings()
        cutoffs = band_cutoffs_100()
        st.caption(
            f"Sulla scala 0-100 le soglie in vigore valgono: easy < {cutoffs['easy']:g}, "
            f"medium < {cutoffs['medium']:g}, hard < {cutoffs['hard']:g}, oltre impossible (la fascia "
            "*Extreme* di #21). Le fasce si decidono sempre sul punteggio grezzo qui sotto."
        )

        st.subheader("Soglie")
        col1, col2, col3 = st.columns(3)
        thresholds = {
            "easy": col1.number_input(
                "easy sotto", value=current["thresholds"]["easy"], step=0.5, key="thr_easy"
            ),
            "medium": col2.number_input(
                "medium sotto", value=current["thresholds"]["medium"], step=0.5, key="thr_medium"
            ),
            "hard": col3.number_input(
                "hard sotto (oltre: impossible)", value=current["thresholds"]["hard"], step=0.5, key="thr_hard"
            ),
        }

        st.subheader("Pesi")
        col1, col2, col3, col4 = st.columns(4)
        weights = {
            "popularity": col1.number_input(
                "notorietà", value=current["weights"]["popularity"], step=0.5, min_value=0.0, key="w_pop"
            ),
            "minor_leagues": col2.number_input(
                "campionati poco noti", value=current["weights"]["minor_leagues"], step=0.5, min_value=0.0, key="w_min"
            ),
            "extra_countries": col3.number_input(
                "paesi in più", value=current["weights"]["extra_countries"], step=0.1, min_value=0.0, key="w_cnt"
            ),
            "extra_teams": col4.number_input(
                "squadre in più", value=current["weights"]["extra_teams"], step=0.1, min_value=0.0, key="w_team"
            ),
        }

        try:
            preview = dataset_editor.preview_difficulty_settings(thresholds, weights, blocked_ids=blocked)
        except DatasetEditError as e:
            preview = None
            st.error(str(e))

        if preview:
            st.subheader("Distribuzione dei selezionabili")
            show_table(
                [
                    {
                        "fascia": level,
                        "ora": preview["before"][level],
                        "dopo": preview["after"][level],
                        "differenza": preview["after"][level] - preview["before"][level],
                    }
                    for level in DIFFICULTY_ORDER
                ]
            )
            if not preview["moves"]:
                st.caption("Con questi valori nessuna scheda cambia fascia.")
            else:
                st.subheader(
                    "🔀 " + count_label(len(preview["moves"]), "scheda cambia fascia", "schede cambiano fascia")
                )
                show_table(
                    [
                        {
                            "id": move["id"],
                            "nome": move["full_name"],
                            "punteggio": move["score"],
                            "da": move["before"],
                            "a": move["after"],
                        }
                        for move in preview["moves"]
                    ]
                )

                st.warning(
                    "La taratura vale per tutto il dataset e cambia anche i punti delle sfide già "
                    "in buffer (la difficoltà viene ricalcolata alla lettura). Controlla le prossime "
                    "sfide nella sezione *Sfide giornaliere* dopo il salvataggio."
                )
                if confirm_button("💾 Salva la taratura", "difficulty_settings", "Cambia le fasce di tutto il dataset."):
                    guarded(
                        lambda: save_difficulty_settings(thresholds, weights),
                        lambda result: (
                            "Taratura salvata in data/config.json "
                            f"(copia di sicurezza: {os.path.basename(result['backup'])})."
                        ),
                    )

    # -- Prevista vs osservata ---------------------------------------------------
    with tab_calibration:
        _render_calibration(today)


def _render_calibration(today):
    st.caption(
        "Com'è andata davvero ogni giornata chiusa, accanto a quanto la formula la prevedeva difficile. "
        "Non modifica niente: dice **se** la taratura ordina bene le sfide e **dove** sbaglia sempre "
        "allo stesso modo. Uno scarto isolato è rumore; uno che si ripete su un intero gruppo "
        "(tutte le carriere da 8+ squadre, tutti i ritirati da 15 anni) è un peso da rivedere nella "
        "scheda *Taratura difficoltà*. Procedura in `docs/difficolta.md`, sezione 6."
    )
    days = st.slider("Giornate chiuse da analizzare", 30, 365, 120, step=15, key="calibration_days")
    try:
        report = cached_difficulty_calibration(days, today)
    except Exception as e:
        st.error(f"Errore leggendo le sfide: {e}")
        return

    settings = report["settings"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Giornate", report["days"])
    col2.metric(
        "Confrontabili",
        report["comparable_days"],
        help=f"Con almeno {settings['min_players']} partecipanti (difficulty_calibration.min_players).",
    )
    col3.metric(
        "Correlazione di rango",
        "—" if report["spearman"] is None else f"{report['spearman']:+.2f}",
        help="Spearman fra punteggio previsto e osservato: 1 = la formula ordina le giornate "
        "esattamente come i giocatori, 0 = nessuna relazione. Servono almeno 3 giornate confrontabili.",
    )
    col4.metric("Previsioni fotografate", f"{report['snapshot_days']}/{report['days']}")

    if not report["comparable_days"]:
        st.info("📭 Nessuna giornata con abbastanza partecipanti nella finestra scelta.")
        return

    if report["snapshot_days"] < report["days"]:
        st.caption(
            "Le giornate senza previsione fotografata (generate prima di #21) usano la previsione "
            "**ricalcolata** con scheda e taratura di oggi: confrontabili, ma non identiche a quelle di allora."
        )
    other_models = {model: n for model, n in report["models"].items() if model != report["current_model"]}
    if other_models:
        st.warning(
            "Nella finestra ci sono previsioni fatte con una taratura diversa da quella in vigore "
            f"({report['current_model']}): "
            + ", ".join(f"{model} × {n}" for model, n in sorted(other_models.items()))
            + ". Confronta con cautela i periodi a cavallo di una modifica."
        )

    st.subheader("Per fascia prevista")
    if report["bands_in_order"] is False:
        st.warning("Le fasce non salgono in ordine: una fascia più alta è stata in media più facile di una più bassa.")
    show_table(
        [
            {
                "fascia": entry["band"],
                "giornate": entry["days"],
                "indovinata da (%)": entry["completion_rate"],
                "tentativi medi": entry["avg_attempts"],
                "punteggio osservato": entry["observed_score"],
            }
            for entry in report["by_band"]
        ]
    )

    st.subheader("Scarto medio per dimensione")
    st.caption(
        "Scarto = percentile osservato − percentile previsto. **Positivo**: il gruppo è stato più difficile "
        f"del previsto; **negativo**: più facile. Una giornata è fuori previsione oltre ±{settings['mismatch_tolerance']:g}."
    )
    columns = st.columns(2)
    for index, (signal, groups) in enumerate(report["by_signal"].items()):
        with columns[index % 2]:
            st.markdown(f"**{signal}**")
            show_table(
                [{"gruppo": entry["group"], "giornate": entry["days"], "scarto medio": entry["avg_delta"]}
                 for entry in groups]
            )

    st.subheader("Giornate fuori previsione")
    show_table(
        [_calibration_row(row) for row in report["mismatches"]],
        "Nessuna giornata oltre la tolleranza.",
    )
    with st.expander("Tutte le giornate"):
        show_table([_calibration_row(row) for row in report["rows"]])


def _calibration_row(row):
    predicted, observed = row["predicted"] or {}, row["observed"]
    return {
        "giorno": row["day"],
        "giocatore": row["player_name"] or row["player_id"],
        "fascia giocata": row["played_band"],
        "prevista": predicted.get("band"),
        "previsto /100": predicted.get("score"),
        "origine previsione": predicted.get("source"),
        "partecipanti": observed["players"],
        "indovinata da (%)": observed["completion_rate"],
        "tentativi medi": observed["avg_attempts"],
        "osservato /100": observed["score"],
        "scarto": row["delta"],
        "esito": row["verdict"] or "—",
    }
