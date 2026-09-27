"""Canonical backup inventory: every top-level Firestore collection, classified.

This is the single list the exporter, the validator, the restore tool and the docs table in
docs/backup-recovery.md are checked against. A collection the code writes but this module
does not classify makes `tests/test_backup_inventory.py` fail: an exclusion has to be a
decision written down here, never an omission.

Classification:

- `durable`: state that exists nowhere else; losing it loses user-visible data.
- `reconstructable`: can be derived again from durable state, backed up anyway when it is
  small and restoring it is harmless (it keeps idempotency records intact).
- `ephemeral`: leases, locks and deduplication receipts whose useful life is much shorter
  than the backup interval; restoring them is useless at best and harmful at worst.
"""
from __future__ import annotations

from dataclasses import dataclass

DURABLE = "durable"
RECONSTRUCTABLE = "reconstructable"
EPHEMERAL = "ephemeral"


@dataclass(frozen=True)
class CollectionPolicy:
    name: str
    classification: str
    backed_up: bool
    recovery_critical: bool
    subcollections: tuple[str, ...]
    reason: str


INVENTORY: tuple[CollectionPolicy, ...] = (
    CollectionPolicy(
        "users", DURABLE, True, True, ("history", "archive"),
        "Profiles, points, streaks, trophies, owned cosmetics, sessions; history/archive are the "
        "per-day results that the calendar, streaks and referral qualification read.",
    ),
    CollectionPolicy(
        "daily_path", DURABLE, True, True, (),
        "Daily challenge content, accepted answers, first-solver state and counters. The generator "
        "picks players randomly, so past days cannot be regenerated identically.",
    ),
    CollectionPolicy(
        "events", DURABLE, True, True, ("participants",),
        "Event definitions with per-day data; participants hold event points and attempts.",
    ),
    CollectionPolicy(
        "seasons", DURABLE, True, True, (),
        "Monthly seasons; season_number is part of monthly trophy codes.",
    ),
    CollectionPolicy(
        "leagues", DURABLE, True, True, ("members",),
        "Private leagues and member points; no other copy exists.",
    ),
    CollectionPolicy(
        "group_rounds", DURABLE, True, False, ("players",),
        "Current group round and accumulated in-group standings (points, rounds_won). Missing "
        "from the pre-#50 backup.",
    ),
    CollectionPolicy(
        "purchases", DURABLE, True, True, (),
        "Telegram Stars ledger: the only place holding the charge id needed for refunds and "
        "idempotent delivery.",
    ),
    CollectionPolicy(
        "app_duels", DURABLE, True, False, (),
        "Arena duels (seven-day expiry) referenced by users.app_duel. Expired duels are ignored by "
        "the code, so restoring them is harmless. Missing from the pre-#50 backup.",
    ),
    CollectionPolicy(
        "referrals", DURABLE, True, True, (),
        "Referral attribution and qualification ledger; the invite code is consumed at "
        "registration, so attribution cannot be recomputed. Missing from the pre-#50 backup.",
    ),
    CollectionPolicy(
        "admin_settings", DURABLE, True, True, (),
        "Admin overrides (dataset_overrides: players blocked with /admin_block). The whole "
        "collection is exported, so settings documents added later are covered automatically.",
    ),
    CollectionPolicy(
        "father_son_pairs", DURABLE, True, False, (),
        "Manual father/son event content with Telegram file ids; not stored in any file.",
    ),
    CollectionPolicy(
        "monthly_closures", DURABLE, True, True, (),
        "Frozen monthly podium written before the reset. Without it a closure resumed after a "
        "restore would recompute winners from already-reset points.",
    ),
    CollectionPolicy(
        "daily_jobs", RECONSTRUCTABLE, True, False, (),
        "Immutable nightly broadcast payload and sent_total. Derivable from other collections, but "
        "one small document per day; restoring it keeps a resumed job from re-deciding the payload.",
    ),
    CollectionPolicy(
        "work_receipts", EPHEMERAL, False, False, (),
        "Deduplication receipts for Telegram updates and notifications (30-day delete_after). "
        "Their protection window is the retry window (minutes to hours), far shorter than the "
        "backup interval; a restored 'processing' receipt would turn into a spurious 'uncertain' "
        "alert and suppress a notification. Duplicate notifications stay prevented by "
        "users.last_notification_day, which is restored.",
    ),
    CollectionPolicy(
        "update_locks", EPHEMERAL, False, False, (),
        "Per-user update leases of a few minutes. A restored lock is at best already expired and "
        "at worst blocks a user's updates; the code recreates them on demand.",
    ),
)

_BY_NAME = {policy.name: policy for policy in INVENTORY}


def policy(name: str) -> CollectionPolicy | None:
    return _BY_NAME.get(name)


def all_names() -> tuple[str, ...]:
    return tuple(policy.name for policy in INVENTORY)


def backed_up_names() -> tuple[str, ...]:
    return tuple(policy.name for policy in INVENTORY if policy.backed_up)


def excluded_names() -> tuple[str, ...]:
    return tuple(policy.name for policy in INVENTORY if not policy.backed_up)


def declared_subcollections(name: str) -> tuple[str, ...]:
    found = _BY_NAME.get(name)
    return found.subcollections if found else ()
