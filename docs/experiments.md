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
  must use the control behavior in that case.
- `services/repos/experiments.py` stores up to 100 records in
  `admin_settings/experiments` and changes them in Firestore transactions. Corrupt
  stored records stop writes. The existing backup of the `admin_settings` collection
  includes this document.
- `scripts/experiments.py` is the operator interface. All starts require a metric
  selected from the implemented `CORE_METRICS` definitions in
  `services/product_analytics_query.py`, enabled product analytics with its identity
  salt, and configured read access for the PostHog query API. A missing credential or
  an unknown metric refuses the start. No experiment is started by deployment.

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

After implementing the treatment and a variant-segmented PostHog insight, verify
`POSTHOG_API_KEY`, `PRODUCT_ANALYTICS_SALT`,
`PRODUCT_ANALYTICS_ENABLED`, `POSTHOG_PERSONAL_API_KEY` and
`POSTHOG_PROJECT_ID`, then start:

```bash
python scripts/experiments.py start daily_intro_v1
python scripts/experiments.py assign daily_intro_v1 --user 123456789
```

An experiment cannot be finished before its scheduled duration. Record a bounded
summary and an HTTPS link to the metric breakdown, then a decision:

```bash
python scripts/experiments.py finish daily_intro_v1 --summary "Treatment improved completion by 3 points" --evidence-url https://example.com/posthog/result
python scripts/experiments.py decide daily_intro_v1 --decision ship
```

Decisions are `ship`, `iterate`, or `stop`. Results and decisions cannot be set
before the preceding lifecycle step. Record the actual analysis in PostHog; this
registry does not perform significance testing or claim causal impact by itself.
