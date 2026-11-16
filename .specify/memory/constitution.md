# OW Study (Overwatch Map Predictor) Constitution

## In short

The rules every feature in this project has to follow. Each principle below says the rule, then
why it exists.

| # | Principle | In plain words |
|---|---|---|
| I | Map is the unit of prediction | We predict one map at a time, not a whole series |
| II | Temporal integrity (non-negotiable) | Nothing used to predict a map may come from that map or later ones |
| III | Documented, verifiable rating math | Every formula is written down first, tested by hand, and compared with a simple win rate |
| IV | Data provenance and cross-checking | Every number traces back to its video and timestamp; raw data is never edited; sources that disagree are logged, not silently overwritten |
| V | Baselines before complexity | A new idea counts only if it beats plain team Elo |
| VI | Reproducibility | One command rebuilds every result, with settings in config files |

## Core Principles

### I. Map Is the Unit of Prediction

- The model MUST predict the outcome of a single **map** (one game of Overwatch), not a
  series/match (Bo3/Bo5/Bo7).
- Every training row, rating update, and evaluation metric MUST be keyed at map level
  (series ID, map number, map name, game mode, date, patch).
- Series-level prediction (e.g., map/mode selection "payout") is out of scope unless added by
  a constitution amendment or explicitly scoped feature spec; when built, it MUST be derived
  from map-level probabilities.

**Rationale**: Rosters, heroes, and bans are fixed for a map; rating updates and features are
only well-defined at that granularity (see `Math_plan.pdf`).

### II. Temporal Integrity (NON-NEGOTIABLE)

- Any feature used to predict a map MUST be computed only from maps played strictly before it.
  Ratings (team, player, player-on-hero, hero) MUST be snapshotted *before* the map's own
  update is applied.
- Train/validation/test splits MUST be chronological. Random shuffled splits and k-fold
  cross-validation across time are prohibited for reported results (use time-series splits).
- Hyperparameters (e.g., Elo `K`, Glicko parameters) MUST be tuned on validation data only;
  the test period MUST be touched only for final reporting.
- Every pipeline stage that produces features MUST have an automated leakage test.

**Rationale**: Sequential rating systems leak the target trivially if updated in the wrong
order; a leaky model looks excellent and is worthless.

### III. Documented, Verifiable Rating Math

- Every strength metric MUST be specified as a formula in project docs before implementation,
  with notation consistent with `Math_plan.pdf`. The initial metric set is:
  - Team Elo: `R_i_new = R_i_old + K(S_ij − μ_ij)`.
  - Player rating via Elo/+/- updates: `p̂_ji = p_ji + K·f(S_ij − μ_ij)`.
  - Time-weighted team strength from players: `m_j = Σ t_jn·p_jn / Σ t_jn`.
  - Player-on-hero strength `h_jik` and hero-weighted player strength
    `p_ji = Σ_k t_jik·h_jik / Σ_k t_jik`.
  - Hero Elo `H_k` (time-weighted across all players of hero `k`), composition strength, and
    ban impact (player strength recomputed with banned hero `x` excluded, `k ≠ x`).
- Each metric implementation MUST have unit tests against hand-computed examples.
- Each metric MUST be validated against its naive counterpart (e.g., hero Elo vs. hero win
  rate; player-on-hero strength vs. player win rate on that hero) and the comparison recorded.
- Rating variants (Elo, Glicko, Glicko-2) MUST share one interface so they are swappable and
  comparable. Patches MUST be represented explicitly (patch ID on every map) so that
  uncertainty or decay can respond to balance changes. Open mathematical questions (e.g., how
  Glicko intervals aggregate across many players of one hero) MUST be documented as
  experiments with stated hypotheses, not assumed correct.

**Rationale**: The project's contribution is the strength model; it must be inspectable,
testable, and honest about what is unproven.

### IV. Data Provenance & Cross-Source Verification

