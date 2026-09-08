"""Confronto fra il calciatore tentato e la soluzione, dopo una risposta sbagliata.

Prima un tentativo sbagliato restituiva solo "❌, te ne restano due": tre buchi nel vuoto,
e in una giornata difficile l'unica strategia era sparare nomi. Qui invece ogni tentativo
lascia qualcosa, come in Wordle: il confronto e' **relativo al nome che l'utente ha
scritto**, quindi non serve tradurre niente (l'utente sa gia' chi ha detto) e non si rivela
mai la soluzione.

Cosa si confronta, e soprattutto cosa no: le squadre **non** si confrontano. Sono gia'
tutte nell'immagine, dirle sarebbe ripetere quello che si vede. Le informazioni che
l'immagine non da' - e che quindi valgono come indizio - sono nazionalita', ruolo ed eta'.

Il nome tentato viene risolto sul dataset (services/player_pool.py). Se non e' li' dentro,
il confronto non c'e' e il messaggio resta quello di prima: chi vuole usare il bot come
oracolo ("questo calciatore e' nel dataset?") ha tre tentativi al giorno per farlo, che e'
un prezzo abbastanza alto da rendere la cosa inutile.
"""
from services.i18n import t
from services.player_pool import find_player_by_answer, get_player_by_id


def compare_players(guess_player, target_player):
    """Gli indizi come lista di (chiave di traduzione, argomenti).

    Funzione pura: non sa niente di lingue ne' di Firestore, cosi' si prova su due
    dizionari. La resa testuale e' di `comparison_text`."""
    clues: list[tuple[str, dict]] = []

    guess_nationality = (guess_player.get("nationality") or "").strip().lower()
    target_nationality = (target_player.get("nationality") or "").strip().lower()
    if guess_nationality and target_nationality:
        same = guess_nationality == target_nationality
        clues.append(("feedback.nationality_same" if same else "feedback.nationality_diff", {}))

    guess_position = (guess_player.get("position") or "").strip().lower()
    target_position = (target_player.get("position") or "").strip().lower()
    if guess_position and target_position:
        same = guess_position == target_position
        clues.append(("feedback.position_same" if same else "feedback.position_diff", {}))

    guess_birth = guess_player.get("birth_year")
    target_birth = target_player.get("birth_year")
    if isinstance(guess_birth, int) and isinstance(target_birth, int):
        if target_birth == guess_birth:
            clues.append(("feedback.birth_same", {"year": guess_birth}))
        elif target_birth < guess_birth:
            clues.append(("feedback.birth_before", {"year": guess_birth}))
        else:
            clues.append(("feedback.birth_after", {"year": guess_birth}))

    return clues


def build_comparison(user_answer, target_player_id):
    """Il confronto da mostrare, o None se non se ne puo' fare nessuno.

    I casi di None sono tutti legittimi e finiscono nello stesso messaggio di prima:
    - la sfida non porta un `player_id` (le sfide vecchie, prima della revisione del
      database, e quelle a cui l'admin ha cambiato le risposte a mano);
    - il calciatore della sfida non e' piu' nel dataset (id cambiato, scheda rimossa);
    - il nome scritto dall'utente non e' nel dataset;
    - il nome scritto **e'** la soluzione: capita solo se qualcuno ha corretto a mano le
      risposte accettate, e mostrare tre spunte verdi dopo un "sbagliato" confonderebbe e
      basta."""
    if not target_player_id:
        return None

    target = get_player_by_id(target_player_id)
    if not target:
        return None

    guess_player = find_player_by_answer(user_answer)
    if not guess_player or guess_player.get("id") == target.get("id"):
        return None

    clues = compare_players(guess_player, target)
    if not clues:
        return None

    return {"name": guess_player.get("full_name") or guess_player.get("id"), "clues": clues}


def comparison_text(lang, comparison):
    """Il blocco da appendere al messaggio di risposta sbagliata. Stringa vuota se non
    c'e' niente da confrontare, cosi' chi chiama non deve mettere una condizione."""
    if not comparison:
        return ""

    lines = [t(lang, "feedback.header", name=comparison["name"])]
    lines += [t(lang, key, **kwargs) for key, kwargs in comparison["clues"]]
    return "\n\n" + "\n".join(lines)
