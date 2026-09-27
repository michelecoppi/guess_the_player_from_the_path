"""Manage experiment plans, launches, results and decisions in Firestore (#52)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import experiments, product_analytics
from services.product_analytics_query import Settings as QuerySettings
from services.repos import experiments as store


def _analytics_ready() -> bool:
    capture = product_analytics.Settings.from_env()
    return bool(capture.enabled and capture.salt and QuerySettings.from_env().configured)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("metrics")
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("key")
    create = sub.add_parser("create")
    create.add_argument("key")
    create.add_argument("--hypothesis", required=True)
    create.add_argument("--metric", required=True, choices=sorted(experiments.METRICS))
    create.add_argument("--duration-days", type=int, required=True)
    create.add_argument("--treatment", required=True)
    start = sub.add_parser("start")
    start.add_argument("key")
    finish = sub.add_parser("finish")
    finish.add_argument("key")
    finish.add_argument("--summary", required=True)
    finish.add_argument("--evidence-url", required=True)
    decide = sub.add_parser("decide")
    decide.add_argument("key")
    decide.add_argument("--decision", required=True, choices=("ship", "iterate", "stop"))
    assign = sub.add_parser("assign")
    assign.add_argument("key")
    target = assign.add_mutually_exclusive_group(required=True)
    target.add_argument("--user")
    target.add_argument("--group")
    args = parser.parse_args(argv)
    if args.command == "metrics":
        print("\n".join(sorted(experiments.METRICS)))
        return 0
    if args.command == "list":
        print(json.dumps({key: row["status"] for key, row in store.load().items()}, sort_keys=True))
        return 0
    if args.command in ("show", "assign"):
        record = store.load().get(args.key)
        if record is None:
            raise ValueError("unknown experiment")
        if args.command == "assign":
            print(experiments.variant_for_subject(record, user_id=args.user, group_id=args.group) or "inactive")
        else:
            print(json.dumps(record, default=str, indent=2))
        return 0
    if args.command == "create":
        record = store.create(experiments.plan(args.key, args.hypothesis, args.metric,
                                               args.duration_days, args.treatment))
    elif args.command == "start":
        record = store.update(args.key, lambda current: experiments.start(
            current, now=datetime.now(timezone.utc), analytics_ready=_analytics_ready()))
    elif args.command == "finish":
        record = store.update(args.key, lambda current: experiments.finish(
            current, summary=args.summary, evidence_url=args.evidence_url,
            now=datetime.now(timezone.utc)))
    else:
        record = store.update(args.key, lambda current: experiments.decide(current, args.decision))
    print(json.dumps(record, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
