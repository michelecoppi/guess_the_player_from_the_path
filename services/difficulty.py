from services.player_pool import load_config

DIFFICULTY_ORDER = ["easy", "medium", "hard", "impossible"]

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

    components = {
        "popularity": (POPULARITY_MAX - popularity) * weights.get("popularity", 4.0),
        "minor_leagues": league_obscurity * weights.get("minor_leagues", 3.0),
        "extra_countries": min(max(len(countries) - 2, 0), 3) * weights.get("extra_countries", 0.5),
        "extra_teams": min(max(len(career) - 5, 0), 5) * weights.get("extra_teams", 0.2),
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
    thresholds = thresholds or config.get("difficulty_thresholds", {"easy": 5, "medium": 9, "hard": 13})

    if score < thresholds["easy"]:
        return "easy"
    if score < thresholds["medium"]:
        return "medium"
    if score < thresholds["hard"]:
        return "hard"
    return "impossible"


def compute_difficulty(player, config=None):
    return bucket_for_score(compute_difficulty_score(player, config=config), config=config)


def explain_difficulty(player, config=None):
    """Scompone il punteggio nei suoi quattro addendi.

    Serve quando una difficolta' sembra sbagliata (il caso tipico: "perche' questo e'
    impossibile?"): mostra subito se a pesare e' la notorieta' o il percorso, senza dover
    rifare i conti a mano. La procedura completa e' in docs/difficolta.md, sezione 5.
    """
    career = player.get("career", [])
    components, league_obscurity, countries = _score_components(player, config=config)
    score = sum(components.values())
    return {
        "score": score,
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
