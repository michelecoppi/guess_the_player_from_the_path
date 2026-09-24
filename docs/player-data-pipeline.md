# Player data pipeline

Authoritative description of how footballer data enters the game. Field-level lineage
is specified in [provenance.md](provenance.md); the popularity scale and difficulty
formula in [difficolta.md](difficolta.md); the dataset schema and the legacy import
commands in the root [README](../README.md) (“Ampliare il dataset dei calciatori”).

## Production dataset and its invariant

- **Production data is [`data/players.json`](../data/players.json)**, versioned in Git,
  read by `services/player_pool.py` and baked into the Cloud Run image. Only
  `verified: true` players with complete careers are selectable for Daily and events;
  `practice_only: true` players feed Training, duels and group rounds only.
- A change to `data/players.json` reaches production only through commit → PR → CI →
  deploy. CI blocks integrity problems (`scripts/dataset_report.py --strict`) and
  directional regressions of quality metrics (valid players, unknown clubs, duplicates,
  career validation errors) against
  [`data/dataset_baseline.json`](../data/dataset_baseline.json)
  (`python -m scripts.dataset_regression --check`).
- A runtime, Firestore-backed override (`/admin_block`, stored in
  `admin_settings/dataset_overrides`) can exclude a player immediately without a
  deploy; it does not edit the dataset.

> **Critical invariant.** Candidate ingestion must never mutate the production player
> dataset without explicit, authorized human approval. Only
> `CandidateReviewService.approve_candidate` (also reached through `edit_and_approve`)
> writes `data/players.json`, and only after admin authorization, revision check,
> validation and conflict checks. High source confidence never auto-approves.

## Two ingestion paths exist today

