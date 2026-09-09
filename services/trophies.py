"""I trofei come targhe da mettere sul profilo.

Un trofeo esisteva gia' (`users.trophies`), ma viveva dentro una lista dietro un bottone di
/stats: si guadagnava arrivando sul podio di un evento o della classifica mensile e poi non
si vedeva piu'. Qui diventa **una cosa da indossare**: se ne scelgono fino a tre e vanno sul
profilo, accanto al titolo comprato in negozio.

Perche' non e' un cosmetico del negozio, pur finendo nello stesso posto: un cosmetico si
compra e sta in un catalogo fisso (`data/shop.json`, con `get_item` e `owned_ids` che ci
lavorano sopra), un trofeo si vince e il suo "catalogo" e' diverso per ogni utente - e' la
sua bacheca. Farlo passare da `services/shop.py` avrebbe voluto dire un catalogo per utente,
cioe' rompere la cosa che tiene in piedi il negozio. Restano due mondi separati che si
incontrano solo alla fine, quando la pagina disegna.

**Qui dentro non si vende niente e non si sblocca niente**: i trofei li assegna
`firebase_service.update_users_trophies` (podio di un evento) e `handlers/daily_job.py`
(podio del mese). Questo modulo li legge e li mette in fila.

Il codice di un trofeo ha due forme, ed erano gia' cosi' prima:

    MON_July_3_2026_1              classifica mensile: mese, stagione, anno, posizione
    2_un_amore_una_maglia_20260907 evento: posizione, id del template, giorno di chiusura

I codici non si toccano: ci sono documenti veri che li portano, e un rename vorrebbe dire
riscrivere la bacheca di tutti. Vanno pero' letti per quello che sono: l'id di un template
**contiene** trattini bassi (`un_amore_una_maglia`), quindi non si divide contando i pezzi -
si prende la posizione davanti, il giorno in fondo, e in mezzo c'e' l'id qualunque cosa
contenga. Il nome leggibile arriva da data/event_templates.json, che e' anche l'unico posto
dove quel nome e' tradotto.
"""
from services.i18n import DEFAULT_LANGUAGE, content_text, month_label

# Quante targhe stanno sul profilo. Tre perche' e' quanto ne sta su una riga sul telefono
# piu' stretto senza andare a capo, e perche' una bacheca che mostra tutto non e' una scelta:
# il senso di sceglierle e' che dicano qualcosa.
MAX_PINNED = 3

MEDALS = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
DEFAULT_MEDAL = "\U0001f3c5"

# Oro, argento, bronzo. Servono al colore della targa: la posizione si legge dalla medaglia,
# ma da lontano si legge prima il colore.
COLORS = {1: "#e8b647", 2: "#c3ccd6", 3: "#c98652"}
DEFAULT_COLOR = "#8ea2b6"

_SEASON_LABEL = {"it": "Stagione", "en": "Season", "es": "Temporada"}
_MONTHLY_LABEL = {"it": "Classifica mensile", "en": "Monthly leaderboard", "es": "Clasificación mensual"}
_WEEK_LABEL = {"it": "Settimana", "en": "Week", "es": "Semana"}


def _medal(position):
    return MEDALS.get(position, DEFAULT_MEDAL)


def _color(position):
    return COLORS.get(position, DEFAULT_COLOR)


def event_name(template_id, lang=DEFAULT_LANGUAGE):
    """Il nome dell'evento nella lingua giusta, dal template che lo ha generato.

    L'import e' qui dentro e non in cima perche' `event_generator` si porta dietro il pool
    dei calciatori: una pagina di profilo non deve caricarlo per scrivere tre parole.

    Se il template non c'e' piu' (ne sono stati tolti, e i trofei restano) si ripiega sull'id
    reso leggibile: `un_amore_una_maglia` -> `Un amore una maglia`. Meglio di un codice."""
    from services.event_generator import load_templates

    entry = next((one for one in load_templates() if one.get("id") == template_id), None)
    if entry:
        return content_text(entry, "name", lang, default=template_id)
    return template_id.replace("_", " ").strip().capitalize() or template_id


def _is_day(value):
    return len(value) == 8 and value.isdigit()


