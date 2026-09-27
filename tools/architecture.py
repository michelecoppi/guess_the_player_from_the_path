"""Domain map and dependency boundaries of the Python monorepo (#28, #109).

The single source of truth for *where a module belongs* and *what it may depend on*. Files
are not moved by this module: it describes the architecture that exists and makes it
checkable, so the monorepo can be reorganised incrementally without a big-bang rewrite.
`tests/test_architecture_boundaries.py` runs the check in CI; the model is explained in
docs/architecture.md#3-composition-root-and-domain-boundaries.

Every Python module belongs to exactly one **component**:

- a **composition root** (`bot.py`, `admin_ui.py`): builds and wires an application;
- an **app** (`bot`, `api`, `admin`, `scripts`, `tools`): adapters that turn Telegram
  updates, HTTP requests, Streamlit pages or command lines into domain calls;
- a **domain** (`game`, `players`, `daily`, `events`, `groups`, `leagues`, `shop`,
  `referrals`, `users`, `analytics`): product rules and their persistence;
- **infrastructure**: cross-cutting technical services with no product rules
  (Firestore client, observability, queues, flags, backup, dates, i18n...);
- shared **config**.

Rules, checked on the real import graph (imports inside functions included):

1. Nothing imports a composition root; a composition root may import anything.
2. Domains and infrastructure never import an app.
3. An app never imports another app.
4. Infrastructure never imports a domain.
5. A domain imports another domain only along an edge declared in `DOMAIN_DEPENDENCIES`,
   and the declared graph stays acyclic.

Existing violations are not hidden: they are listed in `KNOWN_VIOLATIONS` with a reason.
The check fails on a new violation *and* on a listed violation that no longer exists, so the
debt list can only shrink.

Usage:
    python -m tools.architecture                    # summary, debt and any violation
    python -m tools.architecture --graph            # declared vs actual domain dependencies
    python -m tools.architecture --module domains.shop.service
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[1]

ROOT = "root"
APPS = ("bot", "api", "admin", "scripts", "tools")
DOMAINS = ("game", "players", "daily", "events", "groups", "leagues", "shop", "referrals", "users", "analytics")
INFRASTRUCTURE = "infrastructure"
SHARED_CONFIG = "config"

# Where Python modules live. `webapp/` is the Mini App frontend (TypeScript/JS) delivered by
# the `api` app; it is outside this Python map.
SOURCE_PACKAGES = ("apps", "domains", "services", "handlers", "admin_pages", "scripts", "tools")
SOURCE_MODULES = ("bot", "admin_ui", "config")

# Prefix -> component. The longest matching prefix wins, so a package can be assigned as a
# whole and single modules inside it overridden.
COMPONENTS: dict[str, str] = {
    # --- composition roots -------------------------------------------------------------------
    # bot.py only builds the Telegram application and the HTTP app and wires them (#110).
    "bot": ROOT,
    "admin_ui": ROOT,
    "config": SHARED_CONFIG,
    # --- apps --------------------------------------------------------------------------------
    # PTB application, handler registration and lifecycle; the handlers themselves.
    "apps.bot": "bot",
    "handlers": "bot",
    # FastAPI factory, middleware, webhook/workers, Mini App API and static routers. It reaches
    # the bot only through the TelegramBridge injected by bot.py.
    "apps.api": "api",
    "admin_pages": "admin",
    "scripts": "scripts",
    "tools": "tools",
    # Mini App API projections, initData authentication and throttling: HTTP-facing glue
    # between the api app and the domains.
    "services.webapp_api": "api",
    "services.webapp_auth": "api",
    "services.rate_limit": "api",
    # --- infrastructure ----------------------------------------------------------------------
    "services.firebase_service": INFRASTRUCTURE,
    "services.repos": INFRASTRUCTURE,
    "services.repos.bulk": INFRASTRUCTURE,
    "services.repos.file_lock": INFRASTRUCTURE,
    "services.repos.feature_flags": INFRASTRUCTURE,
    "services.feature_flags": INFRASTRUCTURE,
    "services.observability": INFRASTRUCTURE,
    "services.performance": INFRASTRUCTURE,
    "services.task_queue": INFRASTRUCTURE,
    "services.work_receipts": INFRASTRUCTURE,
    "services.broadcast_store": INFRASTRUCTURE,
    "services.alerts": INFRASTRUCTURE,
    "services.backup_status": INFRASTRUCTURE,
    "services.firestore_backup": INFRASTRUCTURE,
    "services.version": INFRASTRUCTURE,
    "services.dates": INFRASTRUCTURE,
    "services.i18n": INFRASTRUCTURE,
    "services.content_i18n": INFRASTRUCTURE,
    "services.fonts": INFRASTRUCTURE,
    # --- players: production dataset, names, difficulty model, candidate pipeline ------------
    "services.player_pool": "players",
    "services.career_order": "players",
    # Name normalisation and fuzzy matching of player names (answers, aliases, candidates).
    "services.matching": "players",
    "services.difficulty": "players",
    "services.dataset_editor": "players",
    "services.dataset_health": "players",
    "services.dataset_regression": "players",
    # Domain packages (#111): a package maps as a whole. Candidate pipeline and source adapters.
    "domains.players": "players",
    # --- daily: Daily Challenge lifecycle, planner, archive ----------------------------------
    "services.daily_challenge": "daily",
    "services.daily_generator": "daily",
    "services.daily_planner": "daily",
    "services.daily_stats": "daily",
    "services.difficulty_calibration": "daily",
    "services.past_challenges": "daily",
    "services.content_admin": "daily",
    "services.repos.challenges": "daily",
    "services.repos.archive": "daily",
    # Admin settings (blocked players, father/son pairs, planner exclusions, overview counts):
    # mixed persistence, kept whole until it is next touched.
    "services.repos.admin": "daily",
    # --- game: guessing and scoring, hints, Training/Arena, result rendering -----------------
    "services.game": "game",
    "services.hints": "game",
    "services.guess_feedback": "game",
    "services.arena": "game",
    "services.story": "game",
    "services.practice_content": "game",
    "services.path_image": "game",
    "services.share": "game",
    # --- events ------------------------------------------------------------------------------
    "services.event_config": "events",
    "services.event_generator": "events",
    "services.event_rules": "events",
    "services.event_template_editor": "events",
    "services.manual_event_service": "events",
    "services.app_events": "events",
    "services.repos.events": "events",
    # --- users: user documents, streaks, leaderboards, seasons, monthly closure, trophies ----
    "services.repos.users": "users",
    "services.repos.seasons": "users",
    "services.streak": "users",
    "services.monthly_closure": "users",
    "services.trophies": "users",
    # --- shop: cosmetics catalogue, purchases, looks -----------------------------------------
    "domains.shop": "shop",
    # --- referrals ---------------------------------------------------------------------------
    "domains.referrals": "referrals",
    # --- groups: group rounds (rules and repository, #147) -----------------------------------
    "domains.groups": "groups",
    # --- leagues -----------------------------------------------------------------------------
    "services.leagues": "leagues",
    "services.repos.leagues": "leagues",
    # --- analytics: product analytics (#29), not observability ------------------------------
    "services.product_analytics": "analytics",
    "services.product_analytics_query": "analytics",
}

# Allowed domain -> domain imports; anything else between domains is a violation. The graph
# must stay acyclic: when two domains need each other, the call becomes a hook or the shared
# part moves down a level. Layering, bottom to top:
# players -> daily, analytics -> game -> events -> users -> shop -> referrals.
# groups plays on training material and judges answers like every mode (players, game);
# leagues stands alone.
DOMAIN_DEPENDENCIES: dict[str, frozenset[str]] = {
    "players": frozenset(),
    "daily": frozenset({"players"}),
    "analytics": frozenset({"players"}),
    "game": frozenset({"players", "daily", "analytics"}),
    "events": frozenset({"players", "game"}),
    "users": frozenset({"events"}),
    "shop": frozenset({"users"}),
    "referrals": frozenset({"daily", "shop", "analytics"}),
    "groups": frozenset({"players", "game"}),
    "leagues": frozenset(),
}

# Existing violations: (importer, imported) fnmatch patterns -> reason. Each is debt to pay
# down, never a pattern to copy. The check fails when an entry no longer matches anything,
# so the list can only shrink.
KNOWN_VIOLATIONS: dict[tuple[str, str], str] = {
    ("services.firebase_service", "services.repos.*"):
        "compatibility facade re-exporting domain repositories so old imports and test "
        "monkeypatches keep working; new code imports its domain's repository",
    ("services.firebase_service", "domains.*.repository"):
        "compatibility facade re-exporting domain repositories so old imports and test "
        "monkeypatches keep working; new code imports its domain's repository",
    ("services.firebase_service", "services.streak"):
        "the facade still imports the streak rules the users repository uses",
    ("services.repos.users", "domains.shop.service"):
        "recording a counter harvests shop achievements (lazy import, users <-> shop); "
        "should become a hook registered by shop",
    ("services.repos.users", "domains.referrals.service"):
        "a correct guess qualifies a referral directly (lazy import); should become a hook",
    ("services.repos.archive", "domains.referrals.service"):
        "an Archive solve qualifies a referral directly (lazy import); should become a hook",
    ("services.share", "domains.shop.service"):
        "the result card looks up the player's cosmetics itself; callers should pass them in",
    ("services.product_analytics", "domains.shop.service"):
        "event property validation checks item ids against the shop catalogue (lazy import)",
    ("services.dataset_health", "services.event_*"):
        "the dataset health report also checks event template feasibility; that part belongs "
        "to events",
    ("scripts.preview_webapp", "services.webapp_api"):
        "the local Mini App preview renders the real API projections",
}


@dataclass(frozen=True)
class Violation:
    importer: str
    imported: str
    rule: str

    def __str__(self) -> str:
        return f"{self.importer} -> {self.imported}: {self.rule}"


# ---------------------------------------------------------------------------
# Module discovery and import graph
# ---------------------------------------------------------------------------


def discover_modules(root: Path = ROOT_DIR) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for package in SOURCE_PACKAGES:
        for path in sorted((root / package).rglob("*.py")):
            name = ".".join(path.relative_to(root).with_suffix("").parts)
            modules[name.removesuffix(".__init__")] = path
    for name in SOURCE_MODULES:
        path = root / f"{name}.py"
        if path.exists():
            modules[name] = path
    return modules


def _resolve(name: str, modules: dict[str, Path]) -> Optional[str]:
    while name:
        if name in modules:
            return name
        name = name.rpartition(".")[0]
    return None


def _absolute(module: str, path: Path, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
    if node.level > 1:
        package = package[: len(package) - (node.level - 1)]
    return ".".join([*package, node.module] if node.module else package)


def import_graph(modules: Optional[dict[str, Path]] = None) -> dict[str, set[str]]:
    """module -> first-party modules it imports, anywhere in the file."""
    modules = modules if modules is not None else discover_modules()
    graph: dict[str, set[str]] = {}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(filter(None, (_resolve(alias.name, modules) for alias in node.names)))
            elif isinstance(node, ast.ImportFrom):
                base = _absolute(module, path, node)
                for alias in node.names:
                    target = _resolve(f"{base}.{alias.name}", modules) or _resolve(base, modules)
                    if target:
                        imported.add(target)
        imported.discard(module)
        graph[module] = imported
    return graph


def component_of(module: str) -> Optional[str]:
    candidate = module
    while candidate:
        if candidate in COMPONENTS:
            return COMPONENTS[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def kind_of(component: str) -> str:
    if component == ROOT:
        return "root"
    if component in APPS:
        return "app"
    if component in DOMAINS:
        return "domain"
    if component == INFRASTRUCTURE:
        return "infrastructure"
    return "shared"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def rule_violations(graph: dict[str, set[str]]) -> list[Violation]:
    found = []
    for importer, targets in graph.items():
        source = component_of(importer)
        if source is None or source == ROOT:
            continue
        for imported in targets:
            target = component_of(imported)
            if target is None or target == source or target == SHARED_CONFIG:
                continue
            source_kind, target_kind = kind_of(source), kind_of(target)
            rule = None
            if target_kind == "root":
                rule = f"nothing may import the composition root '{imported}'"
            elif target_kind == "app":
                rule = (f"app '{source}' must not import app '{target}'" if source_kind == "app"
                        else f"{source_kind} '{source}' must not import app '{target}'")
            elif source_kind == "infrastructure" and target_kind == "domain":
                rule = f"infrastructure must not import domain '{target}'"
            elif (source_kind == "domain" and target_kind == "domain"
                  and target not in DOMAIN_DEPENDENCIES.get(source, frozenset())):
                rule = f"undeclared domain dependency '{source}' -> '{target}'"
            if rule:
                found.append(Violation(importer, imported, rule))
    return sorted(found, key=lambda violation: (violation.importer, violation.imported))


def _matches(key: tuple[str, str], violation: Violation) -> bool:
    return fnmatch.fnmatchcase(violation.importer, key[0]) and fnmatch.fnmatchcase(violation.imported, key[1])


def known_reason(violation: Violation) -> Optional[str]:
    return next((reason for key, reason in KNOWN_VIOLATIONS.items() if _matches(key, violation)), None)


def declared_cycles(dependencies: Optional[dict[str, frozenset[str]]] = None) -> list[list[str]]:
    """Cycles in the declared domain graph, each reported once starting from its smallest name."""
    dependencies = DOMAIN_DEPENDENCIES if dependencies is None else dependencies
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str, path: list[str]) -> None:
        for nxt in sorted(dependencies.get(node, ())):
            if nxt in path:
                cycle = path[path.index(nxt):]
                start = cycle.index(min(cycle))
                cycles.add(tuple(cycle[start:] + cycle[:start]))
            else:
                visit(nxt, [*path, nxt])

    for domain in dependencies:
        visit(domain, [domain])
    return [list(cycle) for cycle in sorted(cycles)]


def domain_edges(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for importer, targets in graph.items():
        source = component_of(importer)
        if source not in DOMAINS:
            continue
        for imported in targets:
            target = component_of(imported)
            if target in DOMAINS and target != source:
                edges[str(source)].add(str(target))
    return edges


@dataclass
class Report:
    modules: dict[str, Path]
    graph: dict[str, set[str]]
    unmapped: list[str]
    invalid_components: list[str]
    invalid_domains: list[str]
    new_violations: list[Violation]
    known: list[Violation]
    resolved_debt: list[tuple[str, str]]
    cycles: list[list[str]]
    unused_edges: list[tuple[str, str]]

    @property
    def ok(self) -> bool:
        return not (self.unmapped or self.invalid_components or self.invalid_domains
                    or self.new_violations or self.resolved_debt or self.cycles or self.unused_edges)


def check(root: Path = ROOT_DIR) -> Report:
    modules = discover_modules(root)
    graph = import_graph(modules)
    violations = rule_violations(graph)
    actual = domain_edges(graph)
    valid = {ROOT, INFRASTRUCTURE, SHARED_CONFIG, *APPS, *DOMAINS}
    declared_targets = {target for targets in DOMAIN_DEPENDENCIES.values() for target in targets}
    return Report(
        modules=modules,
        graph=graph,
        unmapped=sorted(module for module in modules if component_of(module) is None),
        invalid_components=sorted(f"{prefix}: {component}" for prefix, component in COMPONENTS.items()
                                  if component not in valid),
        invalid_domains=sorted((set(DOMAIN_DEPENDENCIES) ^ set(DOMAINS)) | (declared_targets - set(DOMAINS))),
        new_violations=[violation for violation in violations if known_reason(violation) is None],
        known=[violation for violation in violations if known_reason(violation) is not None],
        resolved_debt=sorted(key for key in KNOWN_VIOLATIONS if not any(_matches(key, v) for v in violations)),
        cycles=declared_cycles(),
        # A declared edge no import uses is a stale permission: remove it so the map stays true.
        unused_edges=sorted((source, target) for source, targets in DOMAIN_DEPENDENCIES.items()
                            for target in targets if target not in actual.get(source, set())),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def render(report: Report) -> str:
    counts: dict[str, int] = defaultdict(int)
    for module in report.modules:
        counts[component_of(module) or "?"] += 1
    lines = [f"{len(report.modules)} modules"]
    for component in (ROOT, *APPS, *DOMAINS, INFRASTRUCTURE, SHARED_CONFIG):
        lines.append(f"  {kind_of(component):<14} {component:<14} {counts.get(component, 0)}")
    sections = (
        ("Unmapped modules (add them to COMPONENTS)", report.unmapped),
        ("Invalid component names in COMPONENTS", report.invalid_components),
        ("DOMAIN_DEPENDENCIES names not matching DOMAINS", report.invalid_domains),
        ("New boundary violations", [str(violation) for violation in report.new_violations]),
        ("KNOWN_VIOLATIONS entries that match nothing (remove them)",
         [f"{importer} -> {imported}" for importer, imported in report.resolved_debt]),
        ("Cycles in DOMAIN_DEPENDENCIES", [" -> ".join([*cycle, cycle[0]]) for cycle in report.cycles]),
        ("Declared domain dependencies no import uses (remove them)",
         [f"{source} -> {target}" for source, target in report.unused_edges]),
        ("Known violations (debt)",
         [f"{violation.importer} -> {violation.imported}: {known_reason(violation)}" for violation in report.known]),
    )
    for title, items in sections:
        if items:
            lines.append(f"\n{title}: {len(items)}")
            lines.extend(f"  - {item}" for item in items)
    lines.append("\nOK" if report.ok else "\nFAILED")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None, root: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(description="Check the domain map and dependency boundaries (#28).")
    parser.add_argument("--graph", action="store_true", help="Print declared and actual domain dependencies")
    parser.add_argument("--module", help="Show the component, imports and importers of one module")
    args = parser.parse_args(argv)
    report = check(root or ROOT_DIR)
    if args.module:
        importers = sorted(importer for importer, targets in report.graph.items() if args.module in targets)
        print(f"{args.module}: {component_of(args.module)}")
        print("imports:", ", ".join(f"{m} ({component_of(m)})" for m in sorted(report.graph.get(args.module, ()))))
        print("imported by:", ", ".join(f"{m} ({component_of(m)})" for m in importers))
        return 0
    if args.graph:
        actual = domain_edges(report.graph)
        for domain in DOMAINS:
            print(f"{domain:<10} declared {sorted(DOMAIN_DEPENDENCIES.get(domain, ()))}  actual {sorted(actual.get(domain, ()))}")
        return 0
    print(render(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