| Path | Status | Entry points | Writes |
| --- | --- | --- | --- |
| **Legacy batch import** | In use; the path that built the current dataset | `scripts/wikipedia/build_wiki.py` / `refresh_careers.py` produce a batch in `data/incoming/` (gitignored) → `scripts/import_players.py [--dry-run] [--update] [--verified]` | `data/players.json` directly (new players stay `verified: false` unless `--verified`) |
| **Candidate pipeline** (#13) | Implemented as services + Admin Review Queue | `domains/players/adapters/`, `services/candidate_*.py`, `domains/players/candidates/repository.py`, Admin “🔎 Review giocatori” | `data/candidates/*.json` (gitignored); `data/players.json` only on approval |

Local corrections to existing players (popularity, verified, practice-only, league of
a career stop, difficulty weights) go through the Admin “Dataset” page and
`services/dataset_editor.py`, which validates and writes a backup to `backup/` first.

## Candidate pipeline

```text
discover ──► ingest ──► normalize ──► validate ──► review ──► approve
DISCOVERED   FETCHED    NORMALIZED    VALIDATED    REVIEW_REQUIRED / READY   APPROVED
                                                   └──────── reject ───────► REJECTED
```

| Stage | Module | What happens |
| --- | --- | --- |
| Model + FSM | [`domains/players/candidates/model.py`](../domains/players/candidates/model.py) | `CandidatePlayer` with deterministic id, `CandidateState`, explicit `ALLOWED_TRANSITIONS` (invalid moves raise `InvalidStateTransitionError`), transition history, structured errors, retry counter, revision token. `APPROVED`/`REJECTED` are terminal |
| Repository | [`domains/players/candidates/repository.py`](../domains/players/candidates/repository.py) | Abstract repository; in-memory (tests) and file-backed (`data/candidates/`, atomic writes, process file lock, `save_if_revision` compare-and-set). Never touches `data/players.json` |
| Discover + ingest | [`domains/players/adapters/`](../domains/players/adapters/) | `PlayerSourceAdapter` contract with `WikipediaAdapter` (it.wikipedia infobox, reusing `scripts/wikipedia/wiki.py` parsing) and `WikidataAdapter` (entity claims); injectable HTTP client; structured `AdapterError` types (transport, parse, not_found, timeout, rate_limit). `candidate_integration.populate_candidate_from_result` merges results with provenance and moves `DISCOVERED → FETCHED`; failures are recorded on the candidate |
| Normalize | [`domains/players/candidates/normalization.py`](../domains/players/candidates/normalization.py), [`services/career_order.py`](../services/career_order.py) | Idempotent cleanup: wiki markup, club/league aliases from repository standards, nationality/position, aliases, canonical career order; records `NormalizationRecord`s; `FETCHED → NORMALIZED` |
| Validate | [`domains/players/candidates/validation.py`](../domains/players/candidates/validation.py), [`domains/players/candidates/finding.py`](../domains/players/candidates/finding.py) | Deterministic findings (ranges, overlaps vs loans, unresolved QIDs, ambiguous aliases vs production, multi-country clubs); zero ERROR findings → `VALIDATED`, otherwise `REVIEW_REQUIRED`. `process_candidate` chains normalize + validate |
| Provenance | [`domains/players/candidates/provenance.py`](../domains/players/candidates/provenance.py) | Per-field observations, confidence levels, conflicts, stable career stop ids — see [provenance.md](provenance.md) |
| Review + approve | [`domains/players/candidates/review.py`](../domains/players/candidates/review.py) | `CandidateReviewService`: queue/detail projections, duplicate suggestions, edit allow-list with re-normalization/re-validation, approve, reject, merge into an existing player, source-wrong, retry ingestion |
| Admin UI | [`admin_pages/player_review.py`](../admin_pages/player_review.py) | Human interface only; every mutation calls the service with the revision shown on screen |

### Approval boundary

`approve_candidate` requires an `AdminIdentity` whose id is in `ADMIN_TELEGRAM_IDS`,
the candidate in a reviewable state, the expected revision, a passing validation and no
unresolved provenance conflict (excluding observations from sources explicitly marked
wrong). Under a process-wide lock on the production file the
service loads `data/players.json` fail-closed (missing/corrupt data aborts), writes a
collision-safe backup to `backup/`, writes atomically (temp file + `fsync` +
`os.replace`) and rolls back on failure. The result is a local file change that must
still be reviewed and merged like any other data change.

`merge_candidate` (same authorization, state and revision checks) only records that the
candidate corresponds to an existing production player and marks it `APPROVED`; it
does not modify `data/players.json`. `reject_candidate` is terminal.

### SOURCE_WRONG and retry

- **Source wrong** (`mark_source_wrong`) records that a source — optionally a single
  entity (a Wikipedia page, a Wikidata QID) — is unreliable for this candidate. Evidence
  and provenance are kept for audit, observations from that source stop counting as
  blocking conflicts, and the candidate stays non-terminal in `REVIEW_REQUIRED` so it
  can be edited or retried.
- **Retry ingestion** (`retry_ingestion`) re-fetches through the existing adapters with
  an explicitly selected source and re-runs the pipeline. Retrying only a source that
  was marked unreliable, without an alternative, returns `SOURCE_ERROR` instead of
  silently reusing it.

### Provenance vs production data

Provenance (observations, source URLs, retrieval timestamps, raw payloads,
`_stop_id`, normalization history) lives only in `data/candidates/`. Promotion copies
the approved profile and career into the lean production schema; none of the lineage
data is written to `data/players.json` and none of it is served to players.

## Source/activity backfill and career refresh

The maintenance flow for existing production players has two distinct steps:

1. `python scripts/backfill_player_source_and_activity.py --dry-run` resolves missing
   `source`/`source_id` values. Wikipedia exact-title lookups are sent through batched
   `action=query` requests; only unresolved names fall back to search and Wikidata.
   Remove `--dry-run` only after reviewing the summary. The script never rewrites the
   local `career`.
2. Career refresh, from the Admin **Refresh carriera** page or, for long runs such as the
   end of a transfer window, from the CLI:

   ```bash
   python scripts/refresh_player_careers.py --all [--dry-run]    # active + unknown-activity players
   python scripts/refresh_player_careers.py --all --resume 12    # skip players checked in the last 12 h
   python scripts/refresh_player_careers.py --player dusan_vlahovic --player "Rafael Leao"
   python scripts/refresh_player_careers.py --ids-file data/logs/career_refresh_failed.txt
   ```

   Both call `domains.players.career_refresh.refresh_players`. Players are processed in
   chunks (default 20): the Wikipedia revisions of a chunk are fetched with one bulk
   request outside the lock, then the chunk is applied and written **once** under the
   lock. The dataset is backed up once per run, before the first write. Finished chunks
   stay saved when a run is interrupted, and a failed player keeps no
   `career_last_checked_at`, so `--resume` (Admin: "salta i già controllati") only
   retries what is missing. The CLI writes failed ids to
   `data/logs/career_refresh_failed.txt` and exits non-zero when any player failed.

Every Wikimedia call, from the adapters and from the legacy `scripts/wikipedia/wiki.py`,
goes through `RetryingHttpClient`. Since the 2026
[global API rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits),
a User-Agent without contact info (full URL or email) is classified as *Unidentified*:
10 requests/minute across all Wikimedia projects, then 429s. The User-Agent is built by
`build_user_agent()` and always carries the project URL; set `WIKIMEDIA_CONTACT` to an
email to add one. Requests from one process are spaced at least 1 s apart (≤ 60/min,
well below the 200/min identified limit), and use `maxlag=5`, bounded exponential retry
(also on read/connect timeouts) and `Retry-After`. `scripts/wikipedia/refresh_careers.py`
ignores wikitext cached before the run starts, so it never re-reads pre-transfer pages;
`GTP_WIKI_CACHE_NOT_BEFORE` (epoch seconds) does the same for the other legacy scripts. A bulk chunk that still times
out is split in half and retried, so one slow page does not fail its neighbours; a
player whose bulk result failed transiently is retried once with a single request. If
the source returns nothing for two chunks in a row (Wikipedia down or rate limiting),
the run stops and the remaining players are reported as not attempted instead of
retrying for hours. A temporary transport/rate-limit failure remains retryable and
must not be logged as a genuine “no match”. The batch API records the source revision
and Wikidata id when supplied, so later runs can be audited.

`active` is deliberately optional. It is recalculated only from a career returned by
the source in the current run; an empty or failed fresh result leaves activity unknown
instead of inferring retirement from stale local data. Players with unknown activity
remain eligible for a later refresh, while `active: false` players are excluded from the
normal bulk refresh. When Wikipedia supplies an explicit `terminecarriera` date, that
date takes precedence over the coarser year of the last career stop; this avoids keeping
a player active for the rest of the calendar year after a dated retirement.

## Parent issue #13: documentation audit (2026-09-14)

[#13](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/13) is still
open; its sub-issues #14, #26, #15, #27 and the Admin integration #35 are done. Against
its stated scope:

| #13 criterion | Evidence on `main` |
| --- | --- |
| Candidate model with the eight states | `CandidateState`, `ALLOWED_TRANSITIONS` |
| Modular structure for ingestion, models and repository | adapters / normalization / validation / provenance / review modules, repository abstraction |
| Persistence of results and error handling | file-backed repository with CAS; structured adapter errors and candidate error log |
| Import does not modify production without approval | only the review service writes `data/players.json`, behind admin authorization |
| Candidate state is inspectable and repeatable | state history, revisions, Admin queue; retry re-runs the pipeline |
| Tests for transitions and main failures | `tests/test_candidate_*.py`, `tests/test_adapters.py`, `tests/test_admin_player_review.py` |

Gap worth checking in the closure audit: there is **no end-to-end discovery runner**
(CLI, script or job) that creates `DISCOVERED` candidates from a search and persists
them after `process_candidate`. The stages exist as callable services and the Review
Queue can retry ingestion, but bulk discovery is still performed with the legacy
`scripts/wikipedia/` + `scripts/import_players.py` path. Whether that is required for
“sostituire il flusso manuale” is a decision for the #13 closure audit, not for this
document.

## Planned evolution

- [#25](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/25) — Dataset
  Health dashboard. Today: `services/dataset_health.py`, `/admin_pool`,
  `scripts/dataset_report.py` and the Admin “Dataset” health tab.
- [#21](https://github.com/michelecoppi/guess_the_player_from_the_path/issues/21) —
  data-driven difficulty model: rule-based prediction compared with observed Daily results
  ([difficolta.md §6](difficolta.md)).