def parse(code, lang=DEFAULT_LANGUAGE):
    """Un codice trofeo come si disegna, o None se non e' una delle forme che conosciamo.

    Non alza mai: una bacheca con dentro un codice storto non deve far fallire il profilo,
    deve solo mostrare un trofeo in meno."""
    if not isinstance(code, str) or not code:
        return None
    parts = code.split("_")

    if parts[0] == "MON" and len(parts) == 5:
        _, month, season_raw, year, position_raw = parts
        try:
            position, season = int(position_raw), int(season_raw)
        except ValueError:
            return None
        return {
            "code": code,
            "kind": "monthly",
            "position": position,
            "medal": _medal(position),
            "color": _color(position),
            # `handlers/daily_job.py` scrive il mese con `strftime("%B")`, cioe' in inglese e
            # con l'iniziale maiuscola. Il `capitalize` sull'ingresso e' per i codici storici
            # che potrebbero averlo minuscolo: senza, `month_label` non lo riconosce.
            # Il mese e basta: l'anno lo porta gia' la riga sotto, e in bacheca lo porta
            # anche il titolo del gruppo. "Luglio 2026 - 2026" e' quello che si ottiene a
            # metterlo in tutti e due i posti.
            "label": month_label(lang, month.capitalize()).capitalize(),
            "detail": (f"{_MONTHLY_LABEL.get(lang, _MONTHLY_LABEL[DEFAULT_LANGUAGE])} {year} · "
                       f"{_SEASON_LABEL.get(lang, _SEASON_LABEL[DEFAULT_LANGUAGE])} {season}"),
            "year": year,
        }

    if len(parts) >= 3 and parts[0].isdigit() and _is_day(parts[-1]):
        position, day = int(parts[0]), parts[-1]
        return {
            "code": code,
            "kind": "event",
            "position": position,
            "medal": _medal(position),
            "color": _color(position),
            "label": event_name("_".join(parts[1:-1]), lang),
            "detail": f"{day[6:8]}/{day[4:6]}/{day[0:4]}",
            "year": day[0:4],
        }

    return None


def positions(user):
    """Le posizioni dei podi vinti, e basta.

    Esiste separata da `cabinet` perche' il negozio la chiama ad ogni calcolo di cosa uno
    possiede: costruire le targhe vorrebbe dire caricare i template degli eventi (e con
    loro il pool dei calciatori) per leggere un numero che sta gia' davanti al codice."""
    found = set()
    for code in (user or {}).get("trophies") or []:
        if not isinstance(code, str):
            continue
        head = code.split("_")[0]
        if head.isdigit():
            found.add(int(head))
        elif head == "MON" and code.split("_")[-1].isdigit():
            found.add(int(code.split("_")[-1]))
    return found


def cabinet(user, lang=DEFAULT_LANGUAGE):
    """Tutti i trofei di un utente, gia' disegnabili, dal piu' pregiato.

    L'ordine e' posizione prima e anno dopo: una bacheca ordinata per data mette in cima
    l'ultimo terzo posto e in fondo il primo oro, che e' il contrario di quello che uno
    vorrebbe far vedere."""
    parsed = [parse(code, lang) for code in (user or {}).get("trophies") or []]
    found = [one for one in parsed if one]
    return sorted(found, key=lambda one: (one["position"], -int(one["year"] or 0)))


def _pinned_codes(user):
    return ((user or {}).get("cosmetics") or {}).get("pinned") or []


def showcase(user, lang=DEFAULT_LANGUAGE):
    """Le targhe da disegnare sul profilo: quelle scelte, o le migliori se non ha scelto.

    Il ripiego non e' pigrizia: chi ha vinto qualcosa e non ha mai aperto la scelta deve
    vedere comunque la sua targa, altrimenti la funzione esiste solo per chi la scopre."""
    all_of_them = cabinet(user, lang)
    chosen = _pinned_codes(user)
    if not chosen:
        return all_of_them[:MAX_PINNED]
    by_code = {one["code"]: one for one in all_of_them}
    return [by_code[code] for code in chosen if code in by_code][:MAX_PINNED]


def pin_status(user, codes):
    """Se questa scelta si puo' scrivere, e altrimenti perche' no."""
    if not isinstance(codes, list) or any(not isinstance(one, str) for one in codes):
        return "invalid_choice"
    if len(codes) > MAX_PINNED:
        return "too_many"
    if len(set(codes)) != len(codes):
        return "invalid_choice"
    owned = {one["code"] for one in cabinet(user)}
    if any(code not in owned for code in codes):
        return "not_owned"
    return "ok"


def pin(user_id, user, codes):
    """Scrive quali targhe stanno sul profilo. Ritorna 'ok' o il motivo del rifiuto.

    Sta qui e non nell'handler per la stessa ragione del negozio: la scelta si cambia dalla
    mini app e un domani dalla chat, e la regola su cosa si puo' appendere deve essere una
    sola."""
    from services import firebase_service

    status = pin_status(user, codes)
    if status == "ok":
        firebase_service.pin_trophies(user_id, list(codes))
    return status
