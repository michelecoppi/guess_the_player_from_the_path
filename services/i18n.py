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
            "/guess <risposta> - Il vecchio modo di rispondere, se ci sei affezionato.\n"
            "/stats - Le tue statistiche, la striscia e i trofei.\n"
            "/top - La classifica generale e quella del mese.\n"
            "/events - Il centro eventi.\n"
            "/archivio - Rigioca le sfide dei giorni scorsi (senza punti).\n"
            "/oggi - Esci dall'archivio e torna alla sfida di oggi.\n"
            "/lega - Le tue leghe private; /lega_crea e /lega_entra per farne una o entrarci.\n"
            "/notify - Attiva o disattiva le notifiche.\n"
            "/language - Cambia la lingua del bot.\n"
        ),

        "language.prompt": "🌐 Scegli la lingua del bot:",
        "language.confirm": "✅ Lingua impostata su Italiano.",

        "guess.missing_answer": "❗ Devi scrivere anche il nome del calciatore dopo /guess!",
        "guess.wrong_last": "❌ Risposta sbagliata, hai esaurito i tentativi per oggi! Riprova domani.",
        "guess.wrong_remaining": "❌ Risposta sbagliata, riprova! Hai {attempts_left} tentativi rimasti.",
        "guess.correct": "✅ Corretto! Hai guadagnato {points} punti.\n{bonus_message}",
        "guess.bonus": "💎 Bonus: +{bonus} punto perchè sei il primo ad indovinare!",
        "guess.error.not_registered": "❗ Devi registrarti prima di giocare! Usa /start.",
        "guess.error.already_guessed": "✅ Hai già indovinato oggi! Torna domani per una nuova sfida.",
        "guess.error.no_attempts": "❌ Hai esaurito i tentativi per oggi! Riprova domani.",
        "guess.error.default": "❗ Non è stato possibile registrare il tentativo, riprova.",

        "show.bonus_info": "💎 Bonus: +1 punto se sei il primo a rispondere!",
        "show.caption": "🎯 Difficoltà: {difficulty}\n🏆 Punti: {points}\n{bonus_info}\n\n🔍 Indovina la carriera con il comando /guess <risposta> in privato al bot!\n",

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
            "Per indovinare, usa il comando /events in privato inserendo il nome del calciatore."
        ),
        "events.player_message.career": (
            "🧠 <b>Modalità carriera</b>\n\n"
            "👤 Indovina almeno <b>{min_correct}</b> delle squadre in cui ha giocato {player_name}!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Scrivi le squadre in privato al bot separate da virgole, es: /events Roma, Manchester United, Toronto FC (massimo 5 squadre a tentativo)"
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Modalità padre-figlio</b>\n\n"
            "👤 Indovina la coppia padre/figlio dall'immagine!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato inserendo il nome della coppia padre/figlio."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Modalità trasferimento</b>\n\n"
            "👤 Indovina il calciatore dal trasferimento mostrato!\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato inserendo il nome del calciatore."
        ),
        "events.player_message.default": (
            "🎮 <b>Sfida del giorno</b>\n\n"
            "🏆 Punti disponibili: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Per indovinare, usa il comando /events in privato al bot."
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
        "archive.title": "🗂 <b>Archivio</b>\nRigioca le sfide dei giorni scorsi: non danno punti, valgono per il gusto di riuscirci.\nScegli un giorno:",
        "archive.empty": "🗂 Non c'è ancora nessuna sfida in archivio.",
        "archive.not_registered": "❗ Devi registrarti con /start prima di usare l'archivio.",
        "archive.opened": "🗂 Sfida del {date}. Scrivi il nome del calciatore: questa non assegna punti.\nTorna alla sfida di oggi con /oggi.",
        "archive.missing_day": "❗ Quella sfida non è più disponibile.",
        "archive.correct": "✅ Preso! Sfida del {date} recuperata in {attempts} tentativi.\nScegli un altro giorno con /archivio o torna a oggi con /oggi.",
        "archive.wrong": "❌ No. Tentativi rimasti per questa sfida: {attempts_left}.",
        "archive.wrong_last": "❌ Tentativi finiti: era {answer}.\nScegli un altro giorno con /archivio o torna a oggi con /oggi.",
        "archive.already_solved": "✅ Questa sfida l'avevi già recuperata. Scegline un'altra con /archivio.",
        "archive.no_attempts": "❌ Hai finito i tentativi su questa sfida. Scegline un'altra con /archivio.",
        "archive.exited": "👋 Torniamo alla sfida di oggi: /show per rivederla.",
        "archive.not_in_archive": "Non stai giocando nessuna sfida d'archivio. Aprine una con /archivio.",
        "archive.button_today": "🎯 Torna a oggi",
        "cmd.today": "Torna alla sfida di oggi",

        # --- leghe private ---
        "league.intro": "👥 <b>Le tue leghe</b>\nUna lega è una classifica privata fra amici: si contano i punti che fai da quando ne fai parte.\n\nCrea la tua con <code>/lega_crea Nome della lega</code> o entra in una con <code>/lega_entra CODICE</code>.",
        "league.none": "👥 Non fai parte di nessuna lega.\n\nCreane una con <code>/lega_crea Nome della lega</code>, oppure entra in una esistente con <code>/lega_entra CODICE</code>.",
        "league.usage_create": "Uso: <code>/lega_crea Nome della lega</code>",
        "league.usage_join": "Uso: <code>/lega_entra CODICE</code>",
        "league.usage_leave": "Uso: <code>/lega_esci CODICE</code>",
        "league.name_too_long": "❗ Il nome della lega può essere lungo al massimo {max} caratteri.",
        "league.created": "✅ Lega <b>{name}</b> creata!\nCodice: <code>{code}</code>\n\nInvita chi vuoi con questo link:\n{link}",
        "league.invite": "🔗 Invita nella lega <b>{name}</b>:\n{link}\n\nOppure fagli usare <code>/lega_entra {code}</code>.",
        "league.joined": "✅ Sei entrato nella lega <b>{name}</b>! Vedi la classifica con /lega.",
        "league.already_member": "Fai già parte di questa lega. Vedi la classifica con /lega.",
        "league.not_found": "❗ Nessuna lega con il codice <code>{code}</code>.",
        "league.full": "❗ Questa lega è piena ({max} membri).",
        "league.limit_reached": "❗ Puoi far parte di al massimo {max} leghe. Escine da una con <code>/lega_esci CODICE</code>.",
        "league.left": "👋 Hai lasciato la lega <b>{name}</b>.",
        "league.not_member": "❗ Non fai parte di questa lega.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCodice: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "Ancora nessun punto in questa lega: il primo che indovina apre la classifica.",
        "league.not_registered": "❗ Devi registrarti con /start prima di usare le leghe.",
        "league.button_invite": "🔗 Invita",
        "cmd.league_create": "Crea una lega privata",
        "cmd.league_join": "Entra in una lega con il codice",
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
            "/guess <respuesta> - La forma clásica de responder, si le tienes cariño.\n"
            "/stats - Tus estadísticas, la racha y los trofeos.\n"
            "/top - La clasificación general y la del mes.\n"
            "/events - El centro de eventos.\n"
            "/archivio - Vuelve a jugar los desafíos de días pasados (sin puntos).\n"
            "/oggi - Sal del archivo y vuelve al desafío de hoy.\n"
            "/lega - Tus ligas privadas; /lega_crea y /lega_entra para crear una o entrar.\n"
            "/notify - Activa o desactiva las notificaciones.\n"
            "/language - Cambia el idioma del bot.\n"
        ),

        "language.prompt": "🌐 Elige el idioma del bot:",
        "language.confirm": "✅ Idioma configurado en Español.",

        "guess.missing_answer": "❗ ¡Tienes que escribir también el nombre del futbolista después de /guess!",
        "guess.wrong_last": "❌ Respuesta incorrecta, ¡has agotado los intentos de hoy! Vuelve mañana.",
        "guess.wrong_remaining": "❌ Respuesta incorrecta, ¡inténtalo de nuevo! Te quedan {attempts_left} intentos.",
        "guess.correct": "✅ ¡Correcto! Has ganado {points} puntos.\n{bonus_message}",
        "guess.bonus": "💎 Bono: +{bonus} punto por ser el primero en acertar!",
        "guess.error.not_registered": "❗ ¡Tienes que registrarte antes de jugar! Usa /start.",
        "guess.error.already_guessed": "✅ ¡Ya has acertado hoy! Vuelve mañana para un nuevo desafío.",
        "guess.error.no_attempts": "❌ ¡Has agotado los intentos de hoy! Vuelve mañana.",
        "guess.error.default": "❗ No se ha podido registrar el intento, inténtalo de nuevo.",

        "show.bonus_info": "💎 Bono: +1 punto si eres el primero en responder!",
        "show.caption": "🎯 Dificultad: {difficulty}\n🏆 Puntos: {points}\n{bonus_info}\n\n🔍 ¡Adivina la carrera con el comando /guess <respuesta> en privado al bot!\n",

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
            "Para adivinar, usa el comando /events en privado escribiendo el nombre del futbolista."
        ),
        "events.player_message.career": (
            "🧠 <b>Modo carrera</b>\n\n"
            "👤 ¡Adivina al menos <b>{min_correct}</b> de los equipos en los que jugó {player_name}!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Escribe los equipos en privado al bot separados por comas, ej: /events Roma, Manchester United, Toronto FC (máximo 5 equipos por intento)"
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Modo padre-hijo</b>\n\n"
            "👤 ¡Adivina la pareja padre/hijo a partir de la imagen!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Para adivinar, usa el comando /events en privado escribiendo el nombre de la pareja padre/hijo."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Modo traspaso</b>\n\n"
            "👤 ¡Adivina el futbolista a partir del traspaso mostrado!\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Para adivinar, usa el comando /events en privado escribiendo el nombre del futbolista."
        ),
        "events.player_message.default": (
            "🎮 <b>Desafío del día</b>\n\n"
            "🏆 Puntos disponibles: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Para adivinar, usa el comando /events en privado al bot."
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
        "menu.title": "⚽ <b>Guess the Player</b>\nElige que hacer:",
        "menu.play": "🎯 Desafio de hoy",
        "menu.stats": "📊 Estadisticas",
        "menu.top": "🏆 Clasificacion",
        "menu.events": "🎊 Eventos",
        "menu.archive": "🗂 Archivo",
        "menu.leagues": "👥 Ligas",
        "menu.notify": "🔔 Notificaciones",
        "menu.language": "🌐 Idioma",
        "menu.help": "❓ Ayuda",
        "menu.app": "📱 Abrir la app",
        "menu.back": "⬅️ Menu",

        # --- descripciones de los comandos (set_my_commands) ---
        "cmd.start": "Registrate y abre el menu",
        "cmd.show": "El desafio de hoy",
        "cmd.stats": "Tus estadisticas",
        "cmd.top": "Clasificacion general",
        "cmd.events": "Centro de eventos",
        "cmd.archive": "Vuelve a jugar desafios pasados",
        "cmd.league": "Tus ligas privadas",
        "cmd.notify": "Activa o desactiva las notificaciones",
        "cmd.language": "Cambiar idioma",
        "cmd.help": "Como se juega",

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
        "archive.title": "🗂 <b>Archivo</b>\nVuelve a jugar los desafíos de días pasados: no dan puntos, valen por el gusto de conseguirlo.\nElige un día:",
        "archive.empty": "🗂 Todavía no hay ningún desafío en el archivo.",
        "archive.not_registered": "❗ Regístrate con /start antes de usar el archivo.",
        "archive.opened": "🗂 Desafío del {date}. Escribe el nombre del futbolista: este no da puntos.\nVuelve al desafío de hoy con /oggi.",
        "archive.missing_day": "❗ Ese desafío ya no está disponible.",
        "archive.correct": "✅ ¡Bien! Desafío del {date} recuperado en {attempts} intentos.\nElige otro día con /archivio o vuelve a hoy con /oggi.",
        "archive.wrong": "❌ No. Intentos restantes en este desafío: {attempts_left}.",
        "archive.wrong_last": "❌ Se acabaron los intentos: era {answer}.\nElige otro día con /archivio o vuelve a hoy con /oggi.",
        "archive.already_solved": "✅ Este desafío ya lo habías recuperado. Elige otro con /archivio.",
        "archive.no_attempts": "❌ Se acabaron tus intentos en este desafío. Elige otro con /archivio.",
        "archive.exited": "👋 Volvemos al desafío de hoy: /show para verlo.",
        "archive.not_in_archive": "No estás jugando ningún desafío del archivo. Abre uno con /archivio.",
        "archive.button_today": "🎯 Volver a hoy",
        "cmd.today": "Vuelve al desafío de hoy",

        # --- leghe private ---
        "league.intro": "👥 <b>Tus ligas</b>\nUna liga es una clasificación privada entre amigos: cuentan los puntos que haces desde que entras.\n\nCrea la tuya con <code>/lega_crea Nombre de la liga</code> o entra en una con <code>/lega_entra CÓDIGO</code>.",
        "league.none": "👥 No estás en ninguna liga.\n\nCrea una con <code>/lega_crea Nombre de la liga</code>, o entra en una existente con <code>/lega_entra CÓDIGO</code>.",
        "league.usage_create": "Uso: <code>/lega_crea Nombre de la liga</code>",
        "league.usage_join": "Uso: <code>/lega_entra CÓDIGO</code>",
        "league.usage_leave": "Uso: <code>/lega_esci CÓDIGO</code>",
        "league.name_too_long": "❗ El nombre de la liga puede tener como máximo {max} caracteres.",
        "league.created": "✅ ¡Liga <b>{name}</b> creada!\nCódigo: <code>{code}</code>\n\nInvita a quien quieras con este enlace:\n{link}",
        "league.invite": "🔗 Invita a la liga <b>{name}</b>:\n{link}\n\nO que usen <code>/lega_entra {code}</code>.",
        "league.joined": "✅ ¡Has entrado en la liga <b>{name}</b>! Mira la clasificación con /lega.",
        "league.already_member": "Ya formas parte de esta liga. Mira la clasificación con /lega.",
        "league.not_found": "❗ No hay ninguna liga con el código <code>{code}</code>.",
        "league.full": "❗ Esta liga está llena ({max} miembros).",
        "league.limit_reached": "❗ Puedes estar como máximo en {max} ligas. Sal de una con <code>/lega_esci CÓDIGO</code>.",
        "league.left": "👋 Has dejado la liga <b>{name}</b>.",
        "league.not_member": "❗ No formas parte de esta liga.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCódigo: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "Todavía no hay puntos en esta liga: el primero que acierte abre la clasificación.",
        "league.not_registered": "❗ Regístrate con /start antes de usar las ligas.",
        "league.button_invite": "🔗 Invitar",
        "cmd.league_create": "Crea una liga privada",
        "cmd.league_join": "Entra en una liga con el código",
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
            "/guess <answer> - The old way to answer, if you're attached to it.\n"
            "/stats - Your stats, streak and trophies.\n"
            "/top - The global and monthly leaderboards.\n"
            "/events - The events hub.\n"
            "/archivio - Replay past challenges (no points).\n"
            "/oggi - Leave the archive and go back to today's challenge.\n"
            "/lega - Your private leagues; /lega_crea and /lega_entra to create or join one.\n"
            "/notify - Turn notifications on or off.\n"
            "/language - Change the bot's language.\n"
        ),

        "language.prompt": "🌐 Choose the bot's language:",
        "language.confirm": "✅ Language set to English.",

        "guess.missing_answer": "❗ You also need to write the player's name after /guess!",
        "guess.wrong_last": "❌ Wrong answer, you've used up today's attempts! Try again tomorrow.",
        "guess.wrong_remaining": "❌ Wrong answer, try again! You have {attempts_left} attempts left.",
        "guess.correct": "✅ Correct! You earned {points} points.\n{bonus_message}",
        "guess.bonus": "💎 Bonus: +{bonus} point for being the first to guess!",
        "guess.error.not_registered": "❗ You need to register before playing! Use /start.",
        "guess.error.already_guessed": "✅ You already guessed correctly today! Come back tomorrow for a new challenge.",
        "guess.error.no_attempts": "❌ You've used up today's attempts! Try again tomorrow.",
        "guess.error.default": "❗ Couldn't register the attempt, please try again.",

        "show.bonus_info": "💎 Bonus: +1 point if you're the first to answer!",
        "show.caption": "🎯 Difficulty: {difficulty}\n🏆 Points: {points}\n{bonus_info}\n\n🔍 Guess the career with the command /guess <answer> in a private chat with the bot!\n",

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
            "To guess, use /events in a private chat with the player's name."
        ),
        "events.player_message.career": (
            "🧠 <b>Career mode</b>\n\n"
            "👤 Guess at least <b>{min_correct}</b> of the teams {player_name} has played for!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "Write the teams in a private chat with the bot separated by commas, e.g.: /events Roma, Manchester United, Toronto FC (max 5 teams per attempt)"
        ),
        "events.player_message.father_son": (
            "👨‍👦 <b>Father-son mode</b>\n\n"
            "👤 Guess the father/son pair from the image!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "To guess, use /events in a private chat with the father/son pair's name."
        ),
        "events.player_message.transfer_guess": (
            "🔄 <b>Transfer mode</b>\n\n"
            "👤 Guess the player from the transfer shown!\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "To guess, use /events in a private chat with the player's name."
        ),
        "events.player_message.default": (
            "🎮 <b>Challenge of the day</b>\n\n"
            "🏆 Points available: <b>{points}</b>\n"
            "{bonus_msg}\n"
            "To guess, use /events in a private chat with the bot."
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
        "archive.title": "🗂 <b>Archive</b>\nReplay past challenges: they award no points, they're just for the satisfaction.\nPick a day:",
        "archive.empty": "🗂 There's nothing in the archive yet.",
        "archive.not_registered": "❗ Sign up with /start before using the archive.",
        "archive.opened": "🗂 Challenge from {date}. Type the player's name: this one awards no points.\nGo back to today's challenge with /oggi.",
        "archive.missing_day": "❗ That challenge isn't available any more.",
        "archive.correct": "✅ Got it! Challenge from {date} solved in {attempts} attempts.\nPick another day with /archivio, or go back to today with /oggi.",
        "archive.wrong": "❌ Nope. Attempts left on this one: {attempts_left}.",
        "archive.wrong_last": "❌ Out of attempts: it was {answer}.\nPick another day with /archivio, or go back to today with /oggi.",
        "archive.already_solved": "✅ You already solved this one. Pick another with /archivio.",
        "archive.no_attempts": "❌ No attempts left on this challenge. Pick another with /archivio.",
        "archive.exited": "👋 Back to today's challenge: /show to see it.",
        "archive.not_in_archive": "You're not playing an archive challenge. Open one with /archivio.",
        "archive.button_today": "🎯 Back to today",
        "cmd.today": "Back to today's challenge",

        # --- leghe private ---
        "league.intro": "👥 <b>Your leagues</b>\nA league is a private leaderboard among friends: it counts the points you score from the moment you join.\n\nCreate one with <code>/lega_crea League name</code>, or join one with <code>/lega_entra CODE</code>.",
        "league.none": "👥 You're not in any league.\n\nCreate one with <code>/lega_crea League name</code>, or join an existing one with <code>/lega_entra CODE</code>.",
        "league.usage_create": "Usage: <code>/lega_crea League name</code>",
        "league.usage_join": "Usage: <code>/lega_entra CODE</code>",
        "league.usage_leave": "Usage: <code>/lega_esci CODE</code>",
        "league.name_too_long": "❗ A league name can be at most {max} characters long.",
        "league.created": "✅ League <b>{name}</b> created!\nCode: <code>{code}</code>\n\nInvite anyone with this link:\n{link}",
        "league.invite": "🔗 Invite people to <b>{name}</b>:\n{link}\n\nOr have them use <code>/lega_entra {code}</code>.",
        "league.joined": "✅ You joined the league <b>{name}</b>! See the standings with /lega.",
        "league.already_member": "You're already in this league. See the standings with /lega.",
        "league.not_found": "❗ No league with code <code>{code}</code>.",
        "league.full": "❗ This league is full ({max} members).",
        "league.limit_reached": "❗ You can be in at most {max} leagues. Leave one with <code>/lega_esci CODE</code>.",
        "league.left": "👋 You left the league <b>{name}</b>.",
        "league.not_member": "❗ You're not a member of this league.",
        "league.leaderboard_title": "👥 <b>{name}</b>\nCode: <code>{code}</code>\n\n",
        "league.leaderboard_empty": "No points in this league yet: the first correct answer opens the standings.",
        "league.not_registered": "❗ Sign up with /start before using leagues.",
        "league.button_invite": "🔗 Invite",
        "cmd.league_create": "Create a private league",
        "cmd.league_join": "Join a league with its code",
    },
}
