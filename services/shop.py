"""Il negozio dei cosmetici, senza Telegram e senza Firestore.

Sta qui e non dentro gli handler per la stessa ragione di services/game.py: il negozio si
apre da **due posti** (il comando /shop in chat e la scheda della mini app) e le due strade
devono vendere lo stesso catalogo alle stesse condizioni. Se "ce l'ho gia'" lo decidesse
l'handler, la mini app avrebbe la sua versione della regola e prima o poi le due
divergerebbero - di solito su un pacchetto comprato a meta'.

**La regola che non si tocca**: qui dentro non si vende niente che cambi la partita. Nessun
tentativo in piu', nessun indizio gratis, nessun punto. Solo colori, cornici, titoli,
distintivi e i simboli della card da condividere. Un vantaggio comprabile trasformerebbe la
classifica nella vetrina di chi ha speso, e a quel punto il gioco non e' piu' lo stesso per
chi non spende - che sono quasi tutti.

Il catalogo e' contenuto (data/shop.json) e non codice: prezzi e nomi si ritoccano senza
toccare un .py e senza un deploy diverso da quello dei calciatori.
"""
import hashlib
import hmac
import json
import logging
import os

from config import BOT_TOKEN
from services import firebase_service, trophies
from services.dates import parse_iso, today_iso
from services.i18n import DEFAULT_LANGUAGE

SHOP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shop.json")

# I tipi di cosmetico, nell'ordine in cui si mostrano. Uno per "slot": si tiene equipaggiato
# un oggetto per tipo, e il tipo e' anche quello che dice **dove** si vede.
#
# I cinque **fondamentali** ci sono da sempre e una collezione li riempie tutti: sono quelli
# che disegnano una persona - tema, cornice, titolo, distintivo - e la sua card. I tre in
# fondo sono arrivati dopo e una collezione puo' averli o no: un numero di maglia o un
# festeggiamento non stanno addosso a ogni mondo, e inventarne uno per ogni set vorrebbe dire
# riempire il catalogo di roba senza intenzione.
CORE_KINDS = ("theme", "frame", "title", "badge", "squares")
EXTRA_KINDS = ("number", "celebration", "card")
KINDS = CORE_KINDS + EXTRA_KINDS

# Prefisso del payload dell'invoice. Telegram ce lo restituisce dentro `successful_payment`,
# ed e' l'unica cosa che lega il pagamento all'oggetto comprato.
PAYLOAD_PREFIX = "cosmetic"

# Limiti di Telegram per una fattura in Stelle: sotto 1 non esiste, e un prezzo assurdo
# vorrebbe dire un errore nel catalogo, non un oggetto costoso.
MIN_STARS = 1
MAX_STARS = 2500

# Le fasce di rarita', dal prezzo in su. Non sono un dato in piu' da tenere allineato a mano:
# si ricavano dal prezzo, cosi' non possono mentire. Un oggetto puo' comunque dichiarare la
# sua (`rarity` in data/shop.json) quando la fascia del prezzo non racconta quello che e':
# una figurina che esiste solo dentro una collezione costa zero da sola, e "gratuita" e'
# esattamente il contrario di quello che vuol dire.
RARITY_BANDS = (("common", 15), ("rare", 30), ("collector", MAX_STARS))
RARITIES = ("free", "earned", "common", "rare", "collector")

_catalogue = None


def _load():
    global _catalogue
    if _catalogue is None:
        with open(SHOP_PATH, encoding="utf-8") as f:
            _catalogue = json.load(f)
    return _catalogue


def reload_catalogue():
    """Rilegge data/shop.json. Serve ai test e alla dashboard locale; in produzione il
    catalogo si carica una volta sola, come il dataset dei calciatori."""
    global _catalogue
    _catalogue = None
    return _load()


def all_items():
    return _load().get("items", [])


def get_item(item_id):
    return next((item for item in all_items() if item.get("id") == item_id), None)


def items_of_kind(kind):
    return [item for item in all_items() if item.get("kind") == kind]


def bundles():
    return sorted(items_of_kind("bundle"), key=lambda item: not item.get("featured", False))


# ---------------------------------------------------------------------------
# Cosa ha e cosa indossa un utente
# ---------------------------------------------------------------------------

