"""L'ordine delle tappe segue la convenzione di Wikipedia: il prestito sta sotto il club
che possiede il cartellino, non dove lo mette l'anno di inizio da solo."""
from services.career_order import order_career
from services.player_pool import get_all_players


def teams(career):
    return [(stop["team"], bool(stop.get("loan"))) for stop in career]


def test_loan_goes_after_the_club_that_owns_the_player():
    """Il caso Biabiany: Inter dal 2007 al 2010, in prestito al Chievo nel 2007-2008.
    Ordinando per solo anno di inizio i due 2007 vanno a pari merito e il prestito finiva
    davanti all'Inter."""
    career = [
        {"team": "Chievo", "start_year": 2007, "end_year": 2008, "loan": True},
        {"team": "Inter", "start_year": 2007, "end_year": 2010},
        {"team": "Modena", "start_year": 2008, "end_year": 2009, "loan": True},
    ]
    assert teams(order_career(career)) == [("Inter", False), ("Chievo", True), ("Modena", True)]


def test_loan_stays_before_a_new_contract_of_the_same_year():
    """Il caso Anelka: nel 2013 e' in prestito alla Juventus **dallo Shanghai Shenhua** e
    solo dopo firma con il West Bromwich. Qui il prestito precede il contratto dello stesso
    anno, quindi la regola non puo' essere "prima i contratti, poi i prestiti"."""
    career = [
        {"team": "Shanghai Shenhua", "start_year": 2012, "end_year": 2013},
        {"team": "Juventus", "start_year": 2013, "end_year": 2013, "loan": True},
        {"team": "West Bromwich Albion", "start_year": 2013, "end_year": 2014},
    ]
    assert teams(order_career(career)) == [
        ("Shanghai Shenhua", False),
        ("Juventus", True),
        ("West Bromwich Albion", False),
    ]


def test_loan_to_the_club_that_then_buys_the_player_keeps_its_place():
    """Eto'o al Maiorca: prima il prestito, poi il contratto vero con lo stesso club.
    Il club non va mai portato davanti al proprio prestito."""
    career = [
        {"team": "Real Madrid", "start_year": 1997, "end_year": 2000},
        {"team": "Maiorca", "start_year": 2000, "end_year": 2000, "loan": True},
        {"team": "Maiorca", "start_year": 2000, "end_year": 2004},
    ]
    assert teams(order_career(career)) == [
        ("Real Madrid", False),
        ("Maiorca", True),
        ("Maiorca", False),
    ]


def test_stops_out_of_order_are_put_back_in_chronological_order():
    career = [
        {"team": "B", "start_year": 2010, "end_year": 2014},
        {"team": "A", "start_year": 2005, "end_year": 2010},
    ]
    assert teams(order_career(career)) == [("A", False), ("B", False)]


def test_incomplete_stops_are_left_alone():
    """Senza anno di inizio non si puo' ordinare niente: meglio lasciare le tappe come le ha
    scritte chi ha compilato la scheda (validate_player segnala gia' il dato mancante)."""
    career = [
        {"team": "B", "start_year": None},
        {"team": "A", "start_year": 2005, "end_year": 2010},
    ]
    assert teams(order_career(career)) == [("B", False), ("A", False)]


def test_order_career_does_not_touch_the_original_list():
    career = [
        {"team": "Chievo", "start_year": 2007, "end_year": 2008, "loan": True},
        {"team": "Inter", "start_year": 2007, "end_year": 2010},
    ]
    order_career(career)
    assert teams(career) == [("Chievo", True), ("Inter", False)]


def test_dataset_is_already_in_the_canonical_order():
    """Il dataset e' stato normalizzato una volta: se un import futuro rimette un prestito
    davanti al suo club, questo test lo dice subito."""
    for player in get_all_players() + get_all_players(practice_only=True):
        career = player["career"]
        assert teams(order_career(career)) == teams(career), player["id"]
