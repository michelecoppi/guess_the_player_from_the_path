"""Traduzioni dei messaggi rivolti agli utenti (IT/ES/EN).

Solo i comandi utente sono tradotti (start, help, guess, show, stats, notify, top, events,
language, i messaggi automatici del job di mezzanotte). I comandi /admin_* restano solo in
italiano: li usa solo chi gestisce il bot.

La lingua di un utente si risolve cosi':
1. se ha gia' un account con "language" salvato, si usa quello (impostabile con /language);
2. altrimenti si mappa il `language_code` che Telegram manda con ogni update (lingua del
   client dell'utente) su IT/ES/EN, con EN come default per lingue non supportate.
"""

SUPPORTED_LANGUAGES = ("it", "es", "en")
DEFAULT_LANGUAGE = "it"

LANGUAGE_NAMES = {
    "it": "🇮🇹 Italiano",
    "es": "🇪🇸 Español",
    "en": "🇬🇧 English",
}


def resolve_language(language_code):
    """Mappa il `language_code` di Telegram (es. 'it', 'es-MX', 'pt-BR') su una lingua
    supportata. Nessun codice o lingua non supportata -> inglese, l'inglese e' la lingua
    "cuscinetto" per chi non e' ne' italiano ne' spagnolo."""
    if not language_code:
        return DEFAULT_LANGUAGE
    code = language_code.lower().split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else "en"


def t(lang, key, **kwargs):
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    template = TRANSLATIONS.get(lang, {}).get(key)
    if template is None:
        template = TRANSLATIONS[DEFAULT_LANGUAGE][key]
    return template.format(**kwargs) if kwargs else template


def content_text(entry, field, lang, default=""):
    """Un testo che sta nel **contenuto** e non fra le traduzioni: nome e descrizione di un
    evento (data/event_templates.json, poi copiati sul documento dell'evento).

    Stanno li' e non in TRANSLATIONS perche' sono contenuto come le schede dei calciatori:
    chi aggiunge un evento scrive un blocco solo, in un file solo. Qui si sceglie la lingua,
    con l'italiano di `field` come ripiego - cosi' gli eventi generati prima che le
    traduzioni esistessero continuano a mostrare qualcosa invece di una riga vuota."""
    translated = (entry or {}).get(f"{field}_i18n") or {}
    return translated.get(lang) or (entry or {}).get(field) or default


DIFFICULTY_LABELS = {
    "it": {"easy": "Facile", "medium": "Media", "hard": "Difficile", "impossible": "Impossibile", "unknown": "Sconosciuta"},
    "es": {"easy": "Fácil", "medium": "Media", "hard": "Difícil", "impossible": "Imposible", "unknown": "Desconocida"},
    "en": {"easy": "Easy", "medium": "Medium", "hard": "Hard", "impossible": "Impossible", "unknown": "Unknown"},
}


def difficulty_label(lang, difficulty):
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    return DIFFICULTY_LABELS.get(lang, DIFFICULTY_LABELS[DEFAULT_LANGUAGE]).get(difficulty or "unknown", DIFFICULTY_LABELS[lang]["unknown"])


_ENGLISH_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

MONTH_NAMES = {
    "it": ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
           "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"],
    "es": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
           "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
    "en": _ENGLISH_MONTHS,
}


def month_label(lang, english_month_name):
    """`english_month_name` e' quello che produce `datetime.strftime('%B')` (locale di
    sistema, di norma inglese): lo traduciamo a mano invece di dipendere dalla locale del
    processo, che sui container non e' garantita."""
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    try:
        index = _ENGLISH_MONTHS.index(english_month_name)
    except ValueError:
        return english_month_name
    return MONTH_NAMES.get(lang, _ENGLISH_MONTHS)[index]