def is_free(item):
    """Compreso nel gioco: lo hanno tutti senza comprarlo.

    `locked` distingue il gratuito dal "non in vendita da solo": il titolo Sostenitore
    costa 0 perche' non ha un prezzo suo, ma arriva **solo** dentro il pacchetto. Senza
    questa distinzione lo avrebbero tutti dal primo giorno."""
    return (not item.get("locked") and not item.get("achievement") and not item.get("completes")
            and not item.get("trophy") and int(item.get("price", 0) or 0) <= 0)


def rarity_of(item):
    """La fascia di un oggetto: quella dichiarata se c'e', altrimenti quella del prezzo."""
    declared = (item or {}).get("rarity")
    if declared in RARITIES:
        return declared
    if not item:
        return "free"
    if item.get("achievement") or item.get("completes") or item.get("trophy"):
        return "earned"
    price = int(item.get("price", 0) or 0)
    if price <= 0:
        return "free"
    for name, ceiling in RARITY_BANDS:
        if price <= ceiling:
            return name
    return "collector"


def free_ids():
    return {item["id"] for item in all_items() if is_free(item)}


def default_item_id(kind):
    """L'oggetto di partenza di uno slot: il primo gratuito di quel tipo.

    Esiste per forza (data/shop.json ne ha uno per tipo) e serve a non avere mai uno slot
    vuoto da gestire come caso speciale nella pagina."""
    return next((item["id"] for item in items_of_kind(kind) if is_free(item)), None)


def default_equipped():
    return {kind: default_item_id(kind) for kind in KINDS}


def _cosmetics(user):
    return (user or {}).get("cosmetics") or {}


def reached_ids(user):
    """I traguardi che i contatori di questo utente raggiungono **adesso**.

    E' un calcolo, quindi segue i contatori in tutte e due le direzioni: da solo non basta a
    dire che un traguardo e' di qualcuno, perche' basta alzare un obiettivo in data/shop.json
    per farlo tornare indietro. Serve a sapere quando scatta, non a possederlo."""
    return {item["id"] for item in all_items() if item.get("achievement") and
            int((user or {}).get(item["achievement"]["field"], 0) or 0) >= item["achievement"]["target"]}


def earned_ids(user):
    """I traguardi gia' messi al sicuro sul documento utente.

    Questi non si tolgono piu': un traguardo e' una cosa che e' successa, e un obiettivo
    ritoccato mesi dopo non puo' far sparire un distintivo che qualcuno aveva addosso."""
    return {item_id for item_id in (_cosmetics(user).get("earned") or []) if get_item(item_id)}


def newly_earned(user):
    """Cosa c'e' da scrivere adesso: raggiunto ma non ancora al sicuro.

    Lo chiama firebase_service nel punto in cui i contatori si muovono, cioe' l'unico momento
    in cui un traguardo puo' scattare."""
    return sorted(reached_ids(user) - earned_ids(user))


def podium_ids(user):
    """Gli oggetti che si sbloccano con un piazzamento sul podio.

    `"trophy": {"position": 3}` vuol dire "sei arrivato almeno terzo, da qualche parte":
    un primo posto soddisfa anche la richiesta di un terzo, non il contrario. Sono l'unico
    modo di avere certe cose, e servono a dire che nel negozio non tutto si compra."""
    won = trophies.positions(user)
    return {item["id"] for item in all_items() if item.get("trophy")
            and any(position <= item["trophy"]["position"] for position in won)}


def _base_owned(user):
    owned = set(_cosmetics(user).get("owned") or [])
    return (free_ids() | reached_ids(user) | earned_ids(user) | podium_ids(user)
            | {item_id for item_id in owned if get_item(item_id)})


def completed_ids(user, owned=None):
    """I premi di completamento gia' meritati: quelli la cui collezione e' tutta li'.

    Non si scrivono da nessuna parte, a differenza dei traguardi, ed e' voluto: un premio di
    completamento **e'** la collezione completa, non un fatto avvenuto una volta. Se un
    rimborso toglie un pezzo la collezione non e' piu' completa, e il premio se ne va con
    essa - che e' esattamente quello che deve succedere."""
    owned = _base_owned(user) if owned is None else owned
    return {item["id"] for item in all_items()
            if item.get("completes") and all(one in owned for one in item["completes"])}


def missing_for(user, item):
    """Cosa manca per meritarsi un premio di completamento."""
    owned = _base_owned(user)
    return [one for one in (item or {}).get("completes") or [] if one not in owned]


