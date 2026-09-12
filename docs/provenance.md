# Player-Data Provenance Model

## 1. Overview & Principles

The Candidate Player ingestion pipeline integrates external sources (such as Wikipedia and Wikidata) to discover, fetch, normalize, and review footballer profiles before promotion into the game.

The **Player-Data Provenance** system (#27) provides field-level lineage for every imported fact without polluting the public production dataset (`data/players.json`).

### Core Principles

1. **Granular Field-Level Lineage:** Provenance is not a monolithic string attached to a player. Every individual attribute (`full_name`, `birth_year`, `nationality`, `position`, `career[0].team`, etc.) tracks its specific source observations.
2. **Multi-Source Conflict Preservation:** When Wikipedia and Wikidata disagree, neither is discarded. Both observations are preserved alongside their raw values, allowing human reviewers in the Review Queue (#15) to evaluate the discrepancies.
3. **Traceable Normalization:** Normalization transformations (#26) record both the raw input and normalized output, linking the transition directly to normalization finding codes (e.g. `CLUB_NORMALIZED`).
4. **Stable Career Stop Identity:** Career stops possess an internal `_stop_id` that is immune to array index changes caused by canonical career ordering (`order_career`).
5. **Explainable Confidence:** Confidence scores are strictly deterministic, rule-based, and explainable, avoiding arbitrary floating-point numbers.
6. **Strict Production Isolation:** Provenance structures are strictly internal. `data/players.json` remains lean and unmodified.

---

## 2. Provenance Domain Schema

The provenance model is implemented in `services/candidate_provenance.py` and serialized inside `CandidatePlayer.provenance`.

```text
CandidatePlayer
 └── provenance: CandidateProvenance
      └── fields: dict[str, FieldProvenance]
           ├── "full_name" ──► FieldProvenance
           │                    ├── observations: [SourceObservation (Wikipedia), ...]
           │                    └── transformations: [NormalizationRecord, ...]
           ├── "nationality" ─► FieldProvenance
           │                    └── observations: [SourceObservation (Wikidata), ...]
           └── "career[0].team" ─► FieldProvenance
                                 ├── stop_id: "wikipedia_stop_roma_0"
                                 ├── observations: [
                                 │     SourceObservation (Wikipedia: "Roma"),
                                 │     SourceObservation (Wikidata: "AS Roma")
                                 │   ]
                                 └── transformations: [NormalizationRecord ("Roma" -> "Roma")]
```

### 2.1 `ConfidenceLevel` & Scores

Confidence is represented by the `ConfidenceLevel` enum and mapped to fixed float scores:

| Confidence Level | Score | Description |
| :--- | :--- | :--- |
| `EXACT_STRUCTURED` | `1.00` | Direct claim from a structured database entity (e.g., Wikidata claim for birth year `P569`, nationality `P27`, team membership `P54`). |
| `PARSED_CLAIM` | `0.90` | Semi-structured key-value extracted from high-reliability templates (e.g., Wikipedia `{{Bio}}` or `{{Sportivo}}` infobox). |
| `PARSER_DERIVED` | `0.75` | Derived via regular expressions, heuristic parsing, or wikilink targets (e.g., career text extraction). |
| `INFERRED_NORMALIZED` | `0.60` | Value standardized or enriched via repository canonical dictionaries or alias mappings (e.g. `"PSG"` → `"Paris Saint-Germain"`). |
| `AMBIGUOUS` | `0.30` | Conflicting or ambiguous values flagged for human review. |

> [!NOTE]
> High confidence never causes automatic approval of candidate data into `data/players.json`. Approval always requires explicit workflow authorization (#15 / #35).

### 2.2 `SourceObservation`

Represents an individual source observation:

```json
{
  "source": "wikipedia",
  "source_id": "Francesco_Totti",
  "retrieved_at": "2026-09-12T02:00:00Z",
  "confidence": 0.9,
  "confidence_level": "parsed_claim",
  "raw_value": "Roma",
  "normalized_value": "Roma",
  "source_url": "https://it.wikipedia.org/wiki/Francesco_Totti",
  "metadata": {
    "page_id": 12345,
    "template": "Sportivo"
  },
  "adapter_version": "wikipedia_v1"
}
```

### 2.3 `FieldProvenance`

Aggregates observations and normalization steps for a field path:

- `field_path`: Stable field path (e.g. `"full_name"`, `"nationality"`, `"career[0].team"`).
- `stop_id`: Internal stable stop identity for career stops.
- `current_value`: Active value currently on `CandidatePlayer`.
- `normalized_value`: Consolidated normalized value.
- `observations`: List of `SourceObservation` records from all contributing sources.
- `transformations`: List of `NormalizationRecord` history.
- Helper methods:
  - `has_conflict() -> bool`: Returns `True` if different sources provide conflicting values.
  - `has_multiple_sources() -> bool`: Returns `True` if two or more distinct sources contributed observations.
  - `supporting_sources(value=None) -> list[str]`: Lists sources that agree with the active or specified value.
  - `conflicting_sources(value=None) -> list[str]`: Lists sources that disagree with the active or specified value.

### 2.4 `NormalizationRecord`

Documents transformations performed during the normalization stage:

```json
{
  "raw_value": "PSG",
  "normalized_value": "Paris Saint-Germain",
  "finding_code": "CLUB_NORMALIZED",
  "rule": "Paese del club 'Paris Saint-Germain' dedotto dal dataset",
  "timestamp": "2026-09-12T02:05:00Z"
}
```

---

## 3. Career Stop Stability Across Reordering

The canonical career ordering algorithm (`order_career`) sorts career stops chronologically and places loans immediately following their parent club.

To ensure that career provenance does not become desynchronized or corrupted when stops are reordered:
1. Each career stop dict in `CandidatePlayer.career` is assigned an internal `_stop_id` (e.g. `"wikipedia_stop_roma_0"`).
2. The corresponding `FieldProvenance` stores `stop_id`.
3. When `normalize_candidate` executes `order_career`, it immediately calls:
   ```python
   candidate.provenance.reindex_career_paths(ordered_stops)
   ```
4. This re-indexes the array notation (`career[0].team` ↔ `career[1].team`) according to the new positions of `_stop_id`, guaranteeing that indexed paths remain accurate without losing observation history.

---

## 4. Multi-Source Conflicts & Review Queue Integration (#15)

When merging data from both Wikipedia and Wikidata:
- If both sources report the same value (e.g. birth year `1987`), both observations are recorded. `has_conflict()` is `False`, and `supporting_sources()` returns `["wikipedia", "wikidata"]`.
- If sources disagree (e.g. Wikipedia reports `"Inter Milan"` and Wikidata reports `"Inter"`, or differing appearance counts):
  - Both observations remain recorded in `FieldProvenance.observations`.
  - If normalization resolves them to the same canonical club (`"Inter"`), `has_conflict()` is `False` with both listed as supporting sources.
  - If values remain in disagreement, `has_conflict()` returns `True`.

### Consumption by #15 Review Queue

The future Review Queue interface will read:
1. `candidate.provenance.has_conflicts()` to identify candidate profiles requiring conflict resolution.
2. `field_provenance.observations` to display side-by-side source comparisons to the reviewer (e.g., "Wikipedia says X, Wikidata says Y").
3. `candidate.provenance.get_provenance_for_path(finding.field_path)` to immediately display which source generated a problematic or missing value when inspecting validation findings.

---

## 5. Public / Internal Boundary

| Data Element | Stored in Candidate Ingestion (`data/candidates/*.json`) | Stored in Production (`data/players.json`) |
| :--- | :---: | :---: |
| Approved profile & career | Yes | Yes |
| Field-level observations (`SourceObservation`) | Yes | **No** |
| Source URLs & retrieval timestamps | Yes | **No** |
| Internal career stop IDs (`_stop_id`) | Yes | **No** |
| Raw API payloads (`raw_payload`, `raw_data`) | Yes | **No** |
| Normalization audit records (`transformations`) | Yes | **No** |
