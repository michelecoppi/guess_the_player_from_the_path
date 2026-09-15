"""Inspect and change the operational feature flags (#51) without a deploy.

Reads and writes `admin_settings/feature_flags` with the same credentials as the other
scripts (FIREBASE_CREDENTIALS_PATH or application-default credentials; with
FIRESTORE_EMULATOR_HOST set it talks to the emulator). Every change is validated, shown
before it is applied, confirmed (or `--yes`) and written in a transaction on the current
document, so it never overwrites a concurrent change. Running replicas pick it up within
the cache TTL (FEATURE_FLAGS_CACHE_TTL_SECONDS, default 30 s).

    python scripts/feature_flags.py list
    python scripts/feature_flags.py show shop [--show-targets]
    python scripts/feature_flags.py disable shop            # emergency kill switch
    python scripts/feature_flags.py enable shop
    python scripts/feature_flags.py rollout arena 25
    python scripts/feature_flags.py allow arena --user 123456789
    python scripts/feature_flags.py deny leaderboard --group -1001234567890
    python scripts/feature_flags.py untarget arena --user 123456789
    python scripts/feature_flags.py reset arena             # back to the repository default

Target ids are never printed unless `show --show-targets` is asked for explicitly.
Procedure and semantics: docs/feature-flags.md.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import feature_flags as ff  # noqa: E402
from services import observability  # noqa: E402

EXIT_OK, EXIT_ERROR, EXIT_ABORTED = 0, 1, 2


def _repo():
    from services.repos import feature_flags as repo
    return repo


def _on(value):
    return "on" if value else "OFF"


def _counts(rule):
    return (f"allow {len(rule.allow_users)}u/{len(rule.allow_groups)}g, "
            f"deny {len(rule.deny_users)}u/{len(rule.deny_groups)}g")


def describe(rule, default):
    if rule is None:
        return f"no stored rule (repository default: {_on(default)})"
    return f"enabled={_on(rule.enabled)}, rollout={rule.rollout_percentage}%, {_counts(rule)}"


def render_list(raw, out):
    try:
        report = ff.parse_document(raw)
    except ff.ConfigError as exc:
        out(f"STORED DOCUMENT INVALID ({exc}): runtime keeps its last-known-good config or defaults.")
        return EXIT_ERROR
    config = report.config
    out(f"admin_settings/feature_flags: {'missing (all defaults)' if raw is None else f'revision {config.revision}'}")
    out(f"{'flag':<16} {'default':<8} {'stored':<8} {'enabled':<8} {'rollout':<8} targets")
    for flag in ff.Flag:
        default = ff.REGISTRY[flag].default
        rule = config.rules.get(flag)
        if flag.value in report.invalid:
            stored = f"INVALID({report.invalid[flag.value]})"
        else:
            stored = "yes" if rule else "no"
        if rule is None:
            out(f"{flag.value:<16} {_on(default):<8} {stored:<8} {_on(default):<8} {'-':<8} -")
        else:
            out(f"{flag.value:<16} {_on(default):<8} {stored:<8} {_on(rule.enabled):<8} "
                f"{str(rule.rollout_percentage) + '%':<8} {_counts(rule)}")
    if report.unknown:
        out(f"ignored unknown flag keys: {len(report.unknown)}")
    return EXIT_OK


def render_show(raw, flag, show_targets, out):
    try:
        report = ff.parse_document(raw)
    except ff.ConfigError as exc:
        out(f"STORED DOCUMENT INVALID ({exc})")
        return EXIT_ERROR
    definition = ff.REGISTRY[flag]
    out(f"{flag.value}: {definition.description}")
    if flag.value in report.invalid:
        out(f"stored entry INVALID (field: {report.invalid[flag.value]}); "
            f"runtime uses {'the kill switch (off)' if flag in report.kill_switch_kept else 'last-known-good or default'}")
    rule = report.config.rules.get(flag)
    out(describe(rule, definition.default))
    if rule is not None and show_targets:
        for name in ff.TARGET_LISTS:
            out(f"  {name}: {', '.join(sorted(getattr(rule, name), key=lambda v: (len(v), v))) or '-'}")
    return EXIT_OK


def build_change(args):
    """The pure change for the requested command, validated before anything is read."""
    command = args.command
    if command == "enable":
        return lambda rule: ff.change_enabled(rule, True)
    if command == "disable":
        return lambda rule: ff.change_enabled(rule, False)
    if command == "rollout":
        ff.change_rollout(ff.FlagRule(), args.percentage)
        return lambda rule: ff.change_rollout(rule, args.percentage)
    if command == "reset":
        return None
    target = args.user if args.user is not None else args.group
    ff.normalize_target_id(target)
    groups = args.group is not None
    if command == "untarget":
        return lambda rule: ff.clear_targets(rule, [target], groups=groups)
    list_name = f"{command}_{'groups' if groups else 'users'}"
    opposite = f"{'deny' if command == 'allow' else 'allow'}_{'groups' if groups else 'users'}"
    # Moving an id from deny to allow (or back) is one intention, so it is one change.
    return lambda rule: ff.change_target(ff.change_target(rule, opposite, target, add=False),
                                         list_name, target, add=True)


def mutate(args, flag, *, load, update, confirm, out):
    try:
        change = build_change(args)
    except ValueError as exc:
        out(f"invalid input: {exc}")
        return EXIT_ABORTED

    repo = _repo()
    raw = load()
    try:
        _, _, preview = repo.plan_update(raw, flag, change, expected_revision=args.expected_revision,
                                         replace_invalid_document=args.replace_invalid_document)
    except (repo.StoredConfigInvalid, repo.RevisionConflict, ValueError) as exc:
        out(f"refused: {exc}")
        return EXIT_ERROR

    default = ff.REGISTRY[flag].default
    out(f"flag:   {flag.value} ({ff.REGISTRY[flag].description})")
    out(f"before: {describe(preview.before, default)}")
    out(f"after:  {describe(preview.after, default)}")
    out(f"revision {preview.previous_revision} -> {preview.revision}")
    if not args.yes and not confirm():
        out("aborted: nothing written")
        return EXIT_ABORTED

    try:
        result = update(flag, change, actor=args.actor, expected_revision=args.expected_revision,
                        replace_invalid_document=args.replace_invalid_document)
    except (repo.StoredConfigInvalid, repo.RevisionConflict, ValueError) as exc:
        out(f"refused: {exc}")
        return EXIT_ERROR
    if result.previous_revision != preview.previous_revision:
        out(f"note: the document changed meanwhile; the change was applied on top of revision "
            f"{result.previous_revision} (other changes kept)")
        out(f"now:    {describe(result.after, default)}")
    observability.log_event("feature_flags.change.applied", component="admin", flag=flag.value,
                            operation=args.command, revision=result.revision)
    out(f"applied: revision {result.revision}. Replicas converge within the cache TTL "
        f"(~{int(ff.ttl_from_env())} s).")
    return EXIT_OK


def parser():
    root = argparse.ArgumentParser(description="Feature flag operativi (admin_settings/feature_flags)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="stato di tutti i flag (senza id)")
    show = commands.add_parser("show", help="dettaglio di un flag")
    show.add_argument("flag")
    show.add_argument("--show-targets", action="store_true", help="stampa anche gli id in allow/deny")

    def mutation(name, help_text):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("flag")
        sub.add_argument("--yes", action="store_true", help="non chiedere conferma")
        sub.add_argument("--actor", default="operator-cli", help="etichetta salvata in updated_by")
        sub.add_argument("--expected-revision", type=int, default=None,
                         help="rifiuta se il documento non e' a questa revisione")
        sub.add_argument("--replace-invalid-document", action="store_true",
                         help="se il documento salvato non e' valido, sostituiscilo con uno nuovo")
        return sub

    mutation("enable", "riaccende il flag (master)")
    mutation("disable", "spegne il flag per tutti (kill switch)")
    mutation("rollout", "percentuale di rollout 0-100").add_argument("percentage", type=int)
    mutation("reset", "rimuove la regola: torna al default del repository")
    for name, help_text in (("allow", "abilita esplicitamente un utente o gruppo"),
                            ("deny", "esclude esplicitamente un utente o gruppo"),
                            ("untarget", "toglie un utente o gruppo da allow e deny")):
        sub = mutation(name, help_text)
        target = sub.add_mutually_exclusive_group(required=True)
        target.add_argument("--user")
        target.add_argument("--group")
    return root


def main(argv=None, *, load=None, update=None, confirm=None, out=print):
    args = parser().parse_args(argv)
    if args.command != "list":
        try:
            flag = ff.parse_flag(args.flag)
        except ValueError as exc:
            out(f"{exc}; supported: {', '.join(flag.value for flag in ff.Flag)}")
            return EXIT_ABORTED
    load = load or _repo().load_document
    if args.command == "list":
        return render_list(load(), out)
    if args.command == "show":
        return render_show(load(), flag, args.show_targets, out)
    if confirm is None:
        def confirm():
            if not sys.stdin.isatty():
                out("not a terminal: pass --yes to apply")
                return False
            return input("apply? [y/N] ").strip().lower() in ("y", "yes")
    return mutate(args, flag, load=load, update=update or _repo().update_flag, confirm=confirm, out=out)


if __name__ == "__main__":
    sys.exit(main())
