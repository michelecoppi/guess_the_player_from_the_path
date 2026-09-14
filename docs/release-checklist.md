# Release management

Authoritative document for versioning, changelog, release checklist and rollback
([#49](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/49), part of
epic [#20](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/20)). The
goal: given a specific commit, an operator can determine version, included changes,
readiness, required data/migration checks, deploy procedure, rollback path and post-deploy
smoke checks — without relying on memory of who deployed what. This document does not
duplicate [deploy.md](deploy.md) (how each piece is deployed) or
[ci_cd_pipeline.md](ci_cd_pipeline.md) (what CI runs); it links them and adds the layer
those don't cover: *when* a set of commits becomes a release, and how to know it's safe.

This process does not exist yet: `main` has always deployed continuously with no version
numbers (see [operations.md § Release state](operations.md#release-state) before this
change). Adopting it is opt-in going forward — see [§ Adopting this process](#adopting-this-process).

## 1. Versioning policy

[Semantic Versioning](https://semver.org/spec/v2.0.0.html), `MAJOR.MINOR.PATCH`, applied
pragmatically to a single-service Telegram Mini App product — not to every commit:

| Bump | When |
| --- | --- |
| **MAJOR** | A breaking change to the Mini App API contract (`/app/api/*`) or bot behaviour a client depends on; a Firestore schema change that is not backward-compatible with the previous release's code; removing a user-facing feature; switching the `/app` default to V2 ([#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81) rollout) |
| **MINOR** | A new user-facing feature, game mode, Mini App screen, or backward-compatible API addition |
| **PATCH** | Bug fixes, dependency bumps, backend/infra changes with no user-visible contract change, documentation released alongside a code change |

**Not a release on its own:** the Daily challenge, themed Events, and ordinary dataset
growth through the normal pipeline ([player-data-pipeline.md](player-data-pipeline.md)) are
content operations, not application releases — they don't bump the version. A release is
cut when *code, configuration, or dataset schema* changes and the change should be
deployed, not on a content cadence.

## 2. Canonical version source

The single source of truth is the [`VERSION`](../VERSION) file at the repository root — one
line, `MAJOR.MINOR.PATCH`, no `v` prefix, no pre-release suffix. Nothing else defines the
application's release version:

- `services/version.py` reads it at runtime (`get_version()`), used today by the `/`
  health endpoint (`bot.py`) so a running revision can report its own version without
  redeploying. This is the boundary [#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18)
  (Sentry/error tracking) can later read the same identifier from for its `release` tag —
  no runtime redesign needed, just importing `services.version.get_version()`.
- `package.json`'s `version` field is a **mirror**, kept in sync by the bump tool (§7). It
  exists only because npm expects one; it is not read anywhere in the app and is not a
  second source of truth. `python -m tools.release check` fails if it drifts from `VERSION`.
- `pyproject.toml` has no `[project]` table and defines no version — Python packaging is
  not in play here (this is a service, not a published package), so it stays out of the
  versioning story.

## 3. CHANGELOG

[`CHANGELOG.md`](../CHANGELOG.md) at the repository root, format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries land under
**`## [Unreleased]`** (`Added` / `Changed` / `Fixed` / `Security`) as part of the same PR
that makes the change — not reconstructed afterwards. At release time,
`python -m tools.release bump <level>` moves that content into a new dated
`## [X.Y.Z] - YYYY-MM-DD` section and resets Unreleased to blank. The `0.1.0` entry is a
baseline marker for "state when this process started," not a reconstruction of project
history — `git log` remains authoritative for individual historical commits.

## 4. Release lifecycle

```
main (small PRs land continuously, each already gated by CI — see ci_cd_pipeline.md)
   │
   ▼
release candidate  = the exact commit on main chosen to become a release.
                      Not a branch: main already gates every commit with CI, so a long-lived
                      release branch would just duplicate that gate. "Candidate" is a status
                      applied to one SHA, recorded in the PR/issue, not a git ref.
   │
   ▼
validation         = §5 checklist run against that exact SHA
   │
   ▼
release/tag        = python -m tools.release bump <level>, review + commit, git tag vX.Y.Z
                      on that SHA, push tag → triggers release-check.yml (§9)
   │
   ▼
deploy              = §6 (the same automatic Cloud Run deploy already in place — the tag
                       does not trigger a separate deploy pipeline, see §6)
   │
   ▼
post-deploy smoke   = §11
   │
   ▼
complete  OR  rollback (§10)
```

No long-lived release branches: this repository ships continuously and small, and a
parallel branch would drift from `main` and duplicate CI for no benefit. If a real need for
one emerges later (e.g. maintaining an old MAJOR version), revisit this section rather than
inventing it silently.

## 5. Release checklist

Run against **one exact commit SHA** (§8). Required items apply to every release;
conditional items apply only when that release touches the named area. This checklist is
intentionally a checklist, not a script — see §7 for what `tools.release` automates
(release *metadata*, not the checks themselves, which already exist as CI/test suites this
document is deliberately not duplicating).

### Required

- [ ] **Git** — release candidate is one exact SHA on `main`, working tree at that SHA is
      what will be tagged (§8).
- [ ] **CI** — the `CI` workflow run for that exact SHA is green
      ([ci_cd_pipeline.md](ci_cd_pipeline.md#1-ci--githubworkflowsciyml)). Record the run
      URL/ID as release evidence (§12), don't just say "main passed."
- [ ] **Security** — `python -m tools.dev security-check` clean, or any active exception in
      `security-exceptions.json` reviewed and still justified ([security.md](security.md)).
- [ ] **Backend tests** — covered by the CI run above (`pytest` with coverage gate); no
      separate run needed if CI is green on the exact SHA.
- [ ] **Frontend tests** — covered by the CI run above (`node --test`, `npm run
      test:frontend`).
- [ ] **Vite production build** — covered by CI (`npm run build`); if deploying manually
      instead of via `deploy.yml`, run `python -m tools.dev release-check` locally and
      confirm `npm run build` succeeds from the same SHA before deploying — the Dockerfile
      re-builds it, but a red build should be caught here, not in `gcloud run deploy`.
- [ ] **Legacy `/app` regression** — manual smoke: open `/app` in Telegram or a browser,
      play one Daily guess, confirm no console errors. `/app` is the production default
      until [#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81).
- [ ] **`/app/v2` regression** — same smoke on `/app/v2`
      ([miniapp.md](miniapp.md)). Both exist in production; both must work regardless of
      which is the default.
- [ ] **Dataset validation** — covered by CI (`data/*.json` schema check,
      `scripts/dataset_report.py --strict`).
- [ ] **Dataset regression** — covered by CI (`scripts.dataset_regression --check` against
      `data/dataset_baseline.json`).
- [ ] **CHANGELOG** — `## [Unreleased]` has the entries for what's shipping, or the release
      is explicitly a no-user-facing-change release (documented as such, not silently
      empty). `python -m tools.release check` fails a tagged release with an empty or
      missing matching entry.
- [ ] **Version bump** — `python -m tools.release bump <level>` run and reviewed (§1 for
      which level), or confirmed unnecessary (pure infra change with no CHANGELOG entry —
      rare, justify it).
- [ ] **Post-deploy smoke** — §11 matrix run after deploy, not skipped because CI was green
      (CI runs against the emulator and unit-level fakes, not the deployed Cloud Run
      revision talking to real Telegram/Firestore).

### Conditional — check applicability, then either do it or mark N/A with a one-line reason

- [ ] **Firestore migrations** (§8.1) — required only if the release changes what a
      document/collection looks like in a way old and new code disagree about.
- [ ] **Backup readiness** (§8.2) — required only alongside a Firestore migration or any
      operation that rewrites/deletes existing documents.
- [ ] **Cloud Run build/deploy config** — required only if `Dockerfile`, `deploy.yml`, or
      Cloud Run flags (region, `--max-instances`, etc.) changed; re-read
      [deploy.md § Cloud Run](deploy.md#1-cloud-run-bot) for what changed.
- [ ] **Environment variables/secrets** — required only if the release adds/renames a
      variable the service reads at startup; see
      [deploy.md § env vars](deploy.md#variabili-dambiente--secret-sul-servizio) and
      [runtime-hardening.md](runtime-hardening.md) — a required var missing at Cloud Run
      startup fails the revision, not silently degrades.
- [ ] **Cloud Tasks queues** (§9 below) — required only if the release changes task
      payloads, adds a new internal endpoint under `/internal/*`, or touches
      `TASKS_QUEUE`/`BROADCAST_QUEUE` handling.
- [ ] **Telegram webhook** (§9) — required only if webhook setup, `WEBHOOK_SECRET`
      handling, or the service URL changes.
- [ ] **Telegram menu/Mini App URL** — required only if `PUBLIC_BASE_URL` changes or which
      Mini App variant the menu button opens changes (currently always `/app`, see
      [deploy.md](deploy.md#mini-app-pulsante-nel-menu-del-bot)).
- [ ] **Daily challenge / scheduler** (§9) — required only if `handlers/daily_job.py`,
      buffer generation, or the Cloud Scheduler job/endpoint contract changes.
- [ ] **Stars/shop/payment sanity** (§9) — required only if `services/shop.py`,
      `handlers/shop_handler.py`, or payment/refund flows change.
- [ ] **Admin sanity** — required only if `admin_ui.py`, `admin_pages/`, or
      `handlers/admin_handler.py` change; confirm Admin starts and the touched page loads.

## 6. Deploy procedure

Unchanged by this issue — this checklist gates the **existing** deploy, it does not replace
it. Automatic: every push to `main` that passes CI deploys to Cloud Run
([deploy.yml](../.github/workflows/deploy.yml), detailed in
[deploy.md](deploy.md#1-cloud-run-bot) and
[ci_cd_pipeline.md](ci_cd_pipeline.md#2-deploy--githubworkflowsdeployyml)). Tagging a
release (§7) records that a specific already-deployed (or about-to-be, if tagging ahead of
the automatic deploy landing) commit is release-ready; it is documentation and a CI gate
(§9), **not** a second deploy trigger — there is no `on: push: tags` deploy job, and none
should be added without a real need for decoupling tag-from-deploy.

## 7. Release tooling — `tools/release.py`

Deterministic, read-only unless noted. Never pushes, tags remotely, or deploys — those stay
explicit operator actions.

```bash
python -m tools.release version          # print the current VERSION
python -m tools.release check            # validate VERSION/CHANGELOG.md/package.json locally
python -m tools.release check --tag v1.2.0   # + validate against a specific tag (used by CI, §9)
python -m tools.release bump patch       # or minor / major — see below
python -m tools.release notes            # print Unreleased notes
python -m tools.release notes 1.2.0      # print the dated section for a released version
```

Also reachable as `python -m tools.dev release-version` / `release-check` / `release-notes`
(read-only commands only — `bump` is intentionally not aliased in `tools.dev` so it isn't
one alias away from an accidental mutation).

`bump <major|minor|patch>`:

- computes the next version from `VERSION` (§1 policy, operator picks the level);
- refuses if `## [Unreleased]` in `CHANGELOG.md` is empty (nothing to release) unless
  `--allow-empty` is passed;
- moves the Unreleased content into a new `## [X.Y.Z] - YYYY-MM-DD` section and blanks
  Unreleased;
- updates `VERSION` and mirrors the value into `package.json`;
- **does not** commit, tag, push, or deploy. Review the diff (`git diff`), commit it, then
  continue to §8.

`check` validates release *metadata* (SemVer format, `package.json` drift, required files
present, CHANGELOG has the entry a tag claims) — it does not re-run the test suite; that's
CI's job (§9 explicitly avoids duplicating it).

## 8. Exact-commit requirement

Release approval always applies to one exact SHA — never "latest main." Before deploying
(or after, when verifying what's live), these four must be the same commit:

```
release version   (VERSION at the tagged commit)
release candidate SHA
CI SHA             (the run that was green)
deployed image SHA (what Cloud Run is actually serving)
```

How to check each in practice:

- **Release candidate SHA**: the commit you ran §5 against — `git rev-parse HEAD` at that
  point, or `python -m tools.release check` (prints it).
- **CI SHA**: the `head_sha` GitHub shows on the CI run you're relying on — don't trust "CI
  is green on main" without opening the run and reading its commit.
- **Deployed image SHA**: `gcloud run services describe guess-the-player --region
  europe-west1 --format='value(status.traffic)'` shows the serving revision; cross-reference
  with `gcloud run revisions describe <revision> --region europe-west1
  --format='value(metadata.labels)'` (Cloud Run stamps the source commit on revisions
  created via `--source .` deploys) or the Cloud Build log for that revision.
- **Release version**: the deployed revision's `/` endpoint now returns
  `{"message": "...", "version": "X.Y.Z"}` (§2) — compare it to `VERSION` at the SHA you
  believe is deployed.

Never write "latest main passed" in release evidence (§12) — write the SHA.

### 8.1 Firestore migration gate

The checklist (§5) must say whether a release needs a Firestore/data migration — most don't.
When it does:

- the migration step is deliberate and separate from the code deploy, not implied by it
  (code deploys automatically on CI green; a migration script does not run itself);
- a backup exists first — see §8.2, this gate cannot be satisfied without it;
- dry-run/validation first where the migration script supports it (see existing patterns in
  `scripts/migrate_firestore.py`, `scripts/backfill_users.py` —
  [operations.md](operations.md#manual-operational-responsibilities));
- a rollback/recovery note is written down: what "undo" means for *this specific* migration
  (restoring from the backup taken above, or a documented reverse transform) — not a generic
  "we have backups" statement.

This issue (#49) does not implement disaster recovery — it only ensures the release process
knows when this gate applies and blocks on it. See §8.2.

### 8.2 Backup gate

**Current gap, stated plainly:** `scripts/backup_firestore.py` does not export `referrals`,
`app_duels`, or `group_rounds` (see
[operations.md § Backup and recovery state](operations.md#backup-and-recovery-state)), and
**no restore procedure has ever been run or documented**. An export existing is not the same
as recovery being proven.

Consequences for this checklist:

- A release **cannot** claim "disaster-recovery readiness" — that checkbox does not exist
  here on purpose. Full backup/restore is
  [#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50), tracked
  separately and not implemented by #49.
- Any release with a risky data migration (§8.1) requires a **freshly taken, verified**
  backup (`python scripts/backup_firestore.py`, confirm the output file is non-empty and
  covers the collections the migration touches) before the migration runs — this is the
  minimum, not a substitute for #50.
- If the migration touches `referrals`, `app_duels`, or `group_rounds`, the gap above means
  the automatic backup doesn't cover it: back those up manually
  (`--collections referrals,app_duels,group_rounds`) or treat the migration as higher-risk
  and get a second reviewer before running it.

## 9. CI release gate — `release-check.yml`

[`.github/workflows/release-check.yml`](../.github/workflows/release-check.yml) triggers on
pushing a `v*.*.*` tag and runs `python -m tools.release check --tag "$GITHUB_REF_NAME"`.
`permissions: contents: read` — nothing else, no deploy credentials, no write access. It
does **not** re-run `pytest`, `ruff`, `mypy`, or the frontend build: by the exact-commit
policy above, a tag only ever gets pushed on a SHA whose `CI` workflow already passed, so
re-running those checks here would duplicate `ci.yml` without adding information. What it
adds instead: automated confirmation that `VERSION` on the tagged commit matches the tag,
and that `CHANGELOG.md` has a dated entry for it — the two things `ci.yml` has no reason to
know about. A red `release-check` run means the tag was pushed against
metadata that doesn't match it (wrong `VERSION`, forgotten `tools.release bump`, or a typo'd
tag) — fix and re-tag, don't ignore it.

### Telegram-specific checks (part of §5's conditional items)

Where relevant to what changed: bot starts (Cloud Run revision reaches "Ready", no crash
loop in logs); webhook responds (`GET /` returns 200 with the current version, per §2/§8);
`WEBHOOK_SECRET` present (service fails closed at startup if missing —
[runtime-hardening.md](runtime-hardening.md)); Telegram menu button still targets `/app`
under the current `PUBLIC_BASE_URL` (send `/start` to the bot, tap the menu button); if
command registration changed, `/help` in Telegram shows the updated list. None of this
contacts production Telegram APIs from automated tests — it's manual, against the deployed
service, using the bot itself.

### Cloud Tasks checks (part of §5's conditional items)

Where relevant: `TASKS_QUEUE` and `BROADCAST_QUEUE` still resolve (service fails startup
otherwise, per [runtime-hardening.md](runtime-hardening.md)); if a release adds/changes an
`/internal/*` endpoint, confirm the corresponding queue's target URL matches
`PUBLIC_BASE_URL`. Full queue/secret setup is documented once in
[runtime-hardening.md](runtime-hardening.md) — this checklist doesn't repeat it, only says
when to re-check it.

### Daily challenge / scheduler checks (part of §5's conditional items)

Where relevant: `GENERATION_SECRET` present; Cloud Scheduler job `daily-generation` still
points at `<PUBLIC_BASE_URL>/internal/daily-job`
([deploy.md § Cloud Scheduler](deploy.md#2-cloud-scheduler-generazione-contenuti)); the Daily
buffer has upcoming days after deploy (`/admin_status` or `/admin_next`) — a release must not
leave the next Daily unavailable. Daily selection logic itself is out of scope for #49.

### Stars/shop conditional checks (part of §5's conditional items)

Only for releases touching Shop/payments — manual/safe verification, **never** a real paid
transaction in CI or as part of this checklist:

- catalog loads (`/shop` in both `/app` and `/app/v2`);
- purchase initiation reaches Telegram's payment sheet (no completed charge needed to
  verify this);
- a delivery/reconciliation check on a *past* known purchase (via `/admin_support_reply` /
  purchase history), not a new one;
- equip flow works on an already-owned item;
- purchase history and `/paysupport` → `/admin_refund` path are reachable (don't execute a
  refund against a real charge as part of a routine release check).

## 10. Rollback

Two different cases — pick the right one, they are not interchangeable:

**Code-only release (no data migration).** Route Cloud Run traffic back to the previous
known-good revision, or redeploy from the previous release's exact SHA (§8) — manual today,
as already documented in
[operations.md](operations.md#release-state) and
[ci_cd_pipeline.md](ci_cd_pipeline.md#cosa-resta-aperto):

```bash
gcloud run services update-traffic guess-the-player \
  --region europe-west1 --to-revisions <previous-revision>=100
```

**Release with a Firestore migration.** Routing traffic back is not sufficient — old code
may not understand data the migration already changed. Recovery requires the
migration-specific plan and backup written down in §8.1/§8.2 for *that* migration; there is
no generic automated path. This is exactly the gap #50 exists to close — until then, rolling
back a data migration is a manual, case-by-case recovery, not a one-command rollback.

In both cases, record in release evidence (§12) the exact known-good version/SHA/image you
rolled back to — not "the previous one," the actual identifier (§8).

## 11. Post-deploy smoke matrix

Run against the live deployed revision, not the CI emulator. Required rows first:

| Check | Required? | How |
| --- | --- | --- |
| Health/startup | Required | `GET /` returns 200 with the expected `version` (§2) |
| Telegram bot | Required | `/start` in Telegram gets a response |
| Daily | Required | `/show` returns today's challenge |
| `/app` | Required | Opens, one guess submits successfully |
| `/app/v2` | Required | Opens, one guess submits successfully |
| Authenticated API | Required | One `/app/api/*` call succeeds with a real Telegram `initData` |
| Arena/Training | Conditional | If those modes were touched — one round each |
| Leaderboard | Conditional | If ranking/leagues were touched |
| Shop/Profile | Conditional | If shop/profile were touched — see §9 Stars checks |
| Admin startup | Conditional | If `admin_ui.py`/`admin_pages/` were touched |
| Scheduled job configuration | Conditional | If the Daily/scheduler contract changed — see §9 |

Not every release needs the conditional rows exercised destructively; mark N/A with a reason
when a row doesn't apply, same as §5.

## 12. Release evidence

Recorded per release, lightweight and version-controlled rather than a spreadsheet: the git
tag `vX.Y.Z` plus, if useful for a given release, a
[GitHub Release](https://github.com/michelecoppi/guess_the_player_from_the_path/releases)
on that tag. Body derives from `python -m tools.release notes X.Y.Z` (verbatim CHANGELOG
content — this tool does not generate marketing copy, just reformats what's already
written). Record, either in the GitHub Release body or the release PR:

```
version:          X.Y.Z
date:              YYYY-MM-DD
git SHA:           <exact commit, §8>
CI run:            <URL/ID of the green run for that SHA>
image identifier:  <Cloud Run revision name, §8>
migration status:  none | done (link migration + backup evidence, §8.1)
backup status:     n/a | fresh export confirmed (§8.2) — never "disaster-recovery verified"
deployer:          <who ran/approved this>
smoke result:      pass | issues (link them)
rollback target:   <previous known-good version/SHA/revision, §10>
notes:             <anything a future operator needs that isn't in CHANGELOG>
```

## 13. Tag convention

`vX.Y.Z`, created **after** the exact commit (§8) is approved as release-ready — never
before, never on an assumption that a commit will pass. Locally:

```bash
git tag -a v1.2.0 -m "v1.2.0"
git push origin v1.2.0
```

Pushing the tag triggers `release-check.yml` (§9). No PAT-based automation creates tags —
this stays an explicit, manual operator action; `tools/release.py` never touches git.

## 14. Docker/image traceability

`gcloud run deploy --source .` builds via Cloud Build and uploads to Artifact Registry
(`docs/deploy.md`); there is currently no explicit image label carrying the git SHA beyond
what Cloud Build/Cloud Run already record. To trace a running revision back to a commit
without adding new build steps: Cloud Run revision names are sequential
(`guess-the-player-000NN-xxx`), and each revision's Cloud Build log (Console → Cloud
Build → History, or `gcloud builds list`) records the source it built from. Combined with
the `version` field the running revision now reports at `/` (§2, §8), an operator has: the
app version from the service itself, and the exact build/commit from Cloud Build history for
that revision — no secrets are added to image metadata, and none should be.

## 15. Mini App V2 release context

Documented here because a future rollout issue will use this checklist, and getting the
state wrong would misdirect that work:

- V2 functional migration is complete; the [#61](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/61)
  redesign is complete.
- `/app` (legacy) is still the production default — the Telegram menu button and any
  existing user-facing links point at it.
- `/app/v2` is a released, reachable candidate for the default, not a preview environment —
  both variants must pass §5/§11 on every release, not just the one currently linked.
- [#81](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/81) is the
  final V2 review gate. The rollout/switch itself (making `/app/v2` the default) is a
  **separate future issue**, not part of #49, and will use this checklist when it happens —
  it is a MAJOR release under §1 (a default user-facing surface change).

## Adopting this process

`0.1.0` (§3) marks the point this process starts. It does not retroactively version every
past deploy, and it does not change how `main` deploys today (§6) — it adds a checklist and
optional tagging on top. The first real use of §5–§13 is the next release an operator
chooses to tag; nothing here is enforced by CI beyond `release-check.yml`, which only
activates when a `v*.*.*` tag is pushed.

## Out of scope for #49

Not implemented by this document or its tooling — see the linked issues:
[#18](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/18)
(Sentry/structured logging — §2 only prepares the boundary),
[#50](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/50)
(backup/restore — §8.2 only states the gate),
[#51](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/51)
(feature flags), [#29](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/29)
(analytics), and the V2 rollout issue referenced in §15.
