"""Editor dei template evento (#31): solo template validi arrivano nel file, con backup."""
import json

import pytest

from services import event_generator
from services import event_template_editor as editor
from services.event_config import SCHEMA_VERSION


@pytest.fixture
def templates_file(tmp_path, monkeypatch):
    source = event_generator.load_payload()
    path = tmp_path / "event_templates.json"
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(event_generator, "TEMPLATES_PATH", str(path))
    monkeypatch.setattr(editor, "BACKUP_DIR", str(tmp_path / "backup"))
    event_generator.reload_templates()
    yield path
    event_generator.reload_templates()


def _new_template(**overrides):
    template = json.loads(editor.template_text(None))
    template.update({
        "id": "leggende_mondiali",
        "name": "Leggende dei Mondiali",
        "description": "Campioni famosi.",
        "name_i18n": {"es": "Leyendas", "en": "World Cup legends"},
        "description_i18n": {"es": "Campeones.", "en": "Famous champions."},
        "filters": {"min_popularity": 4},
        "schedule": {"mode": "fixed", "start": "2026-06-11"},
    })
    template.update(overrides)
    return template


def test_the_blank_template_only_needs_texts():
    errors = editor.preview_template(json.loads(editor.template_text(None)))["errors"]
    assert errors and all(e.split(":")[0] in {"name", "description", "name_i18n.es", "name_i18n.en",
                                              "description_i18n.es", "description_i18n.en"} for e in errors)


def test_a_new_template_is_previewed_saved_and_immediately_usable(templates_file):
    template = _new_template()
    preview = editor.preview_template(template)
    assert preview["valid"], preview["errors"]
    assert preview["candidates"] > 0
    assert preview["next_starts"] == ["2026-06-11"]
    assert [day["day"] for day in preview["sample_days"]] == ["2026-06-11", "2026-06-12", "2026-06-13",
                                                              "2026-06-14", "2026-06-15"]

    result = editor.save_template(template)
    assert result["created"] and result["id"] == "leggende_mondiali"
    written = json.loads(templates_file.read_text(encoding="utf-8"))
    assert written["schema_version"] == SCHEMA_VERSION
    assert written["templates"][-1] == template
    assert "leggende_mondiali" in {t["id"] for t in event_generator.load_templates()}
    assert (templates_file.parent / "backup").exists()


def test_an_existing_template_is_modified_in_place(templates_file):
    original = json.loads(editor.template_text("giramondo"))
    changed = dict(original, rewards={"points_per_day": 3, "podium_trophies": 1})
    editor.save_template(changed, original_id="giramondo")
    templates = json.loads(templates_file.read_text(encoding="utf-8"))["templates"]
    assert [t["id"] for t in templates].count("giramondo") == 1
    assert next(t for t in templates if t["id"] == "giramondo")["rewards"]["points_per_day"] == 3
    loaded = next(t for t in event_generator.load_templates() if t["id"] == "giramondo")
    assert loaded["rewards"] == {"points_per_day": 3, "first_correct_bonus": 1, "podium_trophies": 1}


@pytest.mark.parametrize("template_kwargs, original_id, fragment", [
    ({"filters": {"min_team": 3}}, None, "filtro sconosciuto"),
    ({"id": "giramondo"}, None, "esiste gia'"),
    ({"id": "altro_nome"}, "giramondo", "non si cambia"),
])
def test_invalid_saves_are_refused_and_the_file_is_untouched(templates_file, template_kwargs, original_id, fragment):
    before = templates_file.read_text(encoding="utf-8")
    template = _new_template(**template_kwargs)
    if original_id:
        template = dict(json.loads(editor.template_text(original_id)), **template_kwargs)
    with pytest.raises(editor.TemplateEditError, match=fragment):
        editor.save_template(template, original_id=original_id)
    assert templates_file.read_text(encoding="utf-8") == before
    assert not (templates_file.parent / "backup").exists()


def test_saving_an_unchanged_template_is_refused(templates_file):
    with pytest.raises(editor.TemplateEditError, match="Nessuna modifica"):
        editor.save_template(json.loads(editor.template_text("giramondo")), original_id="giramondo")


def test_bad_json_is_explained():
    with pytest.raises(editor.TemplateEditError, match="riga 1"):
        editor.parse_template("{nope")
    with pytest.raises(editor.TemplateEditError, match="oggetto"):
        editor.parse_template("[]")


def test_the_list_shows_candidates_and_schedule():
    rows = {row["id"]: row for row in editor.list_templates()}
    assert rows["giramondo"]["valid"] and rows["giramondo"]["candidates"] > 0
    assert rows["coppie_leggendarie"]["candidates"] is None
    assert rows["coppie_leggendarie"]["schedule"].startswith("manuale")
    assert rows["weekend_transfer"]["schedule"] == "rotazione, parte di fri/sat/sun"


def test_a_rotation_that_can_never_start_is_warned():
    template = _new_template(schedule={"mode": "rotation", "start_weekdays": ["mon"],
                                       "window": {"from": "02-30", "to": "02-30"}})
    preview = editor.preview_template(template)
    assert preview["valid"] and any("non puo' partire" in w for w in preview["warnings"])


@pytest.mark.parametrize("template_id", ["trova_il_collegamento", "metti_in_ordine_la_carriera", "carriera_al_buio"])
def test_the_preview_of_the_new_formats_shows_what_the_player_sees(template_id):
    template = next(t for t in event_generator.load_payload()["templates"] if t["id"] == template_id)
    preview = editor.preview_template(template, original_id=template_id)
    assert preview["valid"], preview["errors"]
    day = preview["sample_days"][0]
    if template_id == "trova_il_collegamento":
        assert " + " in day["content"] and day["answers"] == 1 and day["answer"] != "?"
    elif template_id == "metti_in_ordine_la_carriera":
        assert day["answer"].count(" → ") == 4 and day["answers"] == 1 and day["content"]
    else:
        assert day["content"] and day["stops_shown"] == 5
