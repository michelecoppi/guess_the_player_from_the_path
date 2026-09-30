"""Indizi a pagamento sulla sfida del giorno.

Il confronto dopo un tentativo sbagliato (services/guess_feedback.py) e' **relativo**: dice
"stessa nazionalita'" rispetto al nome che l'utente ha scritto, e quindi non serve a chi non
ha idee. L'indizio invece e' **assoluto** - dice la nazionalita' e basta - ed e' per questo
che costa un punto: e' la differenza fra un aiuto e la risposta regalata.

Tre regole tengono in piedi l'equilibrio, e sono tutte qui o in
`services/repos/users.py` (`hint_refusal`):

1. si sbloccano **uno per ogni tentativo sbagliato** (#277): il primo dopo il primo errore,
   il secondo dopo il secondo. Senza questa condizione l'indizio sarebbe il modo piu'
   comodo per farsi dire nazionalita' e ruolo di ogni sfida senza mai giocare, e un solo
   nome buttato li' li sbloccherebbe tutti;
2. costano **1 punto l'uno**, con un pavimento a 1: chi indovina dopo due indizi su una
   sfida "facile" (che ne vale 1) prende comunque il suo punto, ma nessun bonus striscia in
   piu' di quanto avrebbe preso senza. Non si va mai sotto zero;
3. sono **due al massimo**, e quanti dipende dalla difficolta' (`HINTS_BY_DIFFICULTY`:
   nessuno sulle facili, uno sulle medie). Sono quelli della scala qui sotto. Non e' un numero magico: e'
   quanto si puo' dire senza che la sfida si risolva da sola. La scala e' un dato, quindi
   allungarla (decennio di nascita, iniziale del cognome) e' una riga - ma allungarla vuol
   dire anche rendere piu' facile ogni sfida difficile, che e' una scelta di gioco, non un
   dettaglio tecnico.

Che l'indizio si veda anche nella card condivisa (il 💡 in services/share.py) e' voluto: chi
la incolla in un gruppo dice anche di essersi fatto aiutare.

Le squadre non sono e non saranno mai un indizio: sono gia' tutte nell'immagine.
"""
from services.content_i18n import country_name, position_name
from services.i18n import t

# Le voci in ordine di erogazione. La nazionalita' prima del ruolo perche' e' l'indizio che
# restringe di piu' senza risolvere: i ruoli sono quattro, le nazionalita' cinquanta.
HINT_LADDER = ("nationality", "position")
MAX_HINTS = len(HINT_LADDER)

# Quanti indizi concede ogni difficolta' (#277). Un indizio costa un punto e una sfida "easy"
# ne vale uno solo: col pavimento a 1 sarebbe gratis, quindi li' non ce ne sono. Una "medium"
# (2 punti) ne regge uno, le due piu' dure tutta la scala. Difficolta' sconosciuta: niente,
# come i punti (services/difficulty.py::points_for_difficulty).
HINTS_BY_DIFFICULTY = {"easy": 0, "medium": 1, "hard": MAX_HINTS, "impossible": MAX_HINTS}

# Quanto costa un indizio e sotto quanto non si scende comunque. Il pavimento a 1 serve alle
# sfide "easy", che valgono 1 punto: due indizi le porterebbero a -1.
HINT_COST = 1
MIN_POINTS = 1


def _render(kind, player, lang):
    """Una voce della scala, o None se questa scheda non ha il dato che serve.

    `position` non e' un campo obbligatorio del dataset (services/player_pool.py), quindi il
    caso "non c'e'" e' normale e non un errore: quell'indizio semplicemente non esiste per
    quella sfida."""
    if kind == "nationality":
        value = (player.get("nationality") or "").strip()
        return t(lang, "hint.nationality", value=country_name(value, lang)) if value else None
    if kind == "position":
        value = (player.get("position") or "").strip()
        return t(lang, "hint.position", value=position_name(value, lang)) if value else None
    return None


def build_hints(player, lang):
    """Gli indizi che si possono davvero dare su questa scheda, in ordine.

    Si costruiscono **prima** di consumarne uno: se la scheda non ha niente da dire, l'utente
    non deve pagare un punto per un messaggio vuoto."""
    if not player:
        return []
    rendered = [_render(kind, player, lang) for kind in HINT_LADDER]
    return [hint for hint in rendered if hint]


def hint_limit(difficulty):
    """Quanti indizi si possono chiedere su una sfida di questa difficolta'."""
    return HINTS_BY_DIFFICULTY.get(difficulty, 0)


def points_after_hints(base_points, hints_used):
    """I punti che restano dopo gli indizi chiesti, mai sotto `MIN_POINTS`.

    Si applica solo se si indovina: un indizio su una sfida persa non toglie niente, perche'
    non c'era niente da togliere."""
    if not hints_used:
        return base_points
    return max(base_points - HINT_COST * hints_used, MIN_POINTS)