def owned_ids(user):
    """Tutto quello che questo utente puo' indossare: il gratuito, il guadagnato, il comprato.

    I gratuiti non si scrivono sul documento utente: sono gratuiti per definizione, e
    scriverli vorrebbe dire dover ripassare su tutti gli utenti ogni volta che se ne
    aggiunge uno. I traguardi invece si scrivono, e qui compaiono da due parti: quelli scritti
    (`earned_ids`) e quelli che i contatori raggiungono in questo momento (`reached_ids`). Il
    secondo insieme e' la rete per chi ha guadagnato un traguardo prima che li scrivessimo e
    non ha ancora rigiocato: alla prima partita utile passa nel primo e ci resta.

    I premi di completamento si calcolano **dopo** tutto il resto e non possono premiare a
    loro volta il possesso di un altro premio: un premio che ne sblocca un altro sarebbe una
    catena da srotolare, e c'e' un test che lo vieta."""
    base = _base_owned(user)
    return base | completed_ids(user, base)


def equipped(user):
    """Cosa indossa, slot per slot, gia' ripulito.

    Un id che non esiste piu' nel catalogo, o che l'utente non possiede (un rimborso gli ha
    tolto un oggetto che aveva addosso), torna al valore di partenza: la pagina non deve mai
    trovarsi a disegnare un tema che non c'e'."""
    saved = _cosmetics(user).get("equipped") or {}
    owned = owned_ids(user)
    result = {}
    for kind in KINDS:
        item_id = saved.get(kind)
        item = get_item(item_id) if item_id else None
        if not item or item.get("kind") != kind or item_id not in owned:
            item_id = default_item_id(kind)
        result[kind] = item_id
    return result


def style_of(user, kind):
    """Lo `style` dell'oggetto indossato in questo slot: colori del tema, gradiente della
    cornice, emoji del distintivo, simboli dei quadratini."""
    item = get_item(equipped(user).get(kind))
    return (item or {}).get("style") or {}


def badge_emoji(user):
    """L'emoji da mettere accanto al nome nelle classifiche. Stringa vuota se non ne ha."""
    return style_of(user, "badge").get("emoji") or ""


def squares_symbols(user):
    """I tre simboli della card da condividere, come li vuole services/share.py.

    Se manca qualcosa si ripiega sui quadratini classici pezzo per pezzo: una card mezza
    vuota e' peggio di una card senza personalizzazione."""
    style = style_of(user, "squares")
    fallback = get_item(default_item_id("squares")).get("style", {})
    return (
        style.get("correct") or fallback.get("correct"),
        style.get("wrong") or fallback.get("wrong"),
        style.get("unused") or fallback.get("unused"),
    )


def title_label(user, lang=DEFAULT_LANGUAGE):
    """Il titolo sotto il nome, gia' nella lingua giusta. Stringa vuota se non ne ha uno."""
    style = style_of(user, "title")
    label = style.get("label") or ""
    if not label:
        return ""
    return (style.get("label_i18n") or {}).get(lang) or label


# ---------------------------------------------------------------------------
# Comprare
# ---------------------------------------------------------------------------

def grants_of(item):
    """Cosa consegna un acquisto: un pacchetto consegna la sua lista, tutto il resto se
    stesso. Gli id inesistenti si scartano qui, cosi' un errore di battitura nel catalogo
    non finisce sul documento di un utente."""
    if not item:
        return []
    ids = item.get("grants") if item.get("kind") == "bundle" else [item.get("id")]
    return [item_id for item_id in (ids or []) if get_item(item_id)]


def purchase_status(user, item_id):
    """Se questo utente puo' comprare questo oggetto, e altrimenti perche' no.

    Un pacchetto resta comprabile finche' **almeno un pezzo** manca: chi ha gia' il tema
    Neon e compra il Pacchetto Neon prende gli altri tre, e va bene cosi'. Se invece li ha
    tutti, il pacchetto e' esaurito: farglielo pagare per non dargli niente sarebbe una
    fregatura, e il rimborso lo dovremmo fare a mano."""
    item = get_item(item_id)
    if not item:
        return "unknown_item"
    price = int(item.get("price", 0) or 0)
    if item.get("locked") or price <= 0:
        return "not_for_sale"
    # L'oggetto di benvenuto: si compra una volta sola, e solo prima di aver comprato
    # qualunque altra cosa. Il salto che conta non e' fra due prezzi, e' fra zero e il primo
    # pagamento; dopo, un oggetto a una stella sarebbe solo un oggetto svenduto.
    if item.get("first_purchase_only") and _cosmetics(user).get("owned"):
        return "welcome_only"
    if not (MIN_STARS <= price <= MAX_STARS):
        logging.error(f"[SHOP] Prezzo fuori scala per {item_id}: {price} stelle")
        return "not_for_sale"

    owned = owned_ids(user)
    if all(granted in owned for granted in grants_of(item)):
        return "already_owned"
    return "ok"