TRANSLATIONS = {
    "it": {
        "common.private_only": "❗ Questo comando può essere usato solo in chat privata.",
        "common.no_challenge": "❗ Non c'è ancora una sfida giornaliera disponibile.",

        "start.welcome_new": "Benvenuto, {name}! Il tuo account è stato creato. fai /help per vedere la lista dei comandi disponibili.",
        "start.welcome_back": "Ciao di nuovo, {name}!",

        "help.message": (
            "🛠️ Come si gioca:\n\n"
            "Ogni giorno un percorso di carriera da indovinare. In chat privata ti basta scrivere il nome del calciatore: non serve nessun comando, e hai 3 tentativi.\n\n"
            "📋 Comandi:\n"
            "/menu - Apre il menu con tutto quello che si può fare.\n"
            "/show - Mostra la sfida di oggi.\n"
            "/solution - Chi era il calciatore di una giornata gia' chiusa.\n"
            "/guess <risposta> - Il vecchio modo di rispondere, se ci sei affezionato.\n"
            "/stats - Le tue statistiche, la striscia e i trofei.\n"
            "/top - La classifica generale e quella del mese.\n"
            "/events - Il centro eventi.\n"
            "/archive - Rigioca le sfide dei giorni scorsi (senza punti).\n"
            "/training - Sfide passate a raffica, senza punti.\n"
            "/round - In un gruppo: un round per tutti, vince chi risponde per primo.\n"
            "/standings - In un gruppo: la classifica di quel gruppo.\n"
            "/today - Esci da archivio o allenamento e torna alla sfida di oggi.\n"
            "/league - Le tue leghe private; /league_create e /league_join per farne una o entrarci.\n"
            "/notify - Attiva o disattiva le notifiche.\n"
            "/language - Cambia la lingua del bot.\n"
            "/legend - Come si legge l'immagine del percorso.\n"
        ),

        "language.prompt": "🌐 Scegli la lingua del bot:",
        "language.confirm": "✅ Lingua impostata su Italiano.",

        "guess.missing_answer": "❗ Devi scrivere anche il nome del calciatore dopo /guess!",
        "guess.wrong_last": (
            "❌ Risposta sbagliata: tentativi finiti per oggi.\n"
            "🔒 Chi era te lo dico a mezzanotte, quando la giornata si chiude: da quel momento "
            "lo trovi anche con /solution."
        ),
        # "Hai 1 tentativi rimasti" era sbagliato: la forma con i due punti regge sia il
        # singolare sia il plurale, in tutte e tre le lingue.
        "guess.wrong_remaining": "❌ Risposta sbagliata, riprova! Tentativi rimasti: {attempts_left}.",
        "guess.correct": "✅ Corretto! Hai guadagnato {points} punti.\n{bonus_message}",
        "guess.bonus": "💎 Bonus: +{bonus} punto perchè sei il primo ad indovinare!",
        "guess.error.not_registered": "❗ Devi registrarti prima di giocare! Usa /start.",
        "guess.error.already_guessed": "✅ Hai già indovinato oggi! Torna domani per una nuova sfida.",
        "guess.error.no_attempts": "❌ Hai esaurito i tentativi per oggi! Riprova domani.",
        "guess.error.default": "❗ Non è stato possibile registrare il tentativo, riprova.",

        "show.bonus_info": "💎 Bonus: +1 punto se sei il primo a rispondere!",
        "show.caption": (
            "🎯 Difficoltà: {difficulty}\n"
            "🏆 Punti: {points}\n"
            "{bonus_info}\n\n"
            "✍️ Scrivi qui il nome del calciatore: non serve nessun comando.\n"
            "🔢 Hai {attempts} tentativi. Dopo il primo sbagliato puoi chiedere un indizio."
        ),

        "stats.not_registered": "❗ Non sei registrato! Usa /start per registrarti.",
        "stats.message": (
            "📊 Le tue statistiche:\n\n"
            "👤 Nome: {name}\n"
            "🏆 Punti totali: {points_totali}\n"
            "📅 Punti mensili: {monthly_points}\n"
            "🧠 Indovinati: {players_guessed}\n"
            "⚡ Bonus primo indovino ottenuti: {bonus_first_guessed}"
        ),
        "stats.button_trophies": "🎖️ I miei trofei",
        "stats.no_trophies": "😕 Nessun trofeo guadagnato ancora.",
        "stats.button_back": "🔙 Torna alle stats",
        "stats.trophies_title": "🎖️ *I tuoi trofei:*\n\n",
        "stats.trophy_monthly": "{medal} *Classifica Mensile* ({month} {year}, Stagione {season_num}) - Posizione: {pos}\n",
        "stats.trophy_event": "{medal} *{event}* (Settimana {week}, {year}) - Posizione: {pos}\n",
        "stats.nav_back": "⬅️ Indietro",
        "stats.nav_forward": "➡️ Avanti",

        "notify.not_registered": "❗ Devi registrarti prima con /start.",
        "notify.private_only": "❗ Usa questo comando in chat privata.",
        "notify.active_prompt": "🔔 Le notifiche sono attive. Vuoi disattivarle?",
        "notify.button_disable": "❌ Disattiva notifiche",
        "notify.inactive_prompt": "🔕 Le notifiche non sono attive. Vuoi attivarle?",
        "notify.button_enable": "✅ Attiva notifiche",
        "notify.enabled_confirm": "✅ Notifiche attivate! Riceverai un messaggio ogni giorno.",
        "notify.disabled_confirm": "🔕 Notifiche disattivate. Potrai riattivarle con /notify.",

        "top.title_global": "🏆 <b>Top 10 generale</b> 🏆",
        "top.title_monthly": "📆 <b>Top 10 mensile</b> 📆",
        "top.points_suffix": "punti",
        "top.you_tag": " <b>[TU]</b>",
        "top.your_position": "\n📍 <b>La tua posizione:</b> {position}° - {score} punti",
        "top.button_monthly": "📆 Classifica Mensile",
        "top.button_global": "🌐 Classifica Generale",

        "events.no_active": "❗ Non ci sono eventi attivi al momento.",
        "events.no_active_nav": "❗ Nessun evento attivo al momento.",
        "events.no_daily_challenge": "⚠️ Nessuna sfida disponibile per oggi.",
        "events.max_answers": "⚠️ Puoi inserire al massimo {max_answers} squadre separate da virgola.",
        "events.wrong": "❌ Risposta sbagliata. Tentativi usati: {used}/{max_attempts}.",
        "events.wrong_career_extra": "\n Risposte corrette trovate: {matched}/{total}",
        "events.correct": "✅ Corretto! Hai guadagnato {points} punti! {bonus_tag}",
        "events.bonus_tag": "(Bonus 1°)",
        "events.error.already_guessed": "❌ Hai già indovinato oggi!",
        "events.error.no_attempts": "❌ Hai già usato tutti i {max_attempts} tentativi di oggi.",
        "events.error.default": "❗ Non è stato possibile registrare il tentativo, riprova.",
        "events.no_player_today": "📭 Nessun giocatore disponibile per oggi.",
        "events.unnamed": "Evento senza nome",
        "events.no_end_date": "Data non disponibile",
        "events.button_home": "🏠 Home",
        "events.button_player": "🎮 Giocatore",
        "events.button_leaderboard": "📊 Classifica",
        "events.no_participants": "📊 <b>Classifica dell'evento</b>:\nNessun partecipante al momento.",
        "events.leaderboard_title": "📊 <b>Classifica dell'evento</b>:\n\n",
        "events.leaderboard_footer": "\n🏆 Al termine dell'evento, i primi 3 otterranno un trofeo esclusivo!",
        "events.unknown_user": "Utente sconosciuto",
        "events.gameplay.career": "🎮 <b>Giocatore</b>: indovina le squadre in cui ha giocato il calciatore",
        "events.gameplay.path": "🎮 <b>Giocatore</b>: mostra il calciatore del giorno da indovinare",
        "events.gameplay.father_son": "🎮 <b>Giocatore</b>: indovina la coppia padre/figlio dall'immagine",
        "events.gameplay.transfer_guess": "🎮 <b>Giocatore</b>: indovina il calciatore dal trasferimento mostrato",
        "events.gameplay.default": "🎮 <b>Giocatore</b>: segui le istruzioni della sfida del giorno",
        "events.home_message": (
            "🎉 <b>{name}</b>\n\n"
            "{description}\n\n"
            "📅 L'evento termina il <b>{end_date}</b>.\n"
            "I primi 3 classificati riceveranno un <b>trofeo speciale</b> 🏆!\n\n"
            "📌 Usa i pulsanti qui sotto per navigare:\n"
            "- 🏠 <b>Home</b>: questa schermata\n"
            "- {gameplay_line}\n"
            "- 📊 <b>Classifica</b>: guarda la top 3 dell'evento in tempo reale"
        ),
        "events.bonus_available": "⚡ Il primo che indovina riceverà 1 punto bonus!",
        "events.bonus_taken": "✅ Il bonus è già stato assegnato oggi.",
        "events.player_message.path": (
            "🎮 <b>Giocatore del giorno</b>\n\n"
            "👀 Indovina chi è questo calciatore!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Scrivi il nome qui in privato: hai {attempts} tentativi.\n"
            "Con /today torni alla sfida di oggi."
        ),
        "events.player_message.career": (
            "🧠 <b>Modalità carriera</b>\n\n"
            "👤 Indovina almeno <b>{min_correct}</b> delle squadre in cui ha giocato {player_name}!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Scrivi qui le squadre separate da virgole, es: Roma, Manchester United, Toronto FC\n"
            "(massimo {max_answers} a tentativo). Hai {attempts} tentativi; con /today torni alla sfida di oggi."
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Modalità padre-figlio</b>\n\n"
            "👤 Indovina la coppia padre/figlio dall'immagine!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Scrivi qui il nome della coppia: hai {attempts} tentativi.\n"
            "Con /today torni alla sfida di oggi."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Modalità trasferimento</b>\n\n"
            "👤 Indovina il calciatore dal trasferimento mostrato!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Scrivi il nome qui in privato: hai {attempts} tentativi.\n"
            "Con /today torni alla sfida di oggi."
        ),
        "events.player_message.default": (
            "🎮 <b>Sfida del giorno</b>\n\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Scrivi qui la tua risposta: hai {attempts} tentativi.\n"
            "Con /today torni alla sfida di oggi."
        ),

        "job.congrats": "🎉 Complimenti per aver indovinato il calciatore {player} ieri!\nÈ disponibile una nuova sfida giornaliera!\n👉 Usa /show e prova a essere il primo!",
        "job.missed": "⚠️ Non hai indovinato il calciatore {player} ieri.\n📢 È disponibile una nuova sfida giornaliera!\n👉 Usa /show per indovinare il calciatore misterioso!",
        "job.event_mention": "\n\n🎊 Inoltre è attivo un evento speciale: {event_name}\n🏆 Partecipa usando /events e scala la classifica dell'evento!",
        "job.unknown_event": "Evento Sconosciuto",
        "job.player_fallback": "di ieri",
        "job.feedback_line": "\n\nSe hai idee per migliorare il bot o una funzione nuova che vorresti vedere, manda un messaggio a @gabbente con la tua proposta!",
        "job.monthly_results_title": "🏆 Risultati della stagione mensile {month} {year}:\n",
        "job.monthly_winner_line": "{position}° - {username} ({points} punti)\n",

        # --- testo dentro le immagini generate (services/path_image.py) ---
        "image.path_title": "Percorso misterioso",
        "image.path_subtitle": "{stops} tappe",
        "image.transfer_title": "Trasferimento misterioso",
        "image.transfer_subtitle": "Chi si e' trasferito qui?",
        "image.palmares_title": "Palmares",
        "image.palmares_subtitle": "{count} trofei conquistati",
        "image.badge_event": "EVENTO",
        "image.badge_player": "GIOCATORE DEL GIORNO",
        "image.badge_leaderboard": "CLASSIFICA",

        # --- menu principale e bottoni ---
        "menu.title": "⚽ <b>Guess the Player</b>\nScegli cosa fare:",
        "menu.play": "🎯 Sfida di oggi",
        "menu.stats": "📊 Statistiche",
        "menu.top": "🏆 Classifica",
        "menu.events": "🎊 Eventi",
        "menu.archive": "🗂 Archivio",
        "menu.training": "🏋️ Allenamento",
        "menu.leagues": "👥 Leghe",
        "menu.notify": "🔔 Notifiche",
        "menu.language": "🌐 Lingua",
        "menu.help": "❓ Aiuto",
        "menu.app": "📱 Apri l'app",
        "menu.back": "⬅️ Menu",

        # --- descrizioni dei comandi nel menu di Telegram (set_my_commands) ---
        "cmd.start": "Registrati e apri il menu",
        "cmd.show": "La sfida di oggi",
        "cmd.stats": "Le tue statistiche",
        "cmd.top": "Classifica generale",
        "cmd.events": "Centro eventi",
        "cmd.archive": "Rigioca le sfide passate",
        "cmd.training": "Sfide passate a raffica",
        "cmd.league": "Le tue leghe private",
        "cmd.notify": "Attiva o disattiva le notifiche",
        "cmd.language": "Cambia lingua",
        "cmd.help": "Come si gioca",

        # --- risposta libera (senza /guess) ---
        "guess.free_text_hint": "💬 Scrivimi il nome del calciatore per tentare la sfida di oggi, oppure usa /show per rivederla.",
        "guess.typo_note": "\n✍️ Accettata anche se avevi scritto «{written}».",

        # --- striscia, condivisione e archivio ---
        "guess.streak": "\n🔥 Striscia: {streak} giorni di fila.",
        "guess.streak_bonus": "\n🔥 Striscia di {streak} giorni: +{bonus} punti bonus.",
        "stats.streak_line": "🔥 Striscia: {streak} (record: {best})\n🗂 Sfide recuperate: {archive_solved}",
        "share.button": "📤 Condividi il risultato",
        "share.title": "⚽ Guess the Player #{number}",
        "share.streak": "🔥 {streak}",
        "share.archive_title": "🗄 Guess the Player #{number} (archivio)",

        "feedback.header": "🔎 Rispetto a {name}:",
        "feedback.nationality_same": "🌍 Nazionalità: stessa",
        "feedback.nationality_diff": "🌍 Nazionalità: diversa",
        "feedback.position_same": "🎽 Ruolo: stesso",
        "feedback.position_diff": "🎽 Ruolo: diverso",
        "feedback.birth_same": "🎂 Stesso anno di nascita ({year})",
        "feedback.birth_before": "⬆️ Più vecchio: nato prima del {year}",
        "feedback.birth_after": "⬇️ Più giovane: nato dopo il {year}",

        "training.button_next": "🎲 Un'altra",
        "training.button_reveal": "👀 Rivela",
        "training.private_only": "L'allenamento si fa in chat privata con me.",
        "training.not_registered": "❗ Devi registrarti con /start prima di allenarti.",
        "training.empty": "🏋️ Non ci sono ancora sfide passate da riproporre: torna qui fra qualche giorno.",
        "training.opened": "🏋️ <b>Allenamento</b>: scrivi il nome del calciatore.\nNon vale punti e non tocca la sfida di oggi. Hai {attempts} tentativi.\nTorna alla sfida di oggi con /today.",
        "training.correct": "✅ Preso in {attempts} tentativi!\nNessun punto: è allenamento.",
        "training.wrong": "❌ No. Tentativi rimasti: {attempts_left}.",
        "training.wrong_last": "❌ Tentativi finiti: era {answer}.",
        "training.revealed": "👀 Era {answer}.",
        "training.not_open": "Non hai nessuna sfida di allenamento aperta: /training per cominciarne una.",
        "training.gone": "❗ Quella sfida di allenamento non è più disponibile: /training per un'altra.",
        "training.exited": "👋 Allenamento chiuso: /show per la sfida di oggi.",

        "group.private_hint": "👥 Questa è una modalità da gruppo: aggiungimi a un gruppo e scrivi /round. Qui in privato c'è /training.",
        "group.empty": "👥 Non ci sono ancora sfide passate da riproporre in un round.",
        "group.round_opened": "👥 <b>Round #{number}</b> — {difficulty} ({points} punti)\nChi risponde per primo vince. Si risponde con <code>/guess nome</code>, {attempts} tentativi a testa.\nI punti restano in questo gruppo.",
        "group.no_round": "👥 Nessun round aperto: scrivi /round per cominciarne uno.",
        "group.usage": "👥 Si risponde così: <code>/guess Maldini</code>",
        "group.already_solved": "👥 Questo round l'ha già vinto {winner}. /round per il prossimo.",
        "group.no_attempts": "❌ {name}, hai finito i tentativi per questo round.",
        "group.wrong": "❌ {name}: no. Tentativi rimasti: {attempts_left}.",
        "group.correct": "🏆 <b>{name}</b> vince il round #{number}: +{points} punti nella classifica del gruppo.\n/round per il prossimo, /standings per vedere come siete messi.",
        "group.standings_title": "👥 <b>Classifica del gruppo</b>\n(vale solo qui: la classifica generale è /top)\n\n",
        "group.standings_line": "{medal} {name} — {points} punti ({rounds} round)\n",
        "group.standings_empty": "👥 Nessun round vinto qui dentro: /round per cominciare.",
        "group.button_private": "🎯 Gioca la sfida di oggi",
        "group.button_new_round": "🔁 Un altro round",

        "legend.button": "ℹ️ Come si legge",
        "legend.text": (
            "ℹ️ <b>Come si legge il percorso</b>\n\n"
            "Ogni riga è una tappa, dall'alto in basso in ordine di tempo.\n\n"
            "• <b>2016 – 2019</b>: gli anni in quella squadra. <b>2016 – …</b> vuol dire che è ancora lì.\n"
            "• <b>→ 2016 – 2017</b>: la freccia, insieme alla barretta tratteggiata a sinistra, è un <b>prestito</b>.\n"
            "• <b>33 (22)</b>: presenze e, fra parentesi, gol di <b>campionato</b> (la convenzione di Wikipedia). Per i portieri ci sono le sole presenze.\n"
            "• La <b>barra</b> al posto dei numeri compare quando presenze e gol non li abbiamo: è lunga quanto la tappa.\n"
            "• Sotto il nome della squadra: <b>campionato · paese</b>.\n"
            "• In alto a destra: la <b>difficoltà</b> della sfida.\n\n"
            "Nell'immagine non c'è nessuna parola: la stessa figura va a chi gioca in italiano, spagnolo e inglese."
        ),
        "archive.title": "🗂 <b>Archivio</b>\nRigioca le sfide dei giorni scorsi: non danno punti, valgono per il gusto di riuscirci.\nScegli un giorno:",
        "archive.empty": "🗂 Non c'è ancora nessuna sfida in archivio.",
        "archive.not_registered": "❗ Devi registrarti con /start prima di usare l'archivio.",
        "archive.opened": "🗂 Sfida del {date}. Scrivi il nome del calciatore: questa non assegna punti.\nTorna alla sfida di oggi con /today.",
        "archive.missing_day": "❗ Quella sfida non è più disponibile.",
        "archive.correct": "✅ Preso! Sfida del {date} recuperata in {attempts} tentativi.\nScegli un altro giorno con /archive o torna a oggi con /today.",
        "archive.wrong": "❌ No. Tentativi rimasti per questa sfida: {attempts_left}.",
        "archive.wrong_last": "❌ Tentativi finiti: era {answer}.\nScegli un altro giorno con /archive o torna a oggi con /today.",
        "archive.already_solved": "✅ Questa sfida l'avevi già recuperata. Scegline un'altra con /archive.",
        "archive.no_attempts": "❌ Hai finito i tentativi su questa sfida. Scegline un'altra con /archive.",
        "archive.exited": "👋 Torniamo alla sfida di oggi: /show per rivederla.",
        "archive.not_in_archive": "Non stai giocando nessuna sfida d'archivio. Aprine una con /archive.",
        "archive.button_today": "🎯 Torna a oggi",
        "cmd.today": "Torna alla sfida di oggi",

        # --- leghe private ---
        "league.intro": "👥 <b>Le tue leghe</b>\nUna lega è una classifica privata fra amici: si contano i punti che fai da quando ne fai parte.\n\nCrea la tua con <code>/league_create Nome della lega</code> o entra in una con <code>/league_join CODICE</code>.",
        "league.none": "👥 Non fai parte di nessuna lega.\n\nCreane una con <code>/league_create Nome della lega</code>, oppure entra in una esistente con <code>/league_join CODICE</code>.",
        "league.usage_create": "Uso: <code>/league_create Nome della lega</code>",
        "league.usage_join": "Uso: <code>/league_join CODICE</code>",
        "league.usage_leave": "Uso: <code>/league_leave CODICE</code>",
        "league.name_too_long": "❗ Il nome della lega può essere lungo al massimo {max} caratteri.",
        "league.created": "✅ Lega <b>{name}</b> creata!\nCodice: <code>{code}</code>\n\nInvita chi vuoi con questo link:\n{link}",
        "league.invite": "🔗 Invita nella lega <b>{name}</b>:\n{link}\n\nOppure fagli usare <code>/league_join {code}</code>.",
        "league.joined": "✅ Sei entrato nella lega <b>{name}</b>! Vedi la classifica con /league.",
        "league.already_member": "Fai già parte di questa lega. Vedi la classifica con /league.",
        "league.not_found": "❗ Nessuna lega con il codice <code>{code}</code>.",
        "league.full": "❗ Questa lega è piena ({max} membri).",
        "league.limit_reached": "❗ Puoi far parte di al massimo {max} leghe. Escine da una con <code>/league_leave CODICE</code>.",
        "league.left": "👋 Hai lasciato la lega <b>{name}</b>.",
        "league.not_member": "❗ Non fai parte di questa lega.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCodice: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "Ancora nessun punto in questa lega: il primo che indovina apre la classifica.",
        "league.not_registered": "❗ Devi registrarti con /start prima di usare le leghe.",
        "league.button_invite": "🔗 Invita",
        "cmd.league_create": "Crea una lega privata",
        "cmd.league_join": "Entra in una lega con il codice",

        # Soluzione di una giornata gia' chiusa (/solution)
        "solution.usage": (
            "🗝 <b>Soluzione</b>\n"
            "/solution — la giornata di ieri.\n"
            "/solution 06/09/26 — una giornata precisa, se e' gia' chiusa."
        ),
        "solution.not_registered": "❗ Devi registrarti con /start prima.",
        "solution.bad_date": "❗ Non ho capito la data: scrivila come 06/09/26, oppure usa /solution da solo per la giornata di ieri.",
        "solution.still_open": "🔒 Quella giornata è ancora aperta: la soluzione arriva a mezzanotte, quando si chiude. Intanto giocala con /show.",
        "solution.missing": "❗ Per il {date} non risulta nessuna sfida.",
        "solution.caption": (
            "🗝 <b>Sfida del {date}</b> (#{number})\n\n"
            "👤 Era <b>{answer}</b>.\n"
            "🎯 {difficulty} · {points} punti\n"
            "{rate_line}"
        ),
        "solution.rate": "📊 L'ha indovinato il {percent}% di chi ci ha provato ({solved} su {players}).",
        "solution.rate_unknown": "📊 Troppo pochi tentativi per dire quanti l'hanno indovinato.",
        "solution.button_archive": "🗂 Le altre giornate",

        # Indizi sulla sfida del giorno
        "hint.button": "💡 Indizio (-1 punto)",
        "hint.header": "💡 <b>Indizio {index} di {total}</b>",
        "hint.nationality": "🌍 Nazionalità: <b>{value}</b>",
        "hint.position": "🧭 Ruolo: <b>{value}</b>",
        "hint.cost": "\n\n➖ Ti costa 1 punto: se indovini adesso ne prendi {points} invece di {full_points}.",
        "hint.no_more": "💡 Hai già usato tutti gli indizi di oggi ({max_hints}).",
        "hint.needs_attempt": "💡 Gli indizi si sbloccano dopo un tentativo sbagliato: prova un nome.",
        "hint.already_guessed": "✅ Hai già indovinato oggi: gli indizi non ti servono più.",
        "hint.no_attempts": "❌ Tentativi finiti: un indizio non ti servirebbe più.",
        "hint.unavailable": "💡 Per questa sfida non ho indizi da darti.",
        "hint.not_registered": "❗ Devi registrarti con /start prima.",

        # Notifiche attivate dal messaggio di sconfitta
        "guess.button_notify": "🔔 Avvisami a mezzanotte",
        "notify.enabled_inline": "🔔 Fatto: a mezzanotte ti dico chi era, e ti avviso della sfida nuova.",
        "notify.already_enabled": "🔔 Le notifiche sono già attive: a mezzanotte ti dico chi era.",

        # Eventi: sessione aperta e uscita
        "events.exited": "👋 Evento chiuso: /show per la sfida di oggi.",
        "events.not_open": "❗ Quell'evento non è più in corso: /events per vedere quello attivo.",

        "menu.solution": "🗝 Soluzione",
        "cmd.solution": "La soluzione di una giornata già chiusa",
        "job.rate_line": "\n📊 L'ha indovinato il {percent}% di chi ci ha provato.",
    },
    "es": {
        "common.private_only": "❗ Este comando solo se puede usar en un chat privado.",
        "common.no_challenge": "❗ Todavía no hay un desafío diario disponible.",

        "start.welcome_new": "¡Bienvenido, {name}! Tu cuenta ha sido creada. Usa /help para ver la lista de comandos disponibles.",
        "start.welcome_back": "¡Hola de nuevo, {name}!",

        "help.message": (
            "🛠️ Cómo se juega:\n\n"
            "Cada día una trayectoria que adivinar. En el chat privado basta con escribir el nombre del futbolista: no hace falta ningún comando, y tienes 3 intentos.\n\n"
            "📋 Comandos:\n"
            "/menu - Abre el menú con todo lo que se puede hacer.\n"
            "/show - Muestra el desafío de hoy.\n"
            "/solution - Quién era el futbolista de un día ya cerrado.\n"
            "/guess <respuesta> - La forma clásica de responder, si le tienes cariño.\n"
            "/stats - Tus estadísticas, la racha y los trofeos.\n"
            "/top - La clasificación general y la del mes.\n"
            "/events - El centro de eventos.\n"
            "/archive - Vuelve a jugar los desafíos de días pasados (sin puntos).\n"
            "/training - Desafíos pasados en cadena, sin puntos.\n"
            "/round - En un grupo: un round para todos, gana quien responde primero.\n"
            "/standings - En un grupo: la clasificación de ese grupo.\n"
            "/today - Sal del archivo o del entrenamiento y vuelve al desafío de hoy.\n"
            "/league - Tus ligas privadas; /league_create y /league_join para crear una o entrar.\n"
            "/notify - Activa o desactiva las notificaciones.\n"
            "/language - Cambia el idioma del bot.\n"
            "/legend - Como se lee la imagen de la trayectoria.\n"
        ),

        "language.prompt": "🌐 Elige el idioma del bot:",
        "language.confirm": "✅ Idioma configurado en Español.",

        "guess.missing_answer": "❗ ¡Tienes que escribir también el nombre del futbolista después de /guess!",
        "guess.wrong_last": (
            "❌ Respuesta incorrecta: se acabaron los intentos de hoy.\n"
            "🔒 Quién era te lo digo a medianoche, cuando el día se cierra: a partir de ahí "
            "también lo tienes con /solution."
        ),
        "guess.wrong_remaining": "❌ Respuesta incorrecta, ¡inténtalo de nuevo! Intentos restantes: {attempts_left}.",
        "guess.correct": "✅ ¡Correcto! Has ganado {points} puntos.\n{bonus_message}",
        "guess.bonus": "💎 Bono: +{bonus} punto por ser el primero en acertar!",
        "guess.error.not_registered": "❗ ¡Tienes que registrarte antes de jugar! Usa /start.",
        "guess.error.already_guessed": "✅ ¡Ya has acertado hoy! Vuelve mañana para un nuevo desafío.",
        "guess.error.no_attempts": "❌ ¡Has agotado los intentos de hoy! Vuelve mañana.",
        "guess.error.default": "❗ No se ha podido registrar el intento, inténtalo de nuevo.",

        "show.bonus_info": "💎 Bono: +1 punto si eres el primero en responder!",
        "show.caption": (
            "🎯 Dificultad: {difficulty}\n"
            "🏆 Puntos: {points}\n"
            "{bonus_info}\n\n"
            "✍️ Escribe aquí el nombre del futbolista: no hace falta ningún comando.\n"
            "🔢 Tienes {attempts} intentos. Tras el primer fallo puedes pedir una pista."
        ),

        "stats.not_registered": "❗ ¡No estás registrado! Usa /start para registrarte.",
        "stats.message": (
            "📊 Tus estadísticas:\n\n"
            "👤 Nombre: {name}\n"
            "🏆 Puntos totales: {points_totali}\n"
            "📅 Puntos mensuales: {monthly_points}\n"
            "🧠 Adivinados: {players_guessed}\n"
            "⚡ Bonos de primero en acertar: {bonus_first_guessed}"
        ),
        "stats.button_trophies": "🎖️ Mis trofeos",
        "stats.no_trophies": "😕 Todavía no has ganado ningún trofeo.",
        "stats.button_back": "🔙 Volver a las stats",
        "stats.trophies_title": "🎖️ *Tus trofeos:*\n\n",
        "stats.trophy_monthly": "{medal} *Clasificación Mensual* ({month} {year}, Temporada {season_num}) - Posición: {pos}\n",
        "stats.trophy_event": "{medal} *{event}* (Semana {week}, {year}) - Posición: {pos}\n",
        "stats.nav_back": "⬅️ Atrás",
        "stats.nav_forward": "➡️ Siguiente",

        "notify.not_registered": "❗ Tienes que registrarte antes con /start.",
        "notify.private_only": "❗ Usa este comando en un chat privado.",
        "notify.active_prompt": "🔔 Las notificaciones están activas. ¿Quieres desactivarlas?",
        "notify.button_disable": "❌ Desactivar notificaciones",
        "notify.inactive_prompt": "🔕 Las notificaciones no están activas. ¿Quieres activarlas?",
        "notify.button_enable": "✅ Activar notificaciones",
        "notify.enabled_confirm": "✅ ¡Notificaciones activadas! Recibirás un mensaje cada día.",
        "notify.disabled_confirm": "🔕 Notificaciones desactivadas. Puedes reactivarlas con /notify.",

        "top.title_global": "🏆 <b>Top 10 general</b> 🏆",
        "top.title_monthly": "📆 <b>Top 10 mensual</b> 📆",
        "top.points_suffix": "puntos",
        "top.you_tag": " <b>[TÚ]</b>",
        "top.your_position": "\n📍 <b>Tu posición:</b> {position}° - {score} puntos",
        "top.button_monthly": "📆 Clasificación Mensual",
        "top.button_global": "🌐 Clasificación General",

        "events.no_active": "❗ No hay eventos activos en este momento.",
        "events.no_active_nav": "❗ Ningún evento activo en este momento.",
        "events.no_daily_challenge": "⚠️ No hay ningún desafío disponible para hoy.",
        "events.max_answers": "⚠️ Puedes indicar como máximo {max_answers} equipos separados por comas.",
        "events.wrong": "❌ Respuesta incorrecta. Intentos usados: {used}/{max_attempts}.",
        "events.wrong_career_extra": "\n Respuestas correctas encontradas: {matched}/{total}",
        "events.correct": "✅ ¡Correcto! Has ganado {points} puntos! {bonus_tag}",
        "events.bonus_tag": "(Bono 1°)",
        "events.error.already_guessed": "❌ ¡Ya has acertado hoy!",
        "events.error.no_attempts": "❌ Ya has usado los {max_attempts} intentos de hoy.",
        "events.error.default": "❗ No se ha podido registrar el intento, inténtalo de nuevo.",
        "events.no_player_today": "📭 No hay ningún jugador disponible para hoy.",
        "events.unnamed": "Evento sin nombre",
        "events.no_end_date": "Fecha no disponible",
        "events.button_home": "🏠 Inicio",
        "events.button_player": "🎮 Jugador",
        "events.button_leaderboard": "📊 Clasificación",
        "events.no_participants": "📊 <b>Clasificación del evento</b>:\nNingún participante todavía.",
        "events.leaderboard_title": "📊 <b>Clasificación del evento</b>:\n\n",
        "events.leaderboard_footer": "\n🏆 ¡Al terminar el evento, los primeros 3 obtendrán un trofeo exclusivo!",
        "events.unknown_user": "Usuario desconocido",
        "events.gameplay.career": "🎮 <b>Jugador</b>: adivina los equipos en los que jugó el futbolista",
        "events.gameplay.path": "🎮 <b>Jugador</b>: muestra el futbolista del día a adivinar",
        "events.gameplay.father_son": "🎮 <b>Jugador</b>: adivina la pareja padre/hijo a partir de la imagen",
        "events.gameplay.transfer_guess": "🎮 <b>Jugador</b>: adivina el futbolista a partir del traspaso mostrado",
        "events.gameplay.default": "🎮 <b>Jugador</b>: sigue las instrucciones del desafío del día",
        "events.home_message": (
            "🎉 <b>{name}</b>\n\n"
            "{description}\n\n"
            "📅 El evento termina el <b>{end_date}</b>.\n"
            "¡Los primeros 3 clasificados recibirán un <b>trofeo especial</b> 🏆!\n\n"
            "📌 Usa los botones de abajo para navegar:\n"
            "- 🏠 <b>Inicio</b>: esta pantalla\n"
            "- {gameplay_line}\n"
            "- 📊 <b>Clasificación</b>: mira el top 3 del evento en tiempo real"
        ),
        "events.bonus_available": "⚡ ¡El primero en acertar recibirá 1 punto de bono!",
        "events.bonus_taken": "✅ El bono ya se ha asignado hoy.",
        "events.player_message.path": (
            "🎮 <b>Jugador del día</b>\n\n"
            "👀 ¡Adivina quién es este futbolista!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Escribe el nombre aquí en privado: tienes {attempts} intentos.\n"
            "Con /today vuelves al desafío de hoy."
        ),
        "events.player_message.career": (
            "🧠 <b>Modo carrera</b>\n\n"
            "👤 ¡Adivina al menos <b>{min_correct}</b> de los equipos en los que jugó {player_name}!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Escribe aquí los equipos separados por comas, ej: Roma, Manchester United, Toronto FC\n"
            "(máximo {max_answers} por intento). Tienes {attempts} intentos; con /today vuelves al desafío de hoy."
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Modo padre-hijo</b>\n\n"
            "👤 ¡Adivina la pareja padre/hijo a partir de la imagen!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Escribe aquí el nombre de la pareja: tienes {attempts} intentos.\n"
            "Con /today vuelves al desafío de hoy."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Modo traspaso</b>\n\n"
            "👤 ¡Adivina el futbolista a partir del traspaso mostrado!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Escribe el nombre aquí en privado: tienes {attempts} intentos.\n"
            "Con /today vuelves al desafío de hoy."
        ),
        "events.player_message.default": (
            "🎮 <b>Desafío del día</b>\n\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Escribe aquí tu respuesta: tienes {attempts} intentos.\n"
            "Con /today vuelves al desafío de hoy."
        ),

        "job.congrats": "🎉 ¡Felicidades por adivinar al futbolista {player} de ayer!\n¡Hay un nuevo desafío diario disponible!\n👉 ¡Usa /show e intenta ser el primero!",
        "job.missed": "⚠️ No has adivinado al futbolista {player} de ayer.\n📢 ¡Hay un nuevo desafío diario disponible!\n👉 ¡Usa /show para adivinar al futbolista misterioso!",
        "job.event_mention": "\n\n🎊 Además hay un evento especial activo: {event_name}\n🏆 ¡Participa usando /events y sube en la clasificación del evento!",
        "job.unknown_event": "Evento Desconocido",
        "job.player_fallback": "de ayer",
        "job.feedback_line": "\n\nSi tienes ideas para mejorar el bot o una nueva función que te gustaría ver, ¡manda un mensaje a @gabbente con tu propuesta!",
        "job.monthly_results_title": "🏆 Resultados de la temporada mensual de {month} {year}:\n",
        "job.monthly_winner_line": "{position}° - {username} ({points} puntos)\n",

        # --- texto dentro de las imagenes generadas ---
        "image.path_title": "Trayectoria misteriosa",
        "image.path_subtitle": "{stops} etapas",
        "image.transfer_title": "Traspaso misterioso",
        "image.transfer_subtitle": "¿Quien fiche por este equipo?",
        "image.palmares_title": "Palmares",
        "image.palmares_subtitle": "{count} trofeos conseguidos",
        "image.badge_event": "EVENTO",
        "image.badge_player": "JUGADOR DEL DIA",
        "image.badge_leaderboard": "CLASIFICACION",

        # --- menu principal y botones ---
        "menu.title": "⚽ <b>Guess the Player</b>\nElige qué hacer:",
        "menu.play": "🎯 Desafío de hoy",
        "menu.stats": "📊 Estadísticas",
        "menu.top": "🏆 Clasificación",
        "menu.events": "🎊 Eventos",
        "menu.archive": "🗂 Archivo",
        "menu.training": "🏋️ Entrenamiento",
        "menu.leagues": "👥 Ligas",
        "menu.notify": "🔔 Notificaciones",
        "menu.language": "🌐 Idioma",
        "menu.help": "❓ Ayuda",
        "menu.app": "📱 Abrir la app",
        "menu.back": "⬅️ Menú",

        # --- descripciones de los comandos (set_my_commands) ---
        "cmd.start": "Regístrate y abre el menú",
        "cmd.show": "El desafío de hoy",
        "cmd.stats": "Tus estadísticas",
        "cmd.top": "Clasificación general",
        "cmd.events": "Centro de eventos",
        "cmd.archive": "Vuelve a jugar desafíos pasados",
        "cmd.training": "Desafíos pasados en cadena",
        "cmd.league": "Tus ligas privadas",
        "cmd.notify": "Activa o desactiva las notificaciones",
        "cmd.language": "Cambiar idioma",
        "cmd.help": "Cómo se juega",

        # --- respuesta libre (sin /guess) ---
        "guess.free_text_hint": "💬 Escribeme el nombre del futbolista para intentar el desafio de hoy, o usa /show para verlo otra vez.",
        "guess.typo_note": "\n✍️ Aceptada aunque escribiste «{written}».",

        # --- striscia, condivisione e archivio ---
        "guess.streak": "\n🔥 Racha: {streak} días seguidos.",
        "guess.streak_bonus": "\n🔥 Racha de {streak} días: +{bonus} puntos extra.",
        "stats.streak_line": "🔥 Racha: {streak} (récord: {best})\n🗂 Desafíos recuperados: {archive_solved}",
        "share.button": "📤 Comparte el resultado",
        "share.title": "⚽ Guess the Player #{number}",
        "share.streak": "🔥 {streak}",
        "share.archive_title": "🗄 Guess the Player #{number} (archivo)",

        "feedback.header": "🔎 Comparado con {name}:",
        "feedback.nationality_same": "🌍 Nacionalidad: la misma",
        "feedback.nationality_diff": "🌍 Nacionalidad: distinta",
        "feedback.position_same": "🎽 Posición: la misma",
        "feedback.position_diff": "🎽 Posición: distinta",
        "feedback.birth_same": "🎂 Mismo año de nacimiento ({year})",
        "feedback.birth_before": "⬆️ Más veterano: nació antes de {year}",
        "feedback.birth_after": "⬇️ Más joven: nació después de {year}",

        "training.button_next": "🎲 Otra",
        "training.button_reveal": "👀 Revelar",
        "training.private_only": "El entrenamiento se juega en chat privado conmigo.",
        "training.not_registered": "❗ Regístrate con /start antes de entrenar.",
        "training.empty": "🏋️ Todavía no hay desafíos pasados que reproponer: vuelve dentro de unos días.",
        "training.opened": "🏋️ <b>Entrenamiento</b>: escribe el nombre del futbolista.\nNo da puntos y no toca el desafío de hoy. Tienes {attempts} intentos.\nVuelve al desafío de hoy con /today.",
        "training.correct": "✅ ¡Acertado en {attempts} intentos!\nSin puntos: es entrenamiento.",
        "training.wrong": "❌ No. Intentos restantes: {attempts_left}.",
        "training.wrong_last": "❌ Se acabaron los intentos: era {answer}.",
        "training.revealed": "👀 Era {answer}.",
        "training.not_open": "No tienes ningún entrenamiento abierto: /training para empezar uno.",
        "training.gone": "❗ Ese entrenamiento ya no está disponible: /training para otro.",
        "training.exited": "👋 Entrenamiento cerrado: /show para el desafío de hoy.",

        "group.private_hint": "👥 Esta es una modalidad de grupo: añádeme a un grupo y escribe /round. Aquí en privado está /training.",
        "group.empty": "👥 Todavía no hay desafíos pasados para un round.",
        "group.round_opened": "👥 <b>Round #{number}</b> — {difficulty} ({points} puntos)\nGana quien responda primero. Se responde con <code>/guess nombre</code>, {attempts} intentos por persona.\nLos puntos se quedan en este grupo.",
        "group.no_round": "👥 No hay ningún round abierto: escribe /round para empezar uno.",
        "group.usage": "👥 Se responde así: <code>/guess Maldini</code>",
        "group.already_solved": "👥 Este round ya lo ganó {winner}. /round para el siguiente.",
        "group.no_attempts": "❌ {name}, se te acabaron los intentos de este round.",
        "group.wrong": "❌ {name}: no. Intentos restantes: {attempts_left}.",
        "group.correct": "🏆 <b>{name}</b> gana el round #{number}: +{points} puntos en la clasificación del grupo.\n/round para el siguiente, /standings para ver cómo vais.",
        "group.standings_title": "👥 <b>Clasificación del grupo</b>\n(vale solo aquí: la general es /top)\n\n",
        "group.standings_line": "{medal} {name} — {points} puntos ({rounds} rounds)\n",
        "group.standings_empty": "👥 Nadie ha ganado un round aquí: /round para empezar.",
        "group.button_private": "🎯 Juega el desafío de hoy",
        "group.button_new_round": "🔁 Otro round",

        "legend.button": "ℹ️ Cómo se lee",
        "legend.text": (
            "ℹ️ <b>Cómo se lee la trayectoria</b>\n\n"
            "Cada línea es una etapa, de arriba abajo en orden cronológico.\n\n"
            "• <b>2016 – 2019</b>: los años en ese equipo. <b>2016 – …</b> significa que sigue allí.\n"
            "• <b>→ 2016 – 2017</b>: la flecha, junto a la barra discontinua de la izquierda, indica una <b>cesión</b>.\n"
            "• <b>33 (22)</b>: partidos y, entre paréntesis, goles de <b>liga</b> (la convención de Wikipedia). En los porteros solo aparecen los partidos.\n"
            "• La <b>barra</b> en lugar de los números aparece cuando no tenemos partidos ni goles: mide lo que duró la etapa.\n"
            "• Debajo del nombre del equipo: <b>liga · país</b>.\n"
            "• Arriba a la derecha: la <b>dificultad</b> del desafío.\n\n"
            "En la imagen no hay ni una palabra: la misma figura se envía a quien juega en italiano, español e inglés."
        ),
        "archive.title": "🗂 <b>Archivo</b>\nVuelve a jugar los desafíos de días pasados: no dan puntos, valen por el gusto de conseguirlo.\nElige un día:",
        "archive.empty": "🗂 Todavía no hay ningún desafío en el archivo.",
        "archive.not_registered": "❗ Regístrate con /start antes de usar el archivo.",
        "archive.opened": "🗂 Desafío del {date}. Escribe el nombre del futbolista: este no da puntos.\nVuelve al desafío de hoy con /today.",
        "archive.missing_day": "❗ Ese desafío ya no está disponible.",
        "archive.correct": "✅ ¡Bien! Desafío del {date} recuperado en {attempts} intentos.\nElige otro día con /archive o vuelve a hoy con /today.",
        "archive.wrong": "❌ No. Intentos restantes en este desafío: {attempts_left}.",
        "archive.wrong_last": "❌ Se acabaron los intentos: era {answer}.\nElige otro día con /archive o vuelve a hoy con /today.",
        "archive.already_solved": "✅ Este desafío ya lo habías recuperado. Elige otro con /archive.",
        "archive.no_attempts": "❌ Se acabaron tus intentos en este desafío. Elige otro con /archive.",
        "archive.exited": "👋 Volvemos al desafío de hoy: /show para verlo.",
        "archive.not_in_archive": "No estás jugando ningún desafío del archivo. Abre uno con /archive.",
        "archive.button_today": "🎯 Volver a hoy",
        "cmd.today": "Vuelve al desafío de hoy",

        # --- leghe private ---
        "league.intro": "👥 <b>Tus ligas</b>\nUna liga es una clasificación privada entre amigos: cuentan los puntos que haces desde que entras.\n\nCrea la tuya con <code>/league_create Nombre de la liga</code> o entra en una con <code>/league_join CÓDIGO</code>.",
        "league.none": "👥 No estás en ninguna liga.\n\nCrea una con <code>/league_create Nombre de la liga</code>, o entra en una existente con <code>/league_join CÓDIGO</code>.",
        "league.usage_create": "Uso: <code>/league_create Nombre de la liga</code>",
        "league.usage_join": "Uso: <code>/league_join CÓDIGO</code>",
        "league.usage_leave": "Uso: <code>/league_leave CÓDIGO</code>",
        "league.name_too_long": "❗ El nombre de la liga puede tener como máximo {max} caracteres.",
        "league.created": "✅ ¡Liga <b>{name}</b> creada!\nCódigo: <code>{code}</code>\n\nInvita a quien quieras con este enlace:\n{link}",
        "league.invite": "🔗 Invita a la liga <b>{name}</b>:\n{link}\n\nO que usen <code>/league_join {code}</code>.",
        "league.joined": "✅ ¡Has entrado en la liga <b>{name}</b>! Mira la clasificación con /league.",
        "league.already_member": "Ya formas parte de esta liga. Mira la clasificación con /league.",
        "league.not_found": "❗ No hay ninguna liga con el código <code>{code}</code>.",
        "league.full": "❗ Esta liga está llena ({max} miembros).",
        "league.limit_reached": "❗ Puedes estar como máximo en {max} ligas. Sal de una con <code>/league_leave CÓDIGO</code>.",
        "league.left": "👋 Has dejado la liga <b>{name}</b>.",
        "league.not_member": "❗ No formas parte de esta liga.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCódigo: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "Todavía no hay puntos en esta liga: el primero que acierte abre la clasificación.",
        "league.not_registered": "❗ Regístrate con /start antes de usar las ligas.",
        "league.button_invite": "🔗 Invitar",
        "cmd.league_create": "Crea una liga privada",
        "cmd.league_join": "Entra en una liga con el código",

        # Solución de un día ya cerrado (/solution)
        "solution.usage": (
            "🗝 <b>Solución</b>\n"
            "/solution — el día de ayer.\n"
            "/solution 06/09/26 — un día concreto, si ya está cerrado."
        ),
        "solution.not_registered": "❗ Regístrate con /start antes.",
        "solution.bad_date": "❗ No he entendido la fecha: escríbela como 06/09/26, o usa /solution solo para el día de ayer.",
        "solution.still_open": "🔒 Ese día sigue abierto: la solución llega a medianoche, cuando se cierra. Mientras tanto, juégalo con /show.",
        "solution.missing": "❗ No hay ningún desafío para el {date}.",
        "solution.caption": (
            "🗝 <b>Desafío del {date}</b> (#{number})\n\n"
            "👤 Era <b>{answer}</b>.\n"
            "🎯 {difficulty} · {points} puntos\n"
            "{rate_line}"
        ),
        "solution.rate": "📊 Lo acertó el {percent}% de quienes lo intentaron ({solved} de {players}).",
        "solution.rate_unknown": "📊 Hay muy pocos intentos para decir cuántos lo acertaron.",
        "solution.button_archive": "🗂 Los otros días",

        # Pistas sobre el desafío del día
        "hint.button": "💡 Pista (-1 punto)",
        "hint.header": "💡 <b>Pista {index} de {total}</b>",
        "hint.nationality": "🌍 Nacionalidad: <b>{value}</b>",
        "hint.position": "🧭 Posición: <b>{value}</b>",
        "hint.cost": "\n\n➖ Te cuesta 1 punto: si aciertas ahora te llevas {points} en vez de {full_points}.",
        "hint.no_more": "💡 Ya has usado todas las pistas de hoy ({max_hints}).",
        "hint.needs_attempt": "💡 Las pistas se desbloquean tras un intento fallido: prueba un nombre.",
        "hint.already_guessed": "✅ Ya has acertado hoy: las pistas ya no te hacen falta.",
        "hint.no_attempts": "❌ Se acabaron los intentos: una pista ya no te serviría.",
        "hint.unavailable": "💡 Para este desafío no tengo pistas que darte.",
        "hint.not_registered": "❗ Regístrate con /start antes.",

        # Notificaciones activadas desde el mensaje de derrota
        "guess.button_notify": "🔔 Avísame a medianoche",
        "notify.enabled_inline": "🔔 Hecho: a medianoche te digo quién era, y te aviso del desafío nuevo.",
        "notify.already_enabled": "🔔 Las notificaciones ya están activas: a medianoche te digo quién era.",

        # Eventos: sesión abierta y salida
        "events.exited": "👋 Evento cerrado: /show para el desafío de hoy.",
        "events.not_open": "❗ Ese evento ya no está en curso: /events para ver el activo.",

        "menu.solution": "🗝 Solución",
        "cmd.solution": "La solución de un día ya cerrado",
        "job.rate_line": "\n📊 Lo acertó el {percent}% de quienes lo intentaron.",
    },
    "en": {
        "common.private_only": "❗ This command can only be used in a private chat.",
        "common.no_challenge": "❗ There's no daily challenge available yet.",

        "start.welcome_new": "Welcome, {name}! Your account has been created. Use /help to see the list of available commands.",
        "start.welcome_back": "Hi again, {name}!",

        "help.message": (
            "🛠️ How to play:\n\n"
            "Every day there's a career path to guess. In a private chat just type the player's name: no command needed, and you get 3 attempts.\n\n"
            "📋 Commands:\n"
            "/menu - Opens the menu with everything you can do.\n"
            "/show - Show today's challenge.\n"
            "/solution - Who the player was on a day that has already closed.\n"
            "/guess <answer> - The old way to answer, if you're attached to it.\n"
            "/stats - Your stats, streak and trophies.\n"
            "/top - The global and monthly leaderboards.\n"
            "/events - The events hub.\n"
            "/archive - Replay past challenges (no points).\n"
            "/training - Past challenges back to back, no points.\n"
            "/round - In a group: one round for everyone, first correct answer wins.\n"
            "/standings - In a group: that group's standings.\n"
            "/today - Leave the archive or training and go back to today's challenge.\n"
            "/league - Your private leagues; /league_create and /league_join to create or join one.\n"
            "/notify - Turn notifications on or off.\n"
            "/language - Change the bot's language.\n"
            "/legend - How to read the career path picture.\n"
        ),

        "language.prompt": "🌐 Choose the bot's language:",
        "language.confirm": "✅ Language set to English.",

        "guess.missing_answer": "❗ You also need to write the player's name after /guess!",
        "guess.wrong_last": (
            "❌ Wrong answer: no attempts left for today.\n"
            "🔒 I'll tell you who it was at midnight, when the day closes: from then on "
            "/solution has it too."
        ),
        "guess.wrong_remaining": "❌ Wrong answer, try again! Attempts left: {attempts_left}.",
        "guess.correct": "✅ Correct! You earned {points} points.\n{bonus_message}",
        "guess.bonus": "💎 Bonus: +{bonus} point for being the first to guess!",
        "guess.error.not_registered": "❗ You need to register before playing! Use /start.",
        "guess.error.already_guessed": "✅ You already guessed correctly today! Come back tomorrow for a new challenge.",
        "guess.error.no_attempts": "❌ You've used up today's attempts! Try again tomorrow.",
        "guess.error.default": "❗ Couldn't register the attempt, please try again.",

        "show.bonus_info": "💎 Bonus: +1 point if you're the first to answer!",
        "show.caption": (
            "🎯 Difficulty: {difficulty}\n"
            "🏆 Points: {points}\n"
            "{bonus_info}\n\n"
            "✍️ Just type the player's name here: no command needed.\n"
            "🔢 You have {attempts} attempts. After the first wrong one you can ask for a hint."
        ),

        "stats.not_registered": "❗ You're not registered! Use /start to register.",
        "stats.message": (
            "📊 Your stats:\n\n"
            "👤 Name: {name}\n"
            "🏆 Total points: {points_totali}\n"
            "📅 Monthly points: {monthly_points}\n"
            "🧠 Guessed: {players_guessed}\n"
            "⚡ First-guess bonuses earned: {bonus_first_guessed}"
        ),
        "stats.button_trophies": "🎖️ My trophies",
        "stats.no_trophies": "😕 No trophies earned yet.",
        "stats.button_back": "🔙 Back to stats",
        "stats.trophies_title": "🎖️ *Your trophies:*\n\n",
        "stats.trophy_monthly": "{medal} *Monthly Leaderboard* ({month} {year}, Season {season_num}) - Position: {pos}\n",
        "stats.trophy_event": "{medal} *{event}* (Week {week}, {year}) - Position: {pos}\n",
        "stats.nav_back": "⬅️ Back",
        "stats.nav_forward": "➡️ Next",

        "notify.not_registered": "❗ You need to register first with /start.",
        "notify.private_only": "❗ Use this command in a private chat.",
        "notify.active_prompt": "🔔 Notifications are on. Want to turn them off?",
        "notify.button_disable": "❌ Turn off notifications",
        "notify.inactive_prompt": "🔕 Notifications are off. Want to turn them on?",
        "notify.button_enable": "✅ Turn on notifications",
        "notify.enabled_confirm": "✅ Notifications turned on! You'll get a message every day.",
        "notify.disabled_confirm": "🔕 Notifications turned off. You can turn them back on with /notify.",

        "top.title_global": "🏆 <b>Top 10 overall</b> 🏆",
        "top.title_monthly": "📆 <b>Top 10 this month</b> 📆",
        "top.points_suffix": "points",
        "top.you_tag": " <b>[YOU]</b>",
        "top.your_position": "\n📍 <b>Your position:</b> {position} - {score} points",
        "top.button_monthly": "📆 Monthly Leaderboard",
        "top.button_global": "🌐 Overall Leaderboard",

        "events.no_active": "❗ There are no active events right now.",
        "events.no_active_nav": "❗ No active event right now.",
        "events.no_daily_challenge": "⚠️ No challenge available for today.",
        "events.max_answers": "⚠️ You can enter at most {max_answers} teams, separated by commas.",
        "events.wrong": "❌ Wrong answer. Attempts used: {used}/{max_attempts}.",
        "events.wrong_career_extra": "\n Correct answers found: {matched}/{total}",
        "events.correct": "✅ Correct! You earned {points} points! {bonus_tag}",
        "events.bonus_tag": "(1st bonus)",
        "events.error.already_guessed": "❌ You already guessed correctly today!",
        "events.error.no_attempts": "❌ You've already used all {max_attempts} attempts today.",
        "events.error.default": "❗ Couldn't register the attempt, please try again.",
        "events.no_player_today": "📭 No player available for today.",
        "events.unnamed": "Unnamed event",
        "events.no_end_date": "Date not available",
        "events.button_home": "🏠 Home",
        "events.button_player": "🎮 Player",
        "events.button_leaderboard": "📊 Leaderboard",
        "events.no_participants": "📊 <b>Event leaderboard</b>:\nNo participants yet.",
        "events.leaderboard_title": "📊 <b>Event leaderboard</b>:\n\n",
        "events.leaderboard_footer": "\n🏆 When the event ends, the top 3 will get an exclusive trophy!",
        "events.unknown_user": "Unknown user",
        "events.gameplay.career": "🎮 <b>Player</b>: guess the teams the player has played for",
        "events.gameplay.path": "🎮 <b>Player</b>: shows today's player to guess",
        "events.gameplay.father_son": "🎮 <b>Player</b>: guess the father/son pair from the image",
        "events.gameplay.transfer_guess": "🎮 <b>Player</b>: guess the player from the transfer shown",
        "events.gameplay.default": "🎮 <b>Player</b>: follow the instructions for today's challenge",
        "events.home_message": (
            "🎉 <b>{name}</b>\n\n"
            "{description}\n\n"
            "📅 The event ends on <b>{end_date}</b>.\n"
            "The top 3 will receive a <b>special trophy</b> 🏆!\n\n"
            "📌 Use the buttons below to navigate:\n"
            "- 🏠 <b>Home</b>: this screen\n"
            "- {gameplay_line}\n"
            "- 📊 <b>Leaderboard</b>: see the event's live top 3"
        ),
        "events.bonus_available": "⚡ The first to guess correctly will get 1 bonus point!",
        "events.bonus_taken": "✅ The bonus has already been assigned today.",
        "events.player_message.path": (
            "🎮 <b>Player of the day</b>\n\n"
            "👀 Guess who this player is!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Just type the name here in private: you have {attempts} attempts.\n"
            "Use /today to go back to today's challenge."
        ),
        "events.player_message.career": (
            "🧠 <b>Career mode</b>\n\n"
            "👤 Guess at least <b>{min_correct}</b> of the teams {player_name} has played for!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Type the teams here separated by commas, e.g.: Roma, Manchester United, Toronto FC\n"
            "(max {max_answers} per attempt). You have {attempts} attempts; use /today to go back to today's challenge."
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Father-son mode</b>\n\n"
            "👤 Guess the father/son pair from the image!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Type the pair's name here: you have {attempts} attempts.\n"
            "Use /today to go back to today's challenge."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Transfer mode</b>\n\n"
            "👤 Guess the player from the transfer shown!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Just type the name here in private: you have {attempts} attempts.\n"
            "Use /today to go back to today's challenge."
        ),
        "events.player_message.default": (
            "🎮 <b>Challenge of the day</b>\n\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "✍️ Type your answer here: you have {attempts} attempts.\n"
            "Use /today to go back to today's challenge."
        ),

        "job.congrats": "🎉 Congrats for guessing yesterday's player, {player}!\nA new daily challenge is available!\n👉 Use /show and try to be the first!",
        "job.missed": "⚠️ You didn't guess yesterday's player, {player}.\n📢 A new daily challenge is available!\n👉 Use /show to guess the mystery player!",
        "job.event_mention": "\n\n🎊 There's also a special event running: {event_name}\n🏆 Join in with /events and climb the event leaderboard!",
        "job.unknown_event": "Unknown Event",
        "job.player_fallback": "yesterday's",
        "job.feedback_line": "\n\nIf you have ideas to improve the bot or a new feature you'd like to see, message @gabbente with your suggestion!",
        "job.monthly_results_title": "🏆 Results of the {month} {year} monthly season:\n",
        "job.monthly_winner_line": "{position}. {username} ({points} points)\n",

        # --- text inside the generated images ---
        "image.path_title": "Mystery career path",
        "image.path_subtitle": "{stops} clubs",
        "image.transfer_title": "Mystery transfer",
        "image.transfer_subtitle": "Who moved here?",
        "image.palmares_title": "Trophy room",
        "image.palmares_subtitle": "{count} trophies won",
        "image.badge_event": "EVENT",
        "image.badge_player": "PLAYER OF THE DAY",
        "image.badge_leaderboard": "LEADERBOARD",

        # --- main menu and buttons ---
        "menu.title": "⚽ <b>Guess the Player</b>\nPick what to do:",
        "menu.play": "🎯 Today's challenge",
        "menu.stats": "📊 Stats",
        "menu.top": "🏆 Leaderboard",
        "menu.events": "🎊 Events",
        "menu.archive": "🗂 Archive",
        "menu.training": "🏋️ Training",
        "menu.leagues": "👥 Leagues",
        "menu.notify": "🔔 Notifications",
        "menu.language": "🌐 Language",
        "menu.help": "❓ Help",
        "menu.app": "📱 Open the app",
        "menu.back": "⬅️ Menu",

        # --- command descriptions (set_my_commands) ---
        "cmd.start": "Sign up and open the menu",
        "cmd.show": "Today's challenge",
        "cmd.stats": "Your stats",
        "cmd.top": "Global leaderboard",
        "cmd.events": "Event hub",
        "cmd.archive": "Replay past challenges",
        "cmd.training": "Past challenges back to back",
        "cmd.league": "Your private leagues",
        "cmd.notify": "Turn notifications on or off",
        "cmd.language": "Change language",
        "cmd.help": "How to play",

        # --- free-text answers (no /guess) ---
        "guess.free_text_hint": "💬 Just type the player's name to try today's challenge, or use /show to see it again.",
        "guess.typo_note": "\n✍️ Accepted even though you typed «{written}».",

        # --- striscia, condivisione e archivio ---
        "guess.streak": "\n🔥 Streak: {streak} days in a row.",
        "guess.streak_bonus": "\n🔥 {streak}-day streak: +{bonus} bonus points.",
        "stats.streak_line": "🔥 Streak: {streak} (best: {best})\n🗂 Archive challenges solved: {archive_solved}",
        "share.button": "📤 Share your result",
        "share.title": "⚽ Guess the Player #{number}",
        "share.streak": "🔥 {streak}",
        "share.archive_title": "🗄 Guess the Player #{number} (archive)",

        "feedback.header": "🔎 Compared with {name}:",
        "feedback.nationality_same": "🌍 Nationality: the same",
        "feedback.nationality_diff": "🌍 Nationality: different",
        "feedback.position_same": "🎽 Position: the same",
        "feedback.position_diff": "🎽 Position: different",
        "feedback.birth_same": "🎂 Same birth year ({year})",
        "feedback.birth_before": "⬆️ Older: born before {year}",
        "feedback.birth_after": "⬇️ Younger: born after {year}",

        "training.button_next": "🎲 Another one",
        "training.button_reveal": "👀 Reveal",
        "training.private_only": "Training is played in a private chat with me.",
        "training.not_registered": "❗ Sign up with /start before training.",
        "training.empty": "🏋️ There are no past challenges to replay yet: come back in a few days.",
        "training.opened": "🏋️ <b>Training</b>: type the player's name.\nNo points, and it doesn't touch today's challenge. You have {attempts} attempts.\nBack to today's challenge with /today.",
        "training.correct": "✅ Got it in {attempts} attempts!\nNo points: this is training.",
        "training.wrong": "❌ No. Attempts left: {attempts_left}.",
        "training.wrong_last": "❌ Out of attempts: it was {answer}.",
        "training.revealed": "👀 It was {answer}.",
        "training.not_open": "You have no training challenge open: /training to start one.",
        "training.gone": "❗ That training challenge is no longer available: /training for another one.",
        "training.exited": "👋 Training closed: /show for today's challenge.",

        "group.private_hint": "👥 This is a group mode: add me to a group and type /round. Here in private there is /training.",
        "group.empty": "👥 There are no past challenges to turn into a round yet.",
        "group.round_opened": "👥 <b>Round #{number}</b> — {difficulty} ({points} points)\nFirst correct answer wins. Answer with <code>/guess name</code>, {attempts} attempts each.\nThe points stay in this group.",
        "group.no_round": "👥 No round is open: type /round to start one.",
        "group.usage": "👥 Answer like this: <code>/guess Maldini</code>",
        "group.already_solved": "👥 {winner} already won this round. /round for the next one.",
        "group.no_attempts": "❌ {name}, you are out of attempts for this round.",
        "group.wrong": "❌ {name}: no. Attempts left: {attempts_left}.",
        "group.correct": "🏆 <b>{name}</b> wins round #{number}: +{points} points in the group standings.\n/round for the next one, /standings to see where you stand.",
        "group.standings_title": "👥 <b>Group standings</b>\n(they only count here: the global one is /top)\n\n",
        "group.standings_line": "{medal} {name} — {points} points ({rounds} rounds)\n",
        "group.standings_empty": "👥 Nobody has won a round here: /round to get started.",
        "group.button_private": "🎯 Play today's challenge",
        "group.button_new_round": "🔁 Another round",

        "legend.button": "ℹ️ How to read it",
        "legend.text": (
            "ℹ️ <b>How to read the career path</b>\n\n"
            "Each row is a stop, top to bottom in chronological order.\n\n"
            "• <b>2016 – 2019</b>: the years at that club. <b>2016 – …</b> means he is still there.\n"
            "• <b>→ 2016 – 2017</b>: the arrow, together with the dashed bar on the left, marks a <b>loan</b>.\n"
            "• <b>33 (22)</b>: appearances and, in brackets, <b>league</b> goals (the Wikipedia convention). For goalkeepers only appearances are shown.\n"
            "• The <b>bar</b> replaces the numbers when we do not have appearances and goals: its length is how long the stop lasted.\n"
            "• Under the club name: <b>league · country</b>.\n"
            "• Top right: the <b>difficulty</b> of the challenge.\n\n"
            "There is not a single word in the picture: the same image goes to people playing in Italian, Spanish and English."
        ),
        "archive.title": "🗂 <b>Archive</b>\nReplay past challenges: they award no points, they're just for the satisfaction.\nPick a day:",
        "archive.empty": "🗂 There's nothing in the archive yet.",
        "archive.not_registered": "❗ Sign up with /start before using the archive.",
        "archive.opened": "🗂 Challenge from {date}. Type the player's name: this one awards no points.\nGo back to today's challenge with /today.",
        "archive.missing_day": "❗ That challenge isn't available any more.",
        "archive.correct": "✅ Got it! Challenge from {date} solved in {attempts} attempts.\nPick another day with /archive, or go back to today with /today.",
        "archive.wrong": "❌ Nope. Attempts left on this one: {attempts_left}.",
        "archive.wrong_last": "❌ Out of attempts: it was {answer}.\nPick another day with /archive, or go back to today with /today.",
        "archive.already_solved": "✅ You already solved this one. Pick another with /archive.",
        "archive.no_attempts": "❌ No attempts left on this challenge. Pick another with /archive.",
        "archive.exited": "👋 Back to today's challenge: /show to see it.",
        "archive.not_in_archive": "You're not playing an archive challenge. Open one with /archive.",
        "archive.button_today": "🎯 Back to today",
        "cmd.today": "Back to today's challenge",

        # --- leghe private ---
        "league.intro": "👥 <b>Your leagues</b>\nA league is a private leaderboard among friends: it counts the points you score from the moment you join.\n\nCreate one with <code>/league_create League name</code>, or join one with <code>/league_join CODE</code>.",
        "league.none": "👥 You're not in any league.\n\nCreate one with <code>/league_create League name</code>, or join an existing one with <code>/league_join CODE</code>.",
        "league.usage_create": "Usage: <code>/league_create League name</code>",
        "league.usage_join": "Usage: <code>/league_join CODE</code>",
        "league.usage_leave": "Usage: <code>/league_leave CODE</code>",
        "league.name_too_long": "❗ A league name can be at most {max} characters long.",
        "league.created": "✅ League <b>{name}</b> created!\nCode: <code>{code}</code>\n\nInvite anyone with this link:\n{link}",
        "league.invite": "🔗 Invite people to <b>{name}</b>:\n{link}\n\nOr have them use <code>/league_join {code}</code>.",
        "league.joined": "✅ You joined the league <b>{name}</b>! See the standings with /league.",
        "league.already_member": "You're already in this league. See the standings with /league.",
        "league.not_found": "❗ No league with code <code>{code}</code>.",
        "league.full": "❗ This league is full ({max} members).",
        "league.limit_reached": "❗ You can be in at most {max} leagues. Leave one with <code>/league_leave CODE</code>.",
        "league.left": "👋 You left the league <b>{name}</b>.",
        "league.not_member": "❗ You're not a member of this league.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCode: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "No points in this league yet: the first correct answer opens the standings.",
        "league.not_registered": "❗ Sign up with /start before using leagues.",
        "league.button_invite": "🔗 Invite",
        "cmd.league_create": "Create a private league",
        "cmd.league_join": "Join a league with its code",

        # Solution of a day that has already closed (/solution)
        "solution.usage": (
            "🗝 <b>Solution</b>\n"
            "/solution — yesterday.\n"
            "/solution 06/09/26 — a specific day, once it has closed."
        ),
        "solution.not_registered": "❗ Sign up with /start first.",
        "solution.bad_date": "❗ I didn't understand the date: write it as 06/09/26, or use /solution on its own for yesterday.",
        "solution.still_open": "🔒 That day is still open: the solution comes at midnight, when it closes. In the meantime, play it with /show.",
        "solution.missing": "❗ There is no challenge for {date}.",
        "solution.caption": (
            "🗝 <b>Challenge of {date}</b> (#{number})\n\n"
            "👤 It was <b>{answer}</b>.\n"
            "🎯 {difficulty} · {points} points\n"
            "{rate_line}"
        ),
        "solution.rate": "📊 {percent}% of the people who tried got it ({solved} out of {players}).",
        "solution.rate_unknown": "📊 Too few attempts to say how many got it.",
        "solution.button_archive": "🗂 The other days",

        # Hints on the daily challenge
        "hint.button": "💡 Hint (-1 point)",
        "hint.header": "💡 <b>Hint {index} of {total}</b>",
        "hint.nationality": "🌍 Nationality: <b>{value}</b>",
        "hint.position": "🧭 Position: <b>{value}</b>",
        "hint.cost": "\n\n➖ It costs you 1 point: if you get it now you take {points} instead of {full_points}.",
        "hint.no_more": "💡 You have already used all of today's hints ({max_hints}).",
        "hint.needs_attempt": "💡 Hints unlock after a wrong attempt: try a name.",
        "hint.already_guessed": "✅ You have already got it today: you don't need hints any more.",
        "hint.no_attempts": "❌ No attempts left: a hint would not help you now.",
        "hint.unavailable": "💡 I have no hints to give you for this challenge.",
        "hint.not_registered": "❗ Sign up with /start first.",

        # Notifications turned on from the losing message
        "guess.button_notify": "🔔 Tell me at midnight",
        "notify.enabled_inline": "🔔 Done: at midnight I'll tell you who it was, and let you know about the new challenge.",
        "notify.already_enabled": "🔔 Notifications are already on: at midnight I'll tell you who it was.",

        # Events: open session and exit
        "events.exited": "👋 Event closed: /show for today's challenge.",
        "events.not_open": "❗ That event is no longer running: /events to see the active one.",

        "menu.solution": "🗝 Solution",
        "cmd.solution": "The solution of a day that has already closed",
        "job.rate_line": "\n📊 {percent}% of the people who tried got it.",
    },
}
