"""Ordine delle tappe di carriera: la convenzione di Wikipedia, non l'ordine per anno.

Un prestito non va dove lo mette l'ordine cronologico puro: va **dopo il contratto che lo
ha generato**. Jonathan Biabiany e' dell'Inter dal 2007 al 2010 e nel 2007-2008 e' in
prestito al Chievo; la sua scheda dice prima Inter e poi Chievo, non il contrario. Ordinando
solo per anno di inizio le due tappe vanno a pari merito e il prestito finisce davanti al
club che lo possiede: e' il difetto che si vedeva nell'immagine del percorso.

Non basta pero' la regola "a parita' di anno prima il contratto, poi il prestito". Anelka
nel 2013 e' in prestito alla Juventus **dallo Shanghai Shenhua** e solo dopo firma con il
West Bromwich, sempre nel 2013: li' il prestito viene prima del contratto dello stesso anno,
perche' appartiene a quello precedente. E Pirlo nel 2001 va in prestito al Brescia mentre e'
ancora dell'Inter, poi passa al Milan: anche li' il prestito precede il contratto del 2001.

La regola che regge tutti questi casi guarda **chi possiede il cartellino in quel momento**:
si scorre la carriera in ordine di anno tenendo da parte l'ultimo contratto vero, e un
prestito si sposta solo quando nessun contratto lo copre ancora. In quel caso il proprietario
e' il contratto dello stesso anno che contiene il prestito, e va portato davanti.
"""


def _contains(contract, loan):
    """True se il periodo di `loan` cade dentro quello di `contract`, cioe' se il prestito
    puo' essere partito da quel club."""
    start = contract.get("start_year")
    end = contract.get("end_year")
    loan_start = loan.get("start_year")
    if not isinstance(start, int) or not isinstance(loan_start, int):
        return False
    if loan_start < start:
        return False
    if end is None:
        # Contratto ancora in corso: copre tutto quello che inizia dopo.
        return True
    loan_end = loan.get("end_year")
    if not isinstance(loan_end, int):
        loan_end = loan_start
    return loan_end <= end


def order_career(career):
    """Le stesse tappe, nell'ordine in cui le scriverebbe Wikipedia. Non tocca gli originali.

    Le tappe senza un anno di inizio numerico restano come sono: sono schede incomplete
    (`validate_player` le segnala gia'), e indovinare un ordine sarebbe peggio che lasciarle
    dove le ha messe chi ha scritto i dati.
    """
    stops = list(career or [])
    if len(stops) < 2:
        return stops
    if any(not isinstance(stop.get("start_year"), int) for stop in stops):
        return stops

    chronological = sorted(stops, key=lambda stop: stop["start_year"])

    queue = list(range(len(chronological)))
    ordered = []
    owner = None  # l'ultimo contratto vero incontrato: il club che ha il cartellino
    while queue:
        index = queue.pop(0)
        stop = chronological[index]

        if stop.get("loan") and (owner is None or not _contains(owner, stop)):
            # Prestito senza un proprietario a monte: il club e' il contratto dello stesso
            # anno che lo contiene (le tappe che iniziano dopo non possono contenerlo, e
            # la lista e' ordinata, quindi basta guardare il gruppo dello stesso anno).
            host_position = None
            for position, other in enumerate(queue):
                candidate = chronological[other]
                if candidate["start_year"] != stop["start_year"]:
                    break
                if candidate.get("loan") or candidate.get("team") == stop.get("team"):
                    # Un prestito allo stesso club che poi lo compra e' sempre il prestito
                    # per primo (Eto'o al Maiorca, Gray al Luton): li' il proprietario e' un
                    # altro club, magari con date imprecise, e non va scavalcato.
                    continue
                if _contains(candidate, stop):
                    host_position = position
                    break
            if host_position is not None:
                queue.insert(0, index)  # il prestito torna in coda, subito dopo il club
                index = queue.pop(host_position + 1)
                stop = chronological[index]

        ordered.append(stop)
        if not stop.get("loan"):
            owner = stop
    return ordered
