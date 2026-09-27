"""Scritture su molti documenti: a pagine, in parallelo, senza tenere aperto uno stream.

Il modo ingenuo - `for doc in query.stream(): doc.reference.delete()` - ha tre difetti che
si vedono solo sugli account grossi, che sono l'unico posto dove contano:

- una chiamata bloccante per documento, in fila: chi gioca da un anno sono centinaia di
  round-trip dentro un handler Telegram che nel frattempo non risponde;
- lo stream della query resta aperto per tutto il tempo delle scritture che ne derivano, e
  ha una scadenza. Superata, l'iterazione muore a meta' e la cancellazione resta parziale;
- si itera una query mentre si modifica cio' che la query seleziona. Oggi funziona solo
  perche' ogni scrittura fa smettere al documento di combaciare col filtro: un'invariante
  che non e' scritta da nessuna parte e che il prossimo campo aggiunto rompe in silenzio.

Qui la pagina si legge tutta prima di scrivere (lo stream vive il tempo di una lettura), il
cursore su `__name__` avanza sempre - anche quando la scrittura *non* toglie il documento
dal filtro - e le scritture passano da un BulkWriter, che le raggruppa, le manda in
parallelo e le riprova da solo.
"""

PAGE = 200

# Quante volte il BulkWriter riprova una scrittura prima di arrendersi. Di suo ne fa 15, e
# fra un tentativo e l'altro aspetta un secondo in piu' del giro prima: troppo per una
# richiesta che ha un utente dall'altra parte che aspetta la risposta.
RETRIES = 5

# gRPC NOT_FOUND. Su una delete non arriva: cancellare due volte in Firestore va bene. Su
# una update di sgombero significa che il documento da sistemare non c'e' piu', cioe'
# esattamente il risultato che volevamo, e non una scrittura persa. Contarla come errore
# vorrebbe dire che chi era iscritto a una lega poi cancellata non riesce **mai** a portare
# a termine la sua richiesta di cancellazione: fallirebbe uguale a ogni nuovo tentativo.
GONE = 5

# Codici che riprovare non migliora: argomento non valido, gia' esistente, permesso negato,
# precondizione fallita, fuori intervallo, non autenticato. Riprovarli e' solo attesa.
PERMANENT = frozenset({3, 6, 7, 9, 11, 16})


def sweep(query, apply, *, page=None):
    """Applica `apply(writer, snapshot)` a ogni documento di `query`. Torna quanti erano.

    Il numero e' quello dei documenti passati, non delle scritture: `apply` puo' accodarne
    piu' di una per documento. Ed e' un numero onesto solo perche' una scrittura persa qui
    solleva.

    Serve dirlo perche' il BulkWriter non si comporta come il resto del client: `delete()` e
    `update()` tornano subito e non sollevano mai: gli errori finiscono in un callback che
    di default riprova qualche volta e poi **scarta la scrittura in silenzio**. Un log di
    cancellazione che dichiara il falso e' peggio di una cancellazione fallita, perche'
    l'unico modo di accorgersene sarebbe andare a guardare i documenti a mano.
    """
    from services import firebase_service as fs

    # Non un valore di default nella firma: quello si fissa all'import, e una prova che
    # vuole vedere il cursore girare deve poter rimpicciolire la pagina.
    page = page or PAGE
    failures = []

    def on_error(failure, _writer):
        if failure.code == GONE:
            return False
        if failure.code not in PERMANENT and failure.attempts < RETRIES:
            return True
        failures.append(f"{failure.operation.reference.path}: {failure.code} {failure.message}")
        return False

    writer = fs.db.bulk_writer()
    writer.on_write_error(on_error)
    swept = 0
    cursor = None
    try:
        while True:
            paged = query.order_by("__name__").limit(page)
            snapshots = list((paged.start_after(cursor) if cursor else paged).stream())
            for snapshot in snapshots:
                apply(writer, snapshot)
            # Nessun flush a fine pagina, e non e' una dimenticanza. Primo: non servirebbe,
            # perche' il cursore e' su `__name__` e la pagina dopo e' fatta di documenti
            # diversi, che le scritture di questa siano arrivate o no. Secondo, e peggio:
            # `flush()` spegne il suo pool di thread arrivato in fondo, e all'inizio si
            # ferma subito se lo trova spento. Il secondo flush di fila non manderebbe
            # niente e non lo direbbe a nessuno - le scritture in coda resterebbero li' e la
            # spazzata tornerebbe un numero pieno di documenti che non ha toccato. C'e' una
            # prova che lo becca (una spazzata di sette documenti a pagine da tre).
            # Le scritture partono lo stesso, da sole, appena ce n'e' un lotto pieno; per
            # quelle che avanzano c'e' il `close()` qui sotto, che blocca finche' non sono
            # arrivate tutte.
            swept += len(snapshots)
            if len(snapshots) < page:
                break
            cursor = snapshots[-1]
    finally:
        writer.close()
    # Fuori dal `finally`: se stiamo gia' propagando l'errore di una lettura, e' quello a
    # dire cosa e' successo, e sollevare di li' lo sostituirebbe.
    if failures:
        raise RuntimeError(f"{len(failures)} scritture perse: {'; '.join(failures[:3])}")
    return swept
