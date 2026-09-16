import hashlib
import json

from services.player_pool import load_config

DIFFICULTY_ORDER = ["easy", "medium", "hard", "impossible"]

# Il punteggio grezzo (0..21.5 con la taratura attuale) dipende dai pesi: cambiando un peso
# cambia anche la scala, e "9.3" non si confronta piu' con "9.3" di un mese prima. La scala
# 0-100 divide per il massimo che la taratura in vigore puo' produrre, cosi' resta leggibile
# ("73/100") e confrontabile fra tarature diverse. I tetti di ogni addendo sono gli stessi di
# `_score_components`.
COMPONENT_CAPS = {
    "popularity": 4,          # (5 - popularity), popularity 1..5
    "minor_leagues": 1,       # media dei pesi di campionato, 0..1
    "extra_countries": 3,     # paesi oltre i primi due, al massimo 3
    "extra_teams": 5,         # squadre oltre le prime cinque, al massimo 5
}
DEFAULT_WEIGHTS = {"popularity": 4.0, "minor_leagues": 3.0, "extra_countries": 0.5, "extra_teams": 0.2}
DEFAULT_THRESHOLDS = {"easy": 5, "medium": 9, "hard": 13}

# Scala di notorieta' usata in tutto il dataset. La definizione discorsiva, con gli esempi
# e i criteri per assegnarla, sta in docs/difficolta.md: e' il documento di riferimento,
# qui teniamo solo i numeri.
POPULARITY_MIN = 1
POPULARITY_MAX = 5
DEFAULT_POPULARITY = 3

# Peso di una tappa in base al campionato: 0 = top 5 europeo, 1 = campionato che il
# pubblico del bot fatica a collocare. I campionati "noti ma non top" (Eredivisie,
# Primeira Liga, Liga Argentina, Brasileirao, MLS...) stanno in mezzo: Ajax, Porto e Boca
# non possono pesare come una seconda divisione asiatica.
#
# Il peso 1.0 e' insieme una lista (`obscure_leagues` in data/config.json) e il ripiego per
# tutto cio' che non e' in nessuna lista: la funzione qui sotto non ha bisogno di leggerla,
# perche' il risultato sarebbe identico. La lista serve a `services/dataset_health.py`, che
# senza di essa non puo' distinguere un campionato giudicato sconosciuto da uno che nessuno
# ha ancora guardato - ed e' solo il secondo a meritare un avviso.
LEAGUE_TIER_TOP = 0.0
LEAGUE_TIER_KNOWN = 0.5
LEAGUE_TIER_OBSCURE = 1.0


def league_tier_weight(league, top_leagues, known_leagues):
    if league in top_leagues:
        return LEAGUE_TIER_TOP
    if league in known_leagues:
        return LEAGUE_TIER_KNOWN
    return LEAGUE_TIER_OBSCURE


def _score_components(player, config=None):
    """I quattro addendi del punteggio, tenuti in un posto solo.

    Il modello e' volutamente semplice ed e' documentato in docs/difficolta.md:

    - la **notorieta'** (`popularity` 1-5) fissa la fascia di partenza, a passi di 4 punti:
      un pop 5 parte da 0, un pop 1 da 16;
    - il **percorso** (campionati poco noti, paesi, numero di squadre) e' solo un
      modificatore, con un tetto complessivo di 5.5 punti: puo' spostare un giocatore al
      massimo di una fascia, mai di due.

    E' la regola che tiene allineati dataset e difficolta' percepita: una carriera esotica
    non basta a rendere "impossibile" un giocatore famoso (Forlan, Ibrahimovic), e una
    carriera lineare non basta a rendere "facile" un giocatore che nessuno conosce.

    `config` serve solo a simulare una taratura diversa da quella in vigore (la dashboard
    mostra l'effetto di pesi e soglie nuovi **prima** di salvarli in data/config.json):
    lasciato a None si usa la configurazione reale.
    """
    config = config or load_config()
    top_leagues = set(config.get("top_leagues", []))
    known_leagues = set(config.get("known_leagues", []))
    weights = config.get("difficulty_weights", {})
    career = player.get("career", [])
    countries = {entry.get("country") for entry in career if entry.get("country")}
    popularity = player.get("popularity", DEFAULT_POPULARITY)

    # La quota di tappe "esotiche" e' una media, non una somma: una carriera lunga non deve
    # pesare di piu' solo perche' e' lunga (a quello pensa gia', con molta moderazione, il
    # termine sulle squadre).
    league_obscurity = (
        sum(league_tier_weight(entry.get("league"), top_leagues, known_leagues) for entry in career) / len(career)
        if career
        else 0.0
    )

    caps = COMPONENT_CAPS
    components = {
        "popularity": (POPULARITY_MAX - popularity) * weights.get("popularity", DEFAULT_WEIGHTS["popularity"]),
        "minor_leagues": league_obscurity * weights.get("minor_leagues", DEFAULT_WEIGHTS["minor_leagues"]),
        "extra_countries": min(max(len(countries) - 2, 0), caps["extra_countries"])
        * weights.get("extra_countries", DEFAULT_WEIGHTS["extra_countries"]),
        "extra_teams": min(max(len(career) - 5, 0), caps["extra_teams"])
        * weights.get("extra_teams", DEFAULT_WEIGHTS["extra_teams"]),
    }
    return components, league_obscurity, countries


