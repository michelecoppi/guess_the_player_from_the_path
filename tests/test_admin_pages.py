"""Exercise extracted renderers without connecting to production or clicking writes."""
import importlib

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("page", ["overview", "challenges", "events", "users", "leagues", "dataset", "blocked", "father_son"])
def test_admin_page_renders_with_unavailable_database(page):
    module = importlib.import_module(f"admin_pages.{page}")
    assert callable(module.render)
    script = f'''
from datetime import datetime
from zoneinfo import ZoneInfo
from admin_pages.{page} import render
render("2026-09-09", datetime(2026, 9, 9, tzinfo=ZoneInfo("Europe/Rome")))
'''
    result = AppTest.from_string(script).run(timeout=20)
    assert not result.exception
