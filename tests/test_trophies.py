"""I trofei come targhe da profilo: come si leggono, come si ordinano, cosa si puo' appendere."""
import pytest

from services import firebase_service, trophies


def user(*codes, pinned=None):
    return {"trophies": list(codes), "cosmetics": {"pinned": list(pinned or [])}}


# ---------------------------------------------------------------------------
# Leggere un codice
# ---------------------------------------------------------------------------

def test_an_event_trophy_takes_its_name_from_the_template_that_generated_it():
    """Il codice porta l'id del template, non il nome: il nome sta in
    data/event_templates.json ed e' l'unico posto dove e' anche tradotto."""
    tag = trophies.parse("1_giramondo_20260907", "it")
    assert tag["kind"] == "event"
    assert tag["position"] == 1
    assert tag["medal"] == "🥇"
    assert tag["label"] == "Giramondo"
    assert tag["detail"] == "07/09/2026"
    assert trophies.parse("1_giramondo_20260907", "en")["label"] == "Globetrotters"


def test_an_event_id_with_underscores_is_not_split_by_counting_the_pieces():
    """`un_amore_una_maglia` sono quattro pezzi da solo: il codice si legge dalla posizione
    davanti e dal giorno in fondo, non contando i trattini bassi."""
    tag = trophies.parse("2_un_amore_una_maglia_20260907", "it")
    assert tag["label"] == "Un amore, una maglia"
    assert tag["position"] == 2


def test_a_template_that_no_longer_exists_still_gets_a_readable_name():
    """I template si tolgono, i trofei restano: chi lo ha vinto non deve ritrovarsi un
    codice al posto di un nome."""
    assert trophies.parse("3_una_vecchia_gara_20240101")["label"] == "Una vecchia gara"


def test_a_monthly_trophy_reads_the_month_in_the_right_language():
    assert trophies.parse("MON_july_3_2026_1", "it")["label"] == "Luglio"
    assert trophies.parse("MON_july_3_2026_1", "en")["label"] == "July"
    assert trophies.parse("MON_july_3_2026_1", "es")["label"] == "Julio"


def test_a_monthly_trophy_carries_its_year_in_the_line_below():
    """L'anno sta in un posto solo: in bacheca i trofei sono gia' raggruppati per anno, e
    ripeterlo nel nome vorrebbe dire leggere "Luglio 2026" sotto il titolo "2026"."""
    tag = trophies.parse("MON_july_3_2026_1", "it")
    assert "2026" not in tag["label"]
    assert "2026" in tag["detail"] and tag["year"] == "2026"


def test_a_position_outside_the_podium_still_gets_a_tag():
    """Il podio oggi e' di tre, ma un trofeo con una posizione diversa esiste sui documenti
    vecchi: deve uscire una targa neutra, non un buco."""
    tag = trophies.parse("7_giramondo_20251201")
    assert tag["medal"] == trophies.DEFAULT_MEDAL
    assert tag["color"] == trophies.DEFAULT_COLOR


@pytest.mark.parametrize("code", [None, "", "boh", "MON_July_2026", "x_giramondo_20260101",
                                  "MON_July_tre_2026_1", "1_giramondo_2026", "1_giramondo",
                                  ["1_giramondo_20260101"], 7])
def test_a_code_that_is_not_one_of_ours_is_ignored_without_raising(code):
    """Un codice storto su un documento vero non deve far cadere il profilo: deve solo
    valere un trofeo in meno."""
    assert trophies.parse(code) is None


def test_the_cabinet_skips_what_it_cannot_read():
    data = user("1_giramondo_20261201", "spazzatura", "MON_July_3_2026_2")
    assert [one["code"] for one in trophies.cabinet(data)] == ["1_giramondo_20261201", "MON_July_3_2026_2"]


def test_the_cabinet_puts_the_best_first_and_the_most_recent_before_the_older():
    data = user("3_giramondo_20241201", "1_sudamerica_20250901", "2_giramondo_20260401", "1_campionato_top_20260201")
    assert [one["code"] for one in trophies.cabinet(data)] == [
        "1_campionato_top_20260201", "1_sudamerica_20250901", "2_giramondo_20260401",
        "3_giramondo_20241201",
    ]


# ---------------------------------------------------------------------------
# Sceglierne tre
# ---------------------------------------------------------------------------

def test_without_a_choice_the_profile_shows_the_best_three():
    data = user("3_giramondo_20241201", "1_sudamerica_20250901", "2_giramondo_20260401", "1_campionato_top_20260201")
    assert [one["code"] for one in trophies.showcase(data)] == [
        "1_campionato_top_20260201", "1_sudamerica_20250901", "2_giramondo_20260401",
    ]


def test_a_choice_is_shown_in_the_order_it_was_made():
    data = user("1_sudamerica_20250901", "3_giramondo_20241201",
                pinned=["3_giramondo_20241201", "1_sudamerica_20250901"])
    assert [one["code"] for one in trophies.showcase(data)] == ["3_giramondo_20241201", "1_sudamerica_20250901"]


def test_a_trophy_that_is_no_longer_there_drops_out_of_the_showcase():
    data = user("1_sudamerica_20250901", pinned=["1_sudamerica_20250901", "9_sparito_20200101"])
    assert [one["code"] for one in trophies.showcase(data)] == ["1_sudamerica_20250901"]


def test_someone_without_trophies_has_nothing_to_show():
    assert trophies.showcase(user()) == []
    assert trophies.cabinet({}) == []
    assert trophies.showcase(None) == []


@pytest.mark.parametrize("codes,expected", [
    (["1_sudamerica_20250901"], "ok"),
    ([], "ok"),
    (["1_sudamerica_20250901", "2_giramondo_20260301"], "ok"),
    (["1_sudamerica_20250901", "1_sudamerica_20250901"], "invalid_choice"),
    (["1_sudamerica_20250901", 7], "invalid_choice"),
    ("1_sudamerica_20250901", "invalid_choice"),
    (["1_campionato_top_20260101"], "not_owned"),
    (["1_sudamerica_20250901", "2_giramondo_20260301", "3_giramondo_20260401",
      "1_sudamerica_20250901"], "too_many"),
])
def test_what_can_and_cannot_be_pinned(codes, expected):
    data = user("1_sudamerica_20250901", "2_giramondo_20260301", "3_giramondo_20260401")
    assert trophies.pin_status(data, codes) == expected


def test_pinning_a_trophy_you_did_not_win_writes_nothing(monkeypatch):
    """La regola sta qui e non nella pagina: la mini app manda dei codici, e un codice
    arrivato dal client non e' una prova di aver vinto niente."""
    written = []
    monkeypatch.setattr(firebase_service, "pin_trophies", lambda uid, codes: written.append(codes))
    data = user("1_sudamerica_20250901")

    assert trophies.pin(42, data, ["1_campionato_top_20260101"]) == "not_owned"
    assert written == []

    assert trophies.pin(42, data, ["1_sudamerica_20250901"]) == "ok"
    assert written == [["1_sudamerica_20250901"]]