def compute_difficulty_score(player, config=None):
    """Punteggio piu' alto = piu' difficile da indovinare (vedi _score_components)."""
    if not player.get("career"):
        return 0.0
    components, _, _ = _score_components(player, config=config)
    return sum(components.values())


def bucket_for_score(score, thresholds=None, config=None):
    config = config or load_config()
    thresholds = thresholds or config.get("difficulty_thresholds", DEFAULT_THRESHOLDS)

    if score < thresholds["easy"]:
        return "easy"
    if score < thresholds["medium"]:
        return "medium"
    if score < thresholds["hard"]:
        return "hard"
    return "impossible"


def compute_difficulty(player, config=None):
    return bucket_for_score(compute_difficulty_score(player, config=config), config=config)


def max_raw_score(config=None):
    """Il punteggio grezzo piu' alto che la taratura in vigore puo' produrre."""
    config = config or load_config()
    weights = config.get("difficulty_weights", {})
    return sum(cap * weights.get(key, DEFAULT_WEIGHTS[key]) for key, cap in COMPONENT_CAPS.items())


def to_score_100(raw_score, config=None):
    """Punteggio grezzo -> scala 0-100 (una cifra decimale). 0 se la taratura azzera tutto."""
    top = max_raw_score(config)
    if top <= 0:
        return 0.0
    return round(min(max(raw_score / top, 0.0), 1.0) * 100, 1)


def band_cutoffs_100(config=None):
    """Le soglie delle fasce riportate sulla scala 0-100: servono solo a leggerle, le fasce si
    decidono sempre sul grezzo (`bucket_for_score`), cosi' la scala non introduce arrotondamenti."""
    config = config or load_config()
    thresholds = config.get("difficulty_thresholds", DEFAULT_THRESHOLDS)
    return {level: to_score_100(thresholds[level], config) for level in ("easy", "medium", "hard")}


def model_fingerprint(config=None):
    """Impronta breve della taratura che ha prodotto una previsione.

    Due previsioni con la stessa impronta sono state calcolate con gli stessi pesi, soglie e
    liste di campionati: e' cio' che permette di dire, rileggendo lo storico, se una sfida di
    tre mesi fa va confrontata con le altre o se nel frattempo la formula e' cambiata."""
    config = config or load_config()
    relevant = {
        "weights": {key: float(config.get("difficulty_weights", {}).get(key, DEFAULT_WEIGHTS[key]))
                    for key in COMPONENT_CAPS},
        "thresholds": {key: float(value) for key, value in
                       config.get("difficulty_thresholds", DEFAULT_THRESHOLDS).items()},
        "top_leagues": sorted(config.get("top_leagues", [])),
        "known_leagues": sorted(config.get("known_leagues", [])),
    }
    digest = hashlib.sha256(json.dumps(relevant, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:10]


def predict_difficulty(player, config=None):
    """La previsione da fotografare sul documento della sfida (`daily_path.difficulty_prediction`).

    Si salva al momento della generazione perche' dataset e taratura cambiano: senza la foto,
    confrontare la previsione con com'e' andata davvero vorrebbe dire confrontare la giornata
    di mesi fa con la formula di oggi. La fascia qui e' quella **calcolata**: `difficulty` sul
    documento puo' differire se l'admin l'ha corretta a mano, ed e' giusto che resti visibile."""
    config = config or load_config()
    raw = compute_difficulty_score(player, config=config)
    return {
        "score": to_score_100(raw, config),
        "raw_score": round(raw, 3),
        "band": bucket_for_score(raw, config=config),
        "model": model_fingerprint(config),
    }


def explain_difficulty(player, config=None):
    """Scompone il punteggio nei suoi quattro addendi.

    Serve quando una difficolta' sembra sbagliata (il caso tipico: "perche' questo e'
    impossibile?"): mostra subito se a pesare e' la notorieta' o il percorso, senza dover
    rifare i conti a mano. La procedura completa e' in docs/difficolta.md, sezione 5.
    """
    config = config or load_config()
    career = player.get("career", [])
    components, league_obscurity, countries = _score_components(player, config=config)
    score = sum(components.values())
    return {
        "score": score,
        "score_100": to_score_100(score, config),
        "difficulty": bucket_for_score(score, config=config),
        "components": components,
        "popularity": player.get("popularity", DEFAULT_POPULARITY),
        "teams": len(career),
        "countries": len(countries),
        "league_obscurity": league_obscurity,
    }


def group_players_by_difficulty(players):
    groups: dict[str, list] = {level: [] for level in DIFFICULTY_ORDER}
    for player in players:
        groups[compute_difficulty(player)].append(player)
    return groups


def points_for_difficulty(difficulty):
    return {"easy": 1, "medium": 2, "hard": 3, "impossible": 4}.get(difficulty, 0)
