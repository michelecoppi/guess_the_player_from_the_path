"""Domain map and dependency boundaries (#28, #109): the real repository, and the checker itself.

The first test is the guard: a new module that is not mapped, a new forbidden import or a
debt entry that has been paid off fails here, with the full report in the message. The others
prove on a tiny synthetic repository that each rule actually catches what it claims to.
"""
from pathlib import Path

import pytest

from tools import architecture


def test_repository_respects_the_domain_boundaries():
    report = architecture.check()
    assert report.ok, "\n" + architecture.render(report)


def test_every_domain_and_app_is_documented_in_architecture_md():
    text = (architecture.ROOT_DIR / "docs" / "architecture.md").read_text(encoding="utf-8")
    for name in (*architecture.DOMAINS, *architecture.APPS):
        assert f"`{name}`" in text, f"component {name!r} is not described in docs/architecture.md"


# ---------------------------------------------------------------------------
# The checker on a synthetic repository
# ---------------------------------------------------------------------------


def _write(root: Path, files: dict[str, str]) -> None:
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _write(tmp_path, {
        "bot.py": "import handlers.start\nfrom services import shop\n",
        "config.py": "",
        "handlers/__init__.py": "",
        "handlers/start.py": "from services import shop\nimport config\n",
        "admin_pages/__init__.py": "",
        "admin_pages/page.py": "from services import shop\n",
        "services/shop.py": "from services import dates\n",
        "services/players.py": "",
        "services/dates.py": "",
    })
    monkeypatch.setattr(architecture, "COMPONENTS", {
        "bot": "root", "config": "config", "handlers": "bot", "admin_pages": "admin",
        "services.shop": "shop", "services.players": "players", "services.dates": "infrastructure",
    })
    monkeypatch.setattr(architecture, "DOMAIN_DEPENDENCIES", {domain: frozenset() for domain in architecture.DOMAINS})
    monkeypatch.setattr(architecture, "KNOWN_VIOLATIONS", {})
    return tmp_path


def _rules(root):
    return {(v.importer, v.imported): v.rule for v in architecture.check(root).new_violations}


def test_clean_synthetic_repository_passes(repo):
    report = architecture.check(repo)
    assert report.ok, architecture.render(report)
    assert report.graph["bot"] == {"handlers.start", "services.shop"}


def test_each_rule_is_enforced_including_imports_inside_functions(repo):
    _write(repo, {
        "services/shop.py": "def f():\n    from handlers import start\n    import services.players\n",
        "services/dates.py": "from . import shop\n",
        "admin_pages/page.py": "import handlers.start\n",
        "handlers/start.py": "import bot\n",
    })
    rules = _rules(repo)
    assert rules[("services.shop", "handlers.start")] == "domain 'shop' must not import app 'bot'"
    assert rules[("services.shop", "services.players")] == "undeclared domain dependency 'shop' -> 'players'"
    assert rules[("services.dates", "services.shop")] == "infrastructure must not import domain 'shop'"
    assert rules[("admin_pages.page", "handlers.start")] == "app 'admin' must not import app 'bot'"
    assert rules[("handlers.start", "bot")] == "nothing may import the composition root 'bot'"


def test_declared_edges_allow_imports_but_must_be_used_and_acyclic(repo, monkeypatch):
    _write(repo, {"services/shop.py": "from services.players import x\n"})
    monkeypatch.setitem(architecture.DOMAIN_DEPENDENCIES, "shop", frozenset({"players"}))
    assert architecture.check(repo).ok

    monkeypatch.setitem(architecture.DOMAIN_DEPENDENCIES, "shop", frozenset({"players", "users"}))
    assert architecture.check(repo).unused_edges == [("shop", "users")]

    monkeypatch.setitem(architecture.DOMAIN_DEPENDENCIES, "players", frozenset({"shop"}))
    assert architecture.declared_cycles() == [["players", "shop"]]


def test_unmapped_modules_fail(repo):
    _write(repo, {"services/new_feature.py": ""})
    assert architecture.check(repo).unmapped == ["services.new_feature"]


def test_known_violations_are_tolerated_until_paid_off(repo, monkeypatch):
    _write(repo, {"services/shop.py": "import handlers.start\n"})
    monkeypatch.setattr(architecture, "KNOWN_VIOLATIONS", {("services.sh*", "handlers.*"): "legacy"})
    report = architecture.check(repo)
    assert report.ok and [str(v.imported) for v in report.known] == ["handlers.start"]

    _write(repo, {"services/shop.py": ""})
    report = architecture.check(repo)
    assert not report.ok and report.resolved_debt == [("services.sh*", "handlers.*")]


def test_cli_reports_and_fails_on_violations(repo, capsys):
    assert architecture.main([], root=repo) == 0
    _write(repo, {"services/dates.py": "import services.shop\n"})
    assert architecture.main([], root=repo) == 1
    assert "New boundary violations: 1" in capsys.readouterr().out
    assert architecture.main(["--module", "services.dates"], root=repo) == 0
    assert "services.dates: infrastructure" in capsys.readouterr().out


def test_bot_py_stays_a_pure_composition_root():
    """#110: bot.py wires apps together; routes, handler registration and rules live in apps/."""
    import ast

    tree = ast.parse((architecture.ROOT_DIR / "bot.py").read_text(encoding="utf-8"))
    functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert functions == [], f"bot.py must not define functions: {functions}"
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    # Route decorators need a function, so "no functions" already excludes them; these catch the
    # decorator-less forms of registering routes, handlers or middleware.
    assert not calls & {"add_handler", "add_api_route", "middleware", "include_router", "exception_handler"}


def test_composed_app_exposes_the_bot_bridge_to_the_http_app(monkeypatch):
    import importlib.util

    import config

    monkeypatch.setattr(config, "BOT_TOKEN", "123456:test-token")
    spec = importlib.util.spec_from_file_location("composed_bot", architecture.ROOT_DIR / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app.state.telegram is module.bot_bridge
    assert module.bot_bridge.application is module.telegram_app
    paths = {route.path for route in module.app.routes}
    assert {"/", "/webhook", "/internal/telegram-update", "/app/api/me", "/app/v2/assets/{file_path:path}"} <= paths
    assert len(module.telegram_app.handlers[0]) > 50
