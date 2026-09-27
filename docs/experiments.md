# Experiments

The experiment registry (#52, completing #22) is separate from operational feature
flags. Flags can roll out or disable a feature without a deploy; that alone is not a
measured experiment. An experiment records a hypothesis, a predefined success metric,
control and treatment descriptions, duration, result evidence, and a decision.

## Current implementation

- `services/experiments.py` validates the plan and lifecycle and assigns users or
  groups deterministically to `control` or `treatment` during the scheduled window.
  The SHA-256 bucket includes the experiment key and subject type; raw ids are never
  stored in the registry. `assign(key, user_id=...)` is the runtime entry point:
  it returns a variant at the treatment boundary and captures an
  `experiment_assigned` exposure with bounded `experiment_key` and `variant`
  properties. The existing analytics identity pseudonymization applies. If analytics
  is disabled or the registry cannot be read, it returns `None`; treatment callers
  must use the control behavior in that case. A replica caches the registry for at
  most five seconds and serializes refreshes, so concurrent assignments share one
  Firestore read. A failed refresh discards the expired snapshot and returns control.
  The assignment checks the scheduled end time on every call, even with a cached
  registry, so expiry takes effect immediately. A stop invalidates the cache in the
  process that writes it; other replicas observe the persisted stop within five
  seconds. After a restart, the first assignment reads Firestore again. If that
  read fails, it returns control rather than using an old snapshot.
- `services/repos/experiments.py` stores up to 100 records in
  `admin_settings/experiments` and changes them in Firestore transactions. Corrupt
  stored records stop writes. The existing backup of the `admin_settings` collection
  includes this document.
- `scripts/experiments.py` is the operator interface. All starts require a metric
  selected from the implemented `CORE_METRICS` definitions in
  `services/product_analytics_query.py`, enabled product analytics with its identity
  salt, and configured read access for the PostHog query API. A missing credential or
  an unknown metric refuses the start. Before the registry transaction, `start`
  executes the selected metric's read-only HogQL report query in the configured
  PostHog project. API errors and malformed responses refuse the start; an empty
  result is expected before the first exposure and is accepted. The transaction
  verifies that the selected metric has not changed since preflight. No experiment
  is started by deployment.
- `report` reads the exposed cohort by pseudonymous `distinct_id`. The first
  `experiment_assigned` event in the experiment window fixes each user in one
  variant, so repeat exposures do not increase the sample. Metric events are
  counted only after that exposure and before the scheduled end or an early stop.
  It prints the sample, numerator, denominator (completed Daily count for the
  attempts mean), value and interval for each variant. `empty`,
  `insufficient_data` and `query_error` are explicit states. No statistical
  significance or causal effect is claimed. This query returns aggregates only;
  it never displays pseudonymous IDs or raw Telegram identifiers.

The registry provides assignment, but a specific treatment still needs a product
call site that uses `assign` and a PostHog insight that segments the selected
metric by variant. Create those in the same change that introduces a concrete
experiment; do not call a generic flag rollout an A/B result. The CLI `assign`
command is an operator preview and does not alter gameplay or record an exposure.

## Operator procedure

Use the same Firestore credentials as other admin scripts. First choose a metric:

```bash
python scripts/experiments.py metrics
python scripts/experiments.py create daily_intro_v1 --hypothesis "Shorter intro improves Daily completion" --metric daily_completion_rate --duration-days 7 --treatment "Short intro"
python scripts/experiments.py show daily_intro_v1
```

After implementing the treatment, verify
`POSTHOG_API_KEY`, `PRODUCT_ANALYTICS_SALT`,
`PRODUCT_ANALYTICS_ENABLED`, `POSTHOG_PERSONAL_API_KEY` and
`POSTHOG_PROJECT_ID`, then start:

```bash
python scripts/experiments.py start daily_intro_v1
python scripts/experiments.py assign daily_intro_v1 --user 123456789
python scripts/experiments.py report daily_intro_v1
```

To interrupt a running experiment before its scheduled end, record an operator
identity and reason:

```bash
python scripts/experiments.py stop daily_intro_v1 --operator maintainer --reason "Guardrail failed"
python scripts/experiments.py show daily_intro_v1
```

`stop` is terminal and transactional: at most one concurrent operator succeeds;
later attempts are rejected. If a commit fails under contention, retry the stop
and inspect the persisted record before taking further action. It retains the plan,
scheduled window, and already captured PostHog exposures, and stores the stop time,
reason, and operator in the registry.
It prevents new assignments on the writing replica immediately and on other
replicas within the five-second cache TTL. If Firestore is unavailable during a
refresh, assignments return control; a persisted stop remains effective after
service restart. A stopped experiment cannot be finished or decided through this
CLI. The scheduled end also prevents assignments without an operator action.

An experiment cannot be finished before its scheduled duration. Record a bounded
summary and an HTTPS link to the metric breakdown, then a decision:

```bash
python scripts/experiments.py finish daily_intro_v1 --summary "Treatment improved completion by 3 points" --evidence-url https://example.com/posthog/result
python scripts/experiments.py decide daily_intro_v1 --decision ship
```

Decisions are `ship`, `iterate`, or `stop`. Results and decisions cannot be set
before the preceding lifecycle step. Record the actual analysis in PostHog; this
registry does not perform significance testing or claim causal impact by itself.
The report works for running, stopped and finished experiments. For a stopped
experiment its interval ends at the recorded stop time. If a variant has exposed
users but no denominator events, its value is `null` with `insufficient_data`;
zero exposures are `empty`. Retry `query_error` after checking the PostHog Query
API and project permissions. A report value should not be used as evidence of
significance without a separate analysis.

The Shop metric uses the existing event-count definition of
`shop_purchase_completed` / `shop_viewed` for exposed users. Server-side Shop
events currently carry no session identifier, so this aggregate cannot establish
the session-scoped funnel described in `docs/product-analytics.md` §11–12. Use
PostHog's funnel insight for that session-specific interpretation.