- YouTube replay/POV VODs are the primary data source. Every extracted record MUST carry its
  provenance: video ID/URL, timestamp(s), extraction method/version, and extraction date.
- Raw extracted data MUST be stored immutably; cleaning and corrections happen in separate,
  versioned downstream steps.
- Extracted data MUST be cross-checked against at least one secondary source (e.g., official
  results, the OWCS hero bans/metas spreadsheet) for results, rosters, heroes, and bans
  where available. Disagreements MUST be logged with both values and the resolution; silent
  overwrites are prohibited.
- Records that cannot be verified MUST be flagged with a confidence/verification status, and
  the model MUST be evaluated with and without unverified records.
- Data collection MUST respect platform terms of service and rate limits; only derived data
  (not re-hosted video) is stored in the repo.

**Rationale**: Automated extraction from video is error-prone; untraceable errors in hero or
outcome labels corrupt every downstream rating.

### V. Baselines Before Complexity

- Every new feature or model MUST be compared against established baselines on the same
  chronological test set: (1) always-pick-higher-team-Elo, (2) team-Elo logistic probability,
  and (3) the previous best model.
- A feature or model is adopted only if it improves the primary metric (log loss) without
  materially degrading calibration; otherwise it is documented as a negative result.
- scikit-learn is the default modeling library. Simple, interpretable models (logistic
  regression) come first; more complex estimators MUST justify themselves against them.

**Rationale**: `Math_plan.pdf` already notes player-summed ratings can underperform plain
team Elo; only measured comparison tells us what helps.

### VI. Reproducibility

- Every reported result MUST be reproducible from raw data with a single documented command,
  with fixed random seeds and pinned dependency versions.
- Rating parameters, feature sets, and model configs MUST live in version-controlled config
  files, not hard-coded constants scattered through notebooks.
- Notebooks MAY be used for exploration, but pipeline logic MUST live in importable, tested
  Python modules.

**Rationale**: Results that cannot be regenerated cannot be trusted, compared, or extended.

## Data & Technology Constraints

- **Language**: Python 3.11+.
- **Core libraries**: pandas for tabular data, scikit-learn for modeling and evaluation;
  additional libraries (video download/frame extraction/OCR, Glicko implementations) MUST be
  justified in the relevant plan.
- **Data layout**: `data/raw/` (immutable extractions), `data/interim/` (cleaned/reconciled),
  `data/processed/` (feature tables); each dataset documents its schema.
- **Canonical entities**: Team, Player, Hero, Map, Series, Patch, Ban; IDs MUST be stable and
  name aliases (player renames, team rebrands) resolved through a mapping table.
- **Evaluation metrics**: log loss (primary), Brier score, accuracy, and a calibration
  curve/reliability table on every reported model.

## Development Workflow & Quality Gates

- Work proceeds through Spec Kit: specify → plan → tasks → implement, one feature at a time,
  in this priority order unless amended: (1) strength metrics, (2) data collection &
  verification, (3) sklearn model training & evaluation.
- Before merge, a change MUST pass: unit tests for rating math, leakage tests (Principle II),
  schema/provenance validation on any new data (Principle IV), and a baseline comparison
  report for any modeling change (Principle V).
- Every plan MUST include a Constitution Check confirming compliance with each principle or
  justifying any exception in a Complexity/Deviation note.

## Governance

- This constitution supersedes other project practices. Conflicts are resolved in its favor
  until it is amended.
- Amendments require: a written description of the change and rationale, a version bump, an
  updated Sync Impact Report, and review of dependent specs/plans for consistency.
- Versioning follows semantic versioning: MAJOR for removing or redefining a principle, MINOR
  for adding a principle/section or materially expanding guidance, PATCH for clarifications.
- Compliance is reviewed at each `/speckit-plan` (Constitution Check) and before reporting any
  model result.

**Version**: 1.0.0 | **Ratified**: 2026-11-15 | **Last Amended**: 2026-11-15