def price_for(user, item):
    """Prorate the bundle by the value of missing pieces, rounded up to whole Stars.

    Exclusive pieces use the mean price of the other pieces as their weight.
    A fully owned bundle costs zero and is never offered for purchase.
    """
    if item.get("kind") != "bundle":
        return item["price"]
    pieces = [get_item(one) for one in grants_of(item)]
    owned = owned_ids(user)
    prices = [piece["price"] for piece in pieces if piece["price"] > 0]
    exclusive_weight = max(1, sum(prices) // max(1, len(prices)))
    weights = [piece["price"] or exclusive_weight for piece in pieces]
    remaining = sum(weight for piece, weight in zip(pieces, weights) if piece["id"] not in owned)
    total = sum(weights)
    return (item["price"] * remaining + total - 1) // total if total else 0


def payment_payload(user_id, user, item):
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is required to sign a payment quote")
    granted = grants_of(item)
    owned = owned_ids(user)
    mask = sum(1 << i for i, item_id in enumerate(granted) if item_id not in owned)
    body = f"cosmetic2:{item['id']}:{user_id}:{price_for(user, item)}:{mask:x}"
    signature = hmac.new(BOT_TOKEN.encode(), body.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{body}:{signature}"


def payment_quote(payload):
    if not BOT_TOKEN:
        return None
    parts = (payload or "").split(":")
    if len(parts) != 6 or parts[0] != "cosmetic2":
        return None
    body = ":".join(parts[:5])
    signature = hmac.new(BOT_TOKEN.encode(), body.encode(), hashlib.sha256).hexdigest()[:20]
    if not hmac.compare_digest(signature, parts[5]):
        return None
    try:
        item = get_item(parts[1])
        if not item:
            return None
        ids = grants_of(item)
        mask = int(parts[4], 16)
        if mask <= 0 or mask >= 1 << len(ids):
            return None
        return {"item_id": parts[1], "user_id": int(parts[2]), "price": int(parts[3]),
                "granted": [one for i, one in enumerate(ids) if mask & (1 << i)]}
    except (ValueError, TypeError):
        return None


def payload_for(user_id, item_id):
    """Il payload che viaggia con la fattura e torna indietro col pagamento.

    Ci sta dentro anche l'id dell'utente: `successful_payment` arriva sempre dalla chat di
    chi ha pagato, quindi non e' li' che serve - serve a poter leggere una fattura vecchia
    (o un rimborso) e sapere di chi era, senza cercarla."""
    return f"{PAYLOAD_PREFIX}:{item_id}:{user_id}"


def parse_payload(payload):
    """(item_id, user_id) da un payload, o (None, None) se non e' uno dei nostri.

    Non alza: un pagamento con un payload che non riconosciamo non deve far cadere il
    webhook, deve solo essere rifiutato."""
    if (payload or "").startswith("cosmetic2:"):
        quote = payment_quote(payload)
        return (quote["item_id"], quote["user_id"]) if quote else (None, None)
    parts = (payload or "").split(":")
    if len(parts) != 3 or parts[0] != PAYLOAD_PREFIX:
        return None, None
    try:
        return parts[1], int(parts[2])
    except (TypeError, ValueError):
        return None, None


def equip_status(user, item_id):
    """Se questo utente puo' indossare questo oggetto, e altrimenti perche' no."""
    item = get_item(item_id)
    if not item:
        return "unknown_item"
    if can_wear_bundle(item):
        return "ok" if all(one in owned_ids(user) for one in grants_of(item)) else "not_owned"
    if item.get("kind") not in KINDS:
        return "not_equippable"   # i pacchetti non si indossano, si aprono
    if item_id not in owned_ids(user):
        return "not_owned"
    return "ok"


def can_wear_bundle(item):
    if not item or item.get("kind") != "bundle":
        return False
    kinds = [get_item(one)["kind"] for one in grants_of(item)]
    return bool(kinds) and len(kinds) == len(set(kinds)) and set(kinds) <= set(KINDS)


# ---------------------------------------------------------------------------
# Il catalogo come lo vede una persona
# ---------------------------------------------------------------------------

def localize(item, lang=DEFAULT_LANGUAGE):
    """Nome e descrizione nella lingua dell'utente, con l'italiano come ripiego: stessa
    regola dei nomi degli eventi (services/i18n.py, `content_text`)."""
    name = (item.get("name_i18n") or {}).get(lang) or item.get("name") or item.get("id")
    description = (item.get("description_i18n") or {}).get(lang) or item.get("description") or ""
    return name, description


def _card(item, user, lang, worn):
    name, description = localize(item, lang)
    owned = owned_ids(user)
    granted = grants_of(item)
    return {
        "id": item["id"],
        "kind": item.get("kind"),
        "name": name,
        "description": description,
        "price": price_for(user, item),
        "full_price": int(item.get("price", 0) or 0),
        "missing": [one for one in granted if one not in owned],
        "achievement": item.get("achievement"),
        "progress": min(int((user or {}).get((item.get("achievement") or {}).get("field"), 0) or 0),
                        (item.get("achievement") or {}).get("target", 0)),
        "style": item.get("style") or {},
        "grants": granted if item.get("kind") == "bundle" else [],
        "owned": all(one in owned for one in granted) if granted else item["id"] in owned,
        "equipped": worn.get(item.get("kind")) == item["id"],
        "free": is_free(item),
        "featured": bool(item.get("featured")),
        "equippable": item.get("kind") in KINDS or can_wear_bundle(item),
        "rarity": rarity_of(item),
        # Un premio di completamento: cosa serve e cosa manca ancora, coi nomi gia' tradotti
        # perche' e' quello che la pagina deve scrivere.
        "completes": [{"id": one, "name": localize(get_item(one), lang)[0], "owned": one in owned}
                      for one in item.get("completes") or []],
        "trophy": item.get("trophy"),
        "welcome": bool(item.get("first_purchase_only")),
    }


def appearance(user, lang=DEFAULT_LANGUAGE):
    """Come si deve vedere questo utente: i valori gia' pronti, non gli id.

    Viaggia col profilo e non con il catalogo perche' serve **subito**, al primo disegno
    della pagina: se il tema arrivasse solo aprendo il negozio, chi ha comprato Neon
    vedrebbe un lampo di blu ad ogni apertura."""
    worn = equipped(user)
    return {
        "equipped": worn,
        "theme": style_of(user, "theme"),
        "frame": style_of(user, "frame"),
        "badge": badge_emoji(user),
        "squares": style_of(user, "squares"),
        "title": {"label": title_label(user, lang), "color": style_of(user, "title").get("color") or ""},
        # Il numero di maglia e' una stringa e non un intero apposta: "01" e "1" sono due
        # cose diverse addosso a una maglia, e chi disegna non deve fare i conti.
        "number": style_of(user, "number").get("number") or "",
        "celebration": style_of(user, "celebration").get("effect") or "",
        "card": style_of(user, "card"),
    }


def showcase_week(day_iso=None):
    """La settimana ISO di un giorno, come chiave stabile della vetrina."""
    year, week, _ = parse_iso(day_iso or today_iso()).isocalendar()
    return f"{year}-W{week:02d}"


def weekly_showcase(user, lang=DEFAULT_LANGUAGE, day_iso=None, size=3):
    """I tre oggetti in vetrina questa settimana.

    E' **la stessa per tutti**: una vetrina personalizzata sarebbe solo un altro modo di
    ordinare il catalogo, mentre il senso di una vetrina e' che due persone nello stesso
    gruppo vedano la stessa cosa nello stesso momento. Si ricava dalla settimana con un
    hash, quindi non c'e' niente da scrivere, niente da far girare a mezzanotte e niente che
    possa restare indietro.

    Gli oggetti gia' posseduti restano dentro, marcati come tali: toglierli farebbe cambiare
    la vetrina a chi compra, e una vetrina che si accorcia mentre la guardi e' una vetrina
    rotta."""
    week = showcase_week(day_iso)

    def shuffled(values, salt=""):
        return sorted(values, key=lambda one: hashlib.sha256(f"{week}:{salt}:{one}".encode()).hexdigest())

    # Uno per tipo, e i tipi a rotazione: tre quadratini in fila sono un elenco, non una
    # vetrina. La varieta' e' il motivo per cui questa scelta non e' un semplice `[:3]`.
    buyable: dict[str, list[str]] = {}
    for item in all_items():
        if item.get("kind") in KINDS and purchase_status({}, item["id"]) == "ok":
            buyable.setdefault(item["kind"], []).append(item["id"])
    if not buyable:
        return {"week": week, "items": []}

    worn = equipped(user)
    picked = [shuffled(buyable[kind], kind)[0] for kind in shuffled(sorted(buyable))[:size]]
    return {"week": week,
            "items": [_card(get_item(one), user, lang, worn) for one in picked]}


def catalogue_for(user, lang=DEFAULT_LANGUAGE):
    """Il negozio dal punto di vista di un utente: cosa c'e', cosa ha gia', cosa indossa.

    E' la **stessa** struttura per la mini app e per il comando in chat, cosi' le due
    vetrine non possono raccontare due cose diverse. Gli oggetti `locked` non compaiono da
    soli: si vedono solo dentro il pacchetto che li contiene."""
    worn = equipped(user)
    sections = []
    for kind in KINDS:
        cards = [_card(item, user, lang, worn) for item in items_of_kind(kind)
                 if not item.get("locked") or item["id"] in owned_ids(user)]
        if cards:
            sections.append({"kind": kind, "items": cards})

    packs = [_card(item, user, lang, worn) for item in bundles()]
    for pack in packs:
        pack["contents"] = [
            _card(get_item(item_id), user, lang, worn) for item_id in pack["grants"]
        ]
    return {
        "sections": sections,
        "bundles": packs,
        # La vetrina viaggia con la vetrina: e' la stessa risposta, e un giro in piu' solo
        # per tre oggetti sarebbe un giro in piu' ad ogni apertura del negozio.
        "showcase": weekly_showcase(user, lang),
        "equipped": worn,
        "owned": sorted(owned_ids(user)),
        "looks": _cosmetics(user).get("looks", []),
    }


# ---------------------------------------------------------------------------
# Le due azioni che scrivono
#
# Stanno qui e non negli handler perche' il negozio si apre da due posti: il comando in chat
# e la scheda della mini app devono applicare la stessa regola prima di scrivere, non due
# copie della stessa regola.
# ---------------------------------------------------------------------------

def equip(user_id, user, item_id):
    """Indossa un oggetto gia' posseduto. Ritorna 'ok' o il motivo del rifiuto."""
    status = equip_status(user, item_id)
    if status == "ok":
        item = get_item(item_id)
        if item["kind"] == "bundle":
            firebase_service.equip_look(user_id, {get_item(one)["kind"]: one for one in grants_of(item)})
        else:
            firebase_service.equip_cosmetic(user_id, item["kind"], item_id)
    return status


def save_look(user_id, user, name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 30:
        return "invalid_name"
    looks = list(_cosmetics(user).get("looks", []))
    name = name.strip()
    looks = [look for look in looks if look["name"] != name]
    if len(looks) >= 5:
        return "look_limit"
    looks.append({"name": name, "equipped": equipped(user)})
    firebase_service.save_looks(user_id, looks)
    return "ok"


def use_look(user_id, user, name):
    look = next((look for look in _cosmetics(user).get("looks", []) if look["name"] == name), None)
    if not look:
        return "unknown_item"
    slots = look.get("equipped", {})
    if set(slots) != set(KINDS) or any(equip_status(user, one) != "ok" or get_item(one)["kind"] != kind
                                     for kind, one in slots.items()):
        return "not_owned"
    firebase_service.equip_look(user_id, slots)
    return "ok"


def deliver(user_id, item_id, charge_id, stars, granted=None):
    """Consegna quello che un pagamento ha comprato.

    Volutamente **senza** ricontrollare `purchase_status`: qui il pagamento e' gia' avvenuto,
    e rifiutare adesso vorrebbe dire tenersi le Stelle senza dare niente. Il controllo si fa
    prima, sulla pre-checkout query, che e' il momento in cui Telegram accetta un no.

    Ritorna True se ha consegnato adesso, False se quel pagamento era gia' stato consegnato
    (Telegram rispedisce l'update se il webhook non ha risposto in tempo)."""
    item = get_item(item_id)
    if not item:
        logging.error(f"[SHOP] Pagamento {charge_id} per un oggetto sconosciuto: {item_id}")
        return False
    return firebase_service.deliver_purchase(user_id, charge_id, item_id,
                                             grants_of(item) if granted is None else granted, stars)
