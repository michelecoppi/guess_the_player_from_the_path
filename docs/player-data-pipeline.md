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
| **Candidate pipeline** (#13) | Implemented as services + Admin Review Queue | `services/adapters/`, `services/candidate_*.py`, `services/repos/candidates.py`, Admin “🔎 Review giocatori” | `data/candidates/*.json` (gitignored); `data/players.json` only on approval |

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
| Model + FSM | [`services/candidate_player.py`](../services/candidate_player.py) | `CandidatePlayer` with deterministic id, `CandidateState`, explicit `ALLOWED_TRANSITIONS` (invalid moves raise `InvalidStateTransitionError`), transition history, structured errors, retry counter, revision token. `APPROVED`/`REJECTED` are terminal |
| Repository | [`services/repos/candidates.py`](../services/repos/candidates.py) | Abstract repository; in-memory (tests) and file-backed (`data/candidates/`, atomic writes, process file lock, `save_if_revision` compare-and-set). Never touches `data/players.json` |
| Discover + ingest | [`services/adapters/`](../services/adapters/) | `PlayerSourceAdapter` contract with `WikipediaAdapter` (it.wikipedia infobox, reusing `scripts/wikipedia/wiki.py` parsing) and `WikidataAdapter` (entity claims); injectable HTTP client; structured `AdapterError` types (transport, parse, not_found, timeout, rate_limit). `candidate_integration.populate_candidate_from_result` merges results with provenance and moves `DISCOVERED → FETCHED`; failures are recorded on the candidate |
| Normalize | [`services/candidate_normalization.py`](../services/candidate_normalization.py), [`services/career_order.py`](../services/career_order.py) | Idempotent cleanup: wiki markup, club/league aliases from repository standards, nationality/position, aliases, canonical career order; records `NormalizationRecord`s; `FETCHED → NORMALIZED` |
| Validate | [`services/candidate_validation.py`](../services/candidate_validation.py), [`services/candidate_finding.py`](../services/candidate_finding.py) | Deterministic findings (ranges, overlaps vs loans, unresolved QIDs, ambiguous aliases vs production, multi-country clubs); zero ERROR findings → `VALIDATED`, otherwise `REVIEW_REQUIRED`. `process_candidate` chains normalize + validate |
| Provenance | [`services/candidate_provenance.py`](../services/candidate_provenance.py) | Per-field observations, confidence levels, conflicts, stable career stop ids — see [provenance.md](provenance.md) |
| Review + approve | [`services/candidate_review.py`](../services/candidate_review.py) | `CandidateReviewService`: queue/detail projections, duplicate suggestions, edit allow-list with re-normalization/re-validation, approve, reject, merge into an existing player, source-wrong, retry ingestion |
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
  data-driven difficulty model (today: rule-based, [difficolta.md](difficolta.md)).
