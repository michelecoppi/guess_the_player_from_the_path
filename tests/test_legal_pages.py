"""Le due pagine legali (termini e privacy) devono dire le stesse cose in tre lingue.

Non e' pignoleria: sono i due link che Telegram mostra a chi sta per pagare. Una sezione
presente in italiano e assente in spagnolo vuol dire che il bot promette due cose diverse a
due persone diverse, e nessuno se ne accorge finche' non c'e' una contestazione.

Il modo tipico in cui si rompono e' banale: si corregge una frase in una lingua sola, o si
aggiorna la data in cima solo nel blocco che si stava guardando.
"""
import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parent.parent / "webapp"
PAGES = ["terms.html", "privacy.html"]
LANGUAGES = ["it", "es", "en"]


def page(name):
    return (PAGES_DIR / name).read_text(encoding="utf-8")


def blocks(html):
    """Il contenuto di ogni `<article data-lang="xx">`, per lingua."""
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r'<article data-lang="(\w+)">(.*?)</article>', html, re.S)
    }


@pytest.mark.parametrize("name", PAGES)
def test_every_page_exists_in_the_three_languages_of_the_bot(name):
    assert sorted(blocks(page(name))) == sorted(LANGUAGES)


@pytest.mark.parametrize("name", PAGES)
def test_the_three_versions_have_the_same_sections(name):
    """Stesso numero di sezioni numerate in tutte e tre: se una traduzione ne perde una,
    quella lingua sta leggendo un documento diverso."""
    counts = {lang: len(re.findall(r"<h2>", text)) for lang, text in blocks(page(name)).items()}
    assert len(set(counts.values())) == 1, counts


@pytest.mark.parametrize("name", PAGES)
def test_the_update_date_is_the_same_in_every_language(name):
    """Una data aggiornata in una lingua sola e' peggio di una data vecchia: dice a un
    lettore che il documento e' cambiato e all'altro che non e' cambiato."""
    years = {
        lang: set(re.findall(r"\b(20\d\d)\b", re.search(r'class="updated">(.*?)</p>', text, re.S).group(1)))
        for lang, text in blocks(page(name)).items()
    }
    assert len(set(map(frozenset, years.values()))) == 1, years


@pytest.mark.parametrize("name", PAGES)
def test_each_page_points_at_the_other_one(name):
    """Chi apre i termini deve poter arrivare alla privacy senza tornare su BotFather."""
    other = "/privacy" if name == "terms.html" else "/terms"
    for lang, text in blocks(page(name)).items():
        assert other in text, f"{name}/{lang} non rimanda a {other}"


@pytest.mark.parametrize("name", PAGES)
def test_the_stylesheet_they_ask_for_is_the_one_that_exists(name):
    """Le pagine chiedono `/legal.css`, che bot.py serve leggendo `webapp/legal.css`: il
    nome deve combaciare, altrimenti escono senza stile e nessun test se ne accorge."""
    assert 'href="/legal.css"' in page(name)
    assert (PAGES_DIR / "legal.css").exists()


def test_the_terms_say_that_nothing_bought_changes_the_game():
    """La regola del negozio deve stare **anche** nei termini, non solo nel codice: e' quello
    che legge chi sta per pagare, ed e' la promessa che il catalogo mantiene."""
    for lang, text in blocks(page("terms.html")).items():
        lowered = text.lower()
        assert "punt" in lowered or "point" in lowered, lang
        assert "<b>" in text, lang


def test_the_privacy_policy_says_where_the_data_lives():
    """La region non e' un dettaglio: e' quello che rende vera la frase "i dati restano
    nell'Unione Europea". Se un giorno il deploy si sposta, questo test non se ne accorge da
    solo - ma almeno la frase e' in un posto solo e cercabile."""
    for lang, text in blocks(page("privacy.html")).items():
        assert "europe-west1" in text, lang


def test_the_privacy_policy_lists_the_purchase_record():
    """Gli acquisti sono l'unico dato nuovo introdotto dal negozio: se non sono elencati,
    l'informativa descrive un trattamento diverso da quello che il bot fa davvero."""
    for lang, text in blocks(page("privacy.html")).items():
        assert "Stelle" in text or "Estrellas" in text or "Stars" in text, lang


def test_the_privacy_policy_names_the_controller_and_the_real_deletion_command():
    for lang, text in blocks(page("privacy.html")).items():
        assert "Michele Coppi" in text, lang
        assert "/forgetme" in text, lang
