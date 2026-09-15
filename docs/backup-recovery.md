# Backup and disaster recovery

Authoritative document for Firestore backup scope, format, retention, restore procedure and
restore testing ([#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50),
epic [#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20)). The
Firestore data model itself is in [firestore.md](firestore.md); deploy and WIF setup in
[deploy.md](deploy.md); the release gate that depends on this document in
[release-checklist.md § 8.2](release-checklist.md#82-backup-gate).

In this project, "we have a backup" means: **a backup whose scope is explicitly known
(§3), whose format is validated before it is kept (§6), and whose restore path is exercised
against a real Firestore (the emulator) on every CI run and every week (§10).** It does not
mean a production restore has been rehearsed with production data; that is a manual drill
(§8.3) run by an operator.

## 1. Components

| Piece | What it is |
| --- | --- |
| [`services/firestore_backup/inventory.py`](../services/firestore_backup/inventory.py) | The one classification of every top-level Firestore collection (§3). |
| [`services/firestore_backup/codec.py`](../services/firestore_backup/codec.py) | Typed, reversible JSON encoding of Firestore values (§5). |
| [`services/firestore_backup/archive.py`](../services/firestore_backup/archive.py) | File format v2, validation, v1 upgrade (§5, §6). |
| [`services/firestore_backup/exporter.py`](../services/firestore_backup/exporter.py) | Reads Firestore into an archive. |
| [`services/firestore_backup/restore.py`](../services/firestore_backup/restore.py) | Target safety guard, restore modes, post-restore verification (§7). |
| [`scripts/backup_firestore.py`](../scripts/backup_firestore.py) | Export CLI (writes `.partial`, validates from disk, then renames). |
| [`scripts/restore_firestore.py`](../scripts/restore_firestore.py) | `validate`, `restore`, `verify`, `upgrade-v1` CLI. |
| [`.github/workflows/backup.yml`](../.github/workflows/backup.yml) | Weekly production export (§11). |
| [`.github/workflows/restore-verification.yml`](../.github/workflows/restore-verification.yml) | Weekly synthetic backup→restore→compare on the emulator (§10). |
| [`tests/test_backup_restore_emulator.py`](../tests/test_backup_restore_emulator.py) | The real round-trip test (also part of every CI run). |

## 2. Recovery properties

These are properties of the mechanism, not a service-level agreement; the project does not
offer an SLA.

| Property | Value |
| --- | --- |
| Backup frequency | Weekly, Mondays 03:30 UTC (`backup.yml`), plus manual *Run workflow* before risky data operations |
| Retention | 365 days per artifact (GitHub Actions artifact retention); after that the artifact is gone |
| Maximum expected data loss (RPO) | Up to **7 days** of writes with only the scheduled backup (more if a scheduled run failed and nobody re-ran it); as small as the time since the last manual run otherwise |
| Restore time | Not measured against production. The emulator drill for the synthetic fixture takes seconds; a real restore is dominated by batched writes (up to 250 documents or ~4 MB per batch) and the full re-read used for verification |
| Consistency | *Not* point-in-time: collections are read one after another in a run lasting seconds to minutes. Counters on a parent (e.g. `leagues.members_count`) can disagree with a subcollection written during the export window |
| Restore test cadence | Every CI run and weekly (Tuesdays 05:00 UTC) on synthetic data (§10); a drill with a real artifact is manual (§8.3) |

## 3. Collection inventory

Every top-level collection found in the code, classified. `tests/test_backup_inventory.py`
fails if the code references a collection that is not in the inventory, if an inventory
entry is no longer used, or if this table disagrees with the inventory module.

| Collection | Classification | Backed up | Subcollections | Recovery-critical | Why |
| --- | --- | --- | --- | --- | --- |
| `users` | durable | yes | `history`, `archive` | yes | Profiles, points, streaks, trophies, cosmetics, sessions; per-day results read by calendar, streaks and referral qualification |
| `daily_path` | durable | yes | — | yes | Challenge content, accepted answers, first-solver state, counters; random generation cannot reproduce past days |
| `events` | durable | yes | `participants` | yes | Event definitions and per-day data; participant points and attempts |
| `seasons` | durable | yes | — | yes | Monthly seasons; `season_number` is part of monthly trophy codes |
| `leagues` | durable | yes | `members` | yes | Private leagues and member points |
| `group_rounds` | durable | yes | `players` | no | Current group round and accumulated in-group standings |
| `purchases` | durable | yes | — | yes | Stars ledger; the Telegram charge id is needed for refunds and idempotent delivery |
| `app_duels` | durable | yes | — | no | Arena duels (7-day expiry) referenced by `users.app_duel`; expired duels are ignored by the code |
| `referrals` | durable | yes | — | yes | Attribution and qualification ledger; the invite code is consumed at registration, so it cannot be recomputed |
| `admin_settings` | durable | yes | — | yes | Admin overrides (`dataset_overrides`); the whole collection is exported, so documents added later are covered |
| `father_son_pairs` | durable | yes | — | no | Manual event content with Telegram file ids, not in any file |
| `monthly_closures` | durable | yes | — | yes | Frozen podium; without it a closure resumed after a restore would recompute winners from reset points |
| `daily_jobs` | reconstructable | yes | — | no | Nightly broadcast payload and `sent_total`; derivable, but tiny, and restoring it keeps a resumed job from re-deciding |
| `work_receipts` | ephemeral | no | — | no | Dedup receipts (30-day `delete_after`); useful only within retry windows much shorter than the backup interval; a restored `processing` receipt would raise a spurious `uncertain` alert and suppress a notification. Duplicate notifications stay prevented by `users.last_notification_day`, which is restored |
| `update_locks` | ephemeral | no | — | no | Per-user leases of a few minutes; a restored lock is useless or blocks updates, and the code recreates locks on demand |

**Silently missing before #50.** The previous exporter had a hand-written list of eight
collections. It did not export `referrals`, `app_duels`, `group_rounds` (durable state),
`monthly_closures` or `daily_jobs`; and because it streamed collections, it skipped any
subcollection whose parent document no longer exists (for example participants of an event
document deleted by hand). All of these are now covered. `work_receipts` and `update_locks`
remain excluded, now deliberately.

**Unclassified collections.** If the database contains a top-level collection the inventory
does not know, the exporter still exports it (data is not dropped), records it under
`inventory.unclassified`, and the weekly workflow turns red after uploading the artifact
until the inventory classifies it.

## 4. What these backups do not protect

- Firestore writes after the last successful backup (§2).
- Excluded ephemeral state (§3): after a restore, in-flight updates/notifications at backup
  time are not deduplicated by receipts; users' `last_notification_day` still prevents a
  second daily notification.
- Versioned data in Git (`data/players.json`, `data/config.json`, shop catalogue, templates),
  which Git protects; local gitignored files (`data/candidates/`, `data/incoming/`,
  `backup/`).
- Cloud configuration: Cloud Run service settings and secrets, Cloud Tasks queues, Cloud
  Scheduler, IAM, WIF, optional TTL policies. `firestore.rules` and
  `firestore.indexes.json` are in the repository and must be redeployed separately.
- State held by Telegram (payments, sent messages, webhook registration).
- The artifacts themselves: they live in this repository's GitHub Actions storage. Deleting
  the repository or a run deletes them; after 365 days they expire.
- **Privacy erasures.** A restore brings back every user as of the backup, including users
  who asked to be erased afterwards (`services/repos/users.py`, `/forgetme`). After any
  production restore, erasures executed since the backup must be re-applied (§8.4).

## 5. Backup format v2 and type fidelity

One JSON file, `firestore-<project>-<UTC timestamp>.json`:

```json
{
  "format": "guess-the-player.firestore-backup",
  "format_version": 2,
  "created_at": "2026-09-14T03:30:02.123456Z",
  "completed_at": "2026-09-14T03:30:41.004511Z",
  "source_project": "guess-the-player-from-path-bot",
  "source_emulator": false,
  "generator": {"tool": "scripts/backup_firestore.py", "git_sha": "…", "run_id": "…"},
  "inventory": {"backed_up": ["…"], "excluded": ["update_locks", "work_receipts"], "unclassified": []},
  "collections": ["admin_settings", "app_duels", "…"],
  "complete": true,
  "document_counts": {"users": 812, "users/*/history": 9423, "…": 0},
  "total_documents": 11234,
  "integrity": {"algorithm": "sha256", "data_sha256": "…"},
  "legacy_conversion": null,
  "data": {"users": {"<id>": {"exists": true, "fields": {}, "subcollections": {"history": {}}}}}
}
```

- Document ids are kept verbatim; subcollections stay nested under their parent.
- `exists: false` marks a parent path with no document but with subcollections; restore
  recreates the subcollections and never invents the parent document.
- `document_counts` keys are path patterns (`users/*/history`), never ids, so they are safe
  to print.
- `integrity.data_sha256` is SHA-256 of the canonical JSON of `data` (sorted keys, compact),
  so reformatting the file does not break it but any change of content does.
- No credentials or secrets are written; the file does contain personal data (§12).

**Type fidelity.** Values the code stores are encoded as follows:

| Firestore value (as returned by the Python client) | JSON in the backup | Restored as |
| --- | --- | --- |
| null, boolean, string | same | same |
| integer (int64) | number without decimals | integer |
| double | number with decimals (`1.0` stays `1.0`) | float |
| array, map | array, object | same, recursively |
| timestamp (`SERVER_TIMESTAMP`, `expires_at`, `delete_after`, `generated_at`, …) | `{"$type": "timestamp", "value": "…Z"}` (UTC, microseconds, Firestore's own precision) | timezone-aware UTC datetime |
| map that contains a `$type` key | `{"$type": "map", "value": {…}}` | the original map |

Not used by the game and therefore **rejected** (the export fails with the field path, ids
masked): references, geo points, bytes, vectors, non-finite floats, naive datetimes, nested
arrays. To store one of them in the future, extend the codec and its tests first.

**Legacy v1 files** (produced before #50, still in retained artifacts) are untyped: every
datetime became ISO text and anything else `str(value)`. They are refused by `validate`
and `restore` until converted with `upgrade-v1` (§8.8), which types back the timestamp fields
the code of that time wrote and marks the result `legacy_conversion.lossy: true`.

## 6. Validation

`python scripts/restore_firestore.py validate FILE` reads the file and restores nothing. It
checks JSON syntax (NaN/Infinity refused), format name and version, required and unknown
metadata keys, timestamps, source project, the collection list against `data`, the
`complete` flag, inventory exclusions (an excluded collection in a file is an error), every
document id and node shape, subcollection structure, decoding of **every** value, document
counts, total and the integrity digest. Output: metadata, file SHA-256, warnings, errors, and
the **restore quality** line.

Three levels are kept distinct:

| Level | Meaning | Emulator restore | Real (production) restore |
| --- | --- | --- | --- |
| invalid | validation errors | refused | refused |
| `exceptional` | structurally valid, but `complete` is not true, or converted from legacy v1 (lossy), or missing a collection the current inventory marks recovery-critical, or carrying any validation warning | allowed | refused unless `--allow-incomplete-or-lossy-backup` is added to all other guards (§7.1) |
| `disaster-recovery` | complete, native v2 backup with every recovery-critical collection and no warning | allowed | allowed with the normal guards |

A converted v1 archive is not equivalent to a native v2 backup: it is always `exceptional`.

Exit codes: `0` valid; `1` invalid (or, with `--strict`, valid with warnings). Warnings:
unclassified collection, subcollection not declared in the inventory, collections the current
inventory backs up but the file does not contain, legacy conversion. `--expect-source-project
P` also fails unless the file comes from `P`.

The export script runs the same validation on the file it just wrote before giving it its
final name; restore re-validates before connecting to any target.

## 7. Restore tool

### 7.1 Safety guard

- **Default target is the emulator.** With `FIRESTORE_EMULATOR_HOST` set, `--project` is
  required and may not be the production project id (use a `demo-` id), and
  `--allow-production` is rejected as contradictory.
- **A real project** (no `FIRESTORE_EMULATOR_HOST`) requires all of: `--allow-production`,
  `--project P`, `--confirm-project P` (exact repeat). The presence of credentials never
  counts as permission and the project is never inferred.
- A backup taken from an emulator is never restored into a real project, and the production
  project only accepts backups whose `source_project` is production.
- **Backup quality for a real target.** A normal production restore requires a complete,
  native v2 backup (quality `disaster-recovery`, §6). A partial, legacy-converted (lossy) or
  otherwise `exceptional` backup is refused, dry-run included. The exceptional recovery path
  needs a second, separate acknowledgement, `--allow-incomplete-or-lossy-backup`, which only
  lifts this refusal: `--allow-production`, the exact `--confirm-project` and the source checks
  still apply. With it the tool prints the issues (metadata only) and logs
  `backup.restore.quality_override`. The flag is rejected for emulator targets, which already
  accept any structurally valid backup.
- The target guard runs before the file is read and before any connection; the quality and
  source checks run after validation and also before any connection, so a refusal can never
  follow a write. The client's resolved project must equal `--project`.
- Credentials for a real target: Application Default Credentials, or `--credentials
  key.json`. Writing needs a role with write access (e.g. `roles/datastore.user`); the backup
  workflow's `roles/datastore.viewer` cannot restore.

### 7.2 Existing-data semantics

| `--mode` | Behaviour |
| --- | --- |
| `empty` (default) | Refuses unless every restored collection is empty in the target (an orphan subcollection counts as data). Writes with `create()`, so a document that appears meanwhile aborts the batch instead of being overwritten. |
| `missing-only` | Creates documents that do not exist; leaves existing documents untouched and reports how many differ from the backup. Also resumes an interrupted restore. |
| `overwrite` | Replaces every document present in the backup (whole document, not a field merge). Documents that exist only in the target are kept. |

No mode deletes anything. `--dry-run` validates, resolves the target, reads it and prints the
plan (documents to write/skip per collection) without writing.

After writing, the tool re-exports the restored collections with the same exporter and
compares every document type-strictly with the backup: missing documents fail every mode;
differences fail `empty` and `overwrite`; documents not in the backup fail only `empty`.
`verify` runs the same comparison read-only.

Exit codes: `0` done/verified; `1` invalid backup; `2` refused by a guard (nothing written);
`3` failed during writing or verification (§8.6).

## 8. Procedures

Commands assume the repository root, `pip install -r requirements.txt`, and for emulator
steps a running emulator (`python -m tools.dev emulator`, default `127.0.0.1:8571`).

### 8.1 Find a backup artifact

```bash
gh run list --workflow backup.yml --limit 10
gh run view <run-id>
gh run download <run-id> --dir restore-work
```

The artifact name is `firestore-backup-<UTC timestamp>-run<run id>-<attempt>`; the run
summary shows the validated metadata. Pick the newest run *before* the damage happened, not
simply the newest. Keep `restore-work/` out of Git (it contains personal data).

### 8.2 Check metadata and validate

```bash
python scripts/restore_firestore.py validate restore-work/<name>/firestore-*.json --expect-source-project guess-the-player-from-path-bot
```

Record `created_at`, `file_sha256`, `total_documents`, `document_counts` and the `Restore
quality` line in the incident notes. Do not continue with a file that is invalid. For a normal
production restore the quality must be `disaster-recovery`; if it is `exceptional`, prefer an
older complete native v2 backup, and only fall back to the exceptional path (§8.4) after
inspecting the file in the emulator.

### 8.3 Restore into the emulator first

```bash
python -m tools.dev emulator   # separate terminal
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8571
python scripts/restore_firestore.py restore <file> --project demo-gtp-restore --dry-run
python scripts/restore_firestore.py restore <file> --project demo-gtp-restore
python scripts/restore_firestore.py verify <file> --project demo-gtp-restore
```

Check counts and invariants against the metadata and against what you expect of production:
number of `users`, today's and upcoming `daily_path` days, `purchases` count, a sample of
`leagues.members_count` against the size of `members`. Only continue to production when the
emulator restore completes with `RESTORE COMPLETED AND VERIFIED`.

### 8.4 Emergency production restore

1. **Decide the scope.** Whole database lost → `--mode empty` into an empty database. Some
   documents deleted or corrupted → `--mode missing-only` (recreate what is missing) or
   `--mode overwrite` (put back backup contents over damaged documents, accepting loss of
   later legitimate changes to those documents). There is no per-collection or per-document
   selection in the tool; for a narrow repair build a reduced file in the emulator (restore
   there, fix, re-export the needed collections with `backup_firestore.py --collections`).
   Such a reduced or partial file, like a converted v1 file, is `exceptional` quality: restoring
   it into production is the **exceptional recovery path** and needs
   `--allow-incomplete-or-lossy-backup` in addition to every guard below. Restore it into the
   emulator first and write down why a complete native v2 backup could not be used.
2. **Stop or reduce writers.** There is no maintenance mode. Pause the nightly job
   (`gcloud scheduler jobs pause daily-generation --location <scheduler-region>`) and the
   queues (`gcloud tasks queues pause telegram-updates --location europe-west1`,
   same for `daily-broadcast`); paused tasks are kept and run after resume. Mini App API
   requests write directly and are not stopped by this; judge whether to block traffic.
3. **Take a backup of the current state** (`backup.yml` → *Run workflow*). It is the rollback
   point for the restore itself (§8.7).
4. **Dry-run against production** with the full guards and read the plan:

   ```bash
   python scripts/restore_firestore.py restore <file> --project guess-the-player-from-path-bot \
     --allow-production --confirm-project guess-the-player-from-path-bot --mode <mode> --dry-run
   ```

5. **Restore**: the same command without `--dry-run`, with an identity that has write access.
6. **Verify** (§8.5), then resume queues/scheduler (`gcloud tasks queues resume …`,
   `gcloud scheduler jobs resume …`).
7. **Re-apply privacy erasures** performed after the backup's `created_at` (Cloud Run logs,
   `[PRIVACY] Dati utente … cancellati`; Cloud Logging retention limits how far back this is
   possible) and **refunds** issued after it (`purchases.refunded` must reflect Telegram).
8. Write down backup `created_at`, file SHA-256, mode, counts and the resulting data-loss
   window in the incident/release evidence.

### 8.5 Verify the result

- The restore output must end with `RESTORE COMPLETED AND VERIFIED`; re-run
  `verify` if in doubt (read-only; `--allow-production` without confirmation is enough).
  Pass the same `--mode` used for the restore: with the default `empty`, documents written
  to production after the restore count as failures.
- Smoke-check the bot as in [release-checklist.md § 11](release-checklist.md#11-post-deploy-smoke-matrix):
  `/start`, today's Daily, profile, leaderboard, a league, the shop's purchase history.
- `/admin_status` / `/admin_next`: the Daily buffer still has upcoming days.

### 8.6 Partial failures

A failure while writing (exit code `3`) leaves the batches committed before it in place;
each batch is atomic, nothing is deleted, and the output reports `written` and
`batches_committed`.

- **Retry**: re-run with `--mode missing-only`. It skips what already exists and creates the
  rest, then verifies everything. `empty` would now refuse, by design.
- **Collision in `empty` mode** ("a document appeared in the target"): something is writing
  to the target. Stop writers (§8.4 step 2), then resume with `missing-only`.
- **Verification failed** after a complete write: do not resume traffic; compare the
  reported per-collection counts, run `verify`, and investigate before retrying with
  `overwrite`.

### 8.7 Rolling back or retrying a restore

The tool never deletes, so "undoing" a restore means restoring the pre-restore backup taken in
§8.4 step 3 with `--mode overwrite`. Documents that the restore created and that did not exist
before are not removed by that; remove them deliberately, by hand, only if they are harmful.

### 8.8 Legacy v1 artifacts

```bash
python scripts/restore_firestore.py upgrade-v1 firestore-20260914-033012.json firestore-v2-from-v1.json \
  --source-project guess-the-player-from-path-bot --created-at 2026-09-14T03:30:12Z
python scripts/restore_firestore.py validate firestore-v2-from-v1.json
```

`--created-at` is the export time from the v1 file name (runner clock, UTC on GitHub Actions).
The result is `complete: false` (v1 never had `referrals`, `app_duels`, `group_rounds`,
`monthly_closures`, `daily_jobs`), only the known timestamp fields are typed back, and it is
marked `legacy_conversion.lossy: true`. It is not equivalent to a native v2 backup: its quality
is always `exceptional`, a normal production restore refuses it, and only the exceptional path
(`--allow-incomplete-or-lossy-backup`, after an emulator inspection) can use it.

## 9. Code rollback vs data restore

They are different operations and neither implies the other:

- **Code rollback** (Cloud Run traffic to a previous revision, or redeploy an older commit —
  [release-checklist.md § 10](release-checklist.md#10-rollback)) changes the program. It does
  **not** change a single Firestore document: deploying an old container never restores data.
- **Data restore** (this document) changes Firestore. It does not change the running code,
  which must understand the restored data. After a data migration, restoring the pre-migration
  backup usually also requires rolling code back to a revision that reads the old shape.

## 10. Periodic restore verification

- `tests/test_backup_restore_emulator.py` seeds a synthetic, production-shaped fixture
  (every backed-up collection; `users` + `history`/`archive`, `events` + `participants`,
  `leagues` + `members`, `group_rounds` + `players`, purchases, referrals, duels, admin
  settings; `SERVER_TIMESTAMP`, `Increment`, `ArrayUnion`, aware datetimes, whole floats,
  large ints, a `$type` key, an orphan subcollection, and excluded ephemeral documents) into
  one emulator project, runs `scripts/backup_firestore.py`, validates, restores with
  `scripts/restore_firestore.py` into a second empty project, and compares every document
  with the source type-strictly. It also covers non-empty target refusal, dry-run, an
  interrupted restore resumed with `missing-only`, `overwrite`, corrupt-file rejection and an
  unsupported value failing the export.
- It runs in every CI run (`ci.yml` starts the emulator) and weekly plus on demand in
  `restore-verification.yml` (three consecutive runs). That workflow has
  `permissions: contents: read`, no secrets, no GCP authentication and no `--allow-production`:
  it cannot reach production.
- A real artifact is not used in CI because it would expose personal data; restoring a real
  artifact into the emulator is the manual drill in §8.3, recommended at least once per
  quarter and before a risky migration.

## 11. Weekly production backup (`backup.yml`)

Unchanged architecture: GitHub Actions, Workload Identity Federation with the deploy service
account holding `roles/datastore.viewer` (read-only), no service account keys
([deploy.md § 3](deploy.md#3-backup-settimanale-del-database)). Steps: export (the script
refuses to leave an invalid file), independent `validate --expect-source-project`, metadata to
the run summary, upload of exactly one file as
`firestore-backup-<timestamp>-run<id>-<attempt>` with 365-day retention, then `validate
--strict` so an unclassified collection turns the run red after the data is safely uploaded.
Logs carry metadata and counts, never document contents.

## 12. Handling backup files

Backups contain personal data (Telegram ids, names, purchase and referral records). Download
them only for a restore or drill, keep them out of Git (`backup/` and `restore-work/` are
gitignored), never attach them to issues or
PRs, and delete local copies afterwards. The retention stated in the privacy notice
(`webapp/privacy.html`) is the 365-day artifact retention.

## 13. Observability

Structured events from [observability.md](observability.md) (component `backup`), with
counts/metadata only: `backup.export.completed|failed` (collections, total_documents,
complete, unclassified), `backup.export.collection` (collection, documents),
`backup.export.unclassified_collection`, `backup.export.written`, `backup.export.invalid`,
`backup.validate.completed`, `backup.restore.completed|failed` (mode, planned, written,
verified, missing/different/extra), `backup.restore.real_target` (WARNING),
`backup.restore.quality_override` (WARNING: target, `complete`, `lossy`, issue count),
`backup.verify.completed`.
