# Research: Strength Metrics (Python implementation)

**Feature**: `001-strength-metrics` | **Date**: 2026-11-15 | **Plan**: [plan.md](./plan.md)

## In short: every decision on one page

| # | Question | Decision |
|---|---|---|
| R1 | What shape is the code? | An importable package plus a thin command-line tool |
| R2 | How are maps processed? | One pass in time order: snapshot ratings → score the map → update ratings |
| R3 | Can the rating system be swapped later? | Yes: every metric goes through one shared rating interface (Elo for now) |
| R4 | Which Elo formulas? | Standard logistic Elo for win chances; player updates follow Marveldoss (2018) |
| R5 | How is a hero's rating kept up to date? | Running time-weighted sums, updated as each player-on-hero rating changes |
| R6 | Composition vs. hero-weighted strength? | Two separate metrics: lineup strength right now (per segment) vs. time-weighted over the map |
| R7 | How is ban impact measured? | Each opposing player's strength with and without the banned hero, from their past play |
| R8 | How is the score differential built and turned into `S`? | Kills plus objective points per mode; defenders score from attackers' unused time; a logistic curve maps it to 0–1 |
| R9 | What does the input look like? | A folder of CSV files (maps, segments, heroes per segment, bans, attacks, aliases) |
| R10 | Same input, same output? | Yes: fixed column order and number formats, no timestamps |
| R11 | What if two maps can't be put in order? | Stop with an error, unless the order can't change any rating |
| R12 | How are settings tuned and results judged? | Time-based train/validation/test split; staged grid search on validation only |
| R13 | How is "no peeking at the future" proven? | Change later maps and confirm earlier snapshots don't move |
| R14 | Is it fast enough? | ~40,000 updates per season: well under a second per run |
| R16 | When is each feature known? | Every output column is labeled pre-map, map-start, segment or post-map; only the first two may be used to predict |
| R17 | How closely does it follow Marveldoss? | Same expected +/-, bounded update and point conservation; time measured against each map's length |
| R15 | Which libraries? | pandas, numpy, scikit-learn, PyYAML; pytest and hypothesis for tests |

## How to read each entry

Each section records one decision that was open in Technical Context, with rationale and the
alternatives considered. No `NEEDS CLARIFICATION` items remain.

---

## R1. Overall shape: importable package + thin CLI

- **Decision**: An importable package `owstudy` under `src/` (src layout), with the strength
  engine in `owstudy.strength`. A command-line entry point `owstudy-strength` (also runnable as
  `python -m owstudy.strength`) wraps it with four subcommands: `validate`, `run`, `tune`,
  `report`, plus `check-leakage`.
- **Rationale**: Constitution VI requires pipeline logic in importable, tested modules and one
  documented command per result. A CLI gives the single command; the package lets notebooks and
  the later sklearn feature import the same code.
- **Alternatives**: A single `strength.py` script (untestable in pieces, violates VI); notebook
  pipeline (prohibited by VI for pipeline logic).

## R2. Processing model: one chronological pass, snapshot → score → update

- **Decision**: A single loop over maps in chronological order. For each map the engine:
  1. **Snapshot** — reads current state (read-only) and writes every pre-map rating, strength,
     expected probability, composition strength, and ban impact for that map.
  2. **Score** — computes the map score differential `D_AB` and both outcome values
     (`S_wl` from win/loss/draw, `S_diff` from the differential mapping).
  3. **Update** — applies Elo updates to team, player, player-on-hero state (both variants), then
     refreshes the hero aggregates.

  The snapshot step receives a frozen view of state, and the update step is the only code that
  mutates it. All metrics run in the same pass, so player, hero, and ban metrics are always
  consistent with each other.
- **Rationale**: Makes FR-002 / Constitution II structural rather than a convention: nothing in
  step 1 can see the current map's result because step 2 hasn't run yet.
- **Alternatives**: Separate passes per metric (repeats ordering logic in several places, easy
  to desynchronize); vectorized pandas computation (Elo is inherently sequential; vectorizing
  invites leakage via `shift` mistakes).

## R3. Rating-system interface (Constitution III, FR-011)

- **Decision**: A `RatingSystem` protocol with two methods:
  `expected(r_a, r_b) -> float` and `delta(s, mu, weight=1.0) -> float`. `EloRating(k, scale=400,
  f=identity)` is the only implementation in this feature. All metric modules call the protocol,
  never the Elo formula directly.
- **Rationale**: Keeps the update rule separate from metric bookkeeping so Glicko can be added
  later without changing input/output formats.
- **Alternatives**: Hard-coding Elo in each metric (blocks later Glicko comparison).

## R4. Elo details (aligned with Marveldoss 2018, see R17)

- **Decision**:
  - Win probability (all levels): `Pr(j > k) = 1 / (1 + 10^((r_k − r_j)/400))` (thesis eq.
    1.2/2.29), where `r` is team Elo, `m_j`, or another team-strength value.
  - **Team Elo**: `R_new = R_old + K_team·(S − μ)` (eq. 1.1). Full map, so `t̂ = 1`.
  - **Player rating, `diff` variant (the Marveldoss +/- update)**, for player `i` on team `j`
    against team `k`:
    1. Team strength `m_j = Σ_n t_jn p_jn / Σ_n t_jn` (eq. 2.3), and team strength without
       the player, `m̂_ji = Σ_{n≠i} t_jn p_jn / Σ_{n≠i} t_jn` (eq. 2.4).
    2. Expected +/-: `μ_ji = t_ji·(p_ji + 4·m̂_ji − 5·m_k) / α` (eq. 2.6–2.8). Overwatch is 5v5,
       so the thesis's "5" and "4" carry over unchanged. `t` is in minutes.
    3. Actual +/-: `S_ji` = the team's **normalized** score differential `D̃` while the player
       was in play (R17 N3). This is the whole map for players, since they play the full map.
    4. `b_ji = F(S_ji − μ_ji)`, where `F(x) = 1/(1+e^{−x/β}) − 0.5`, which bounds it to
       (−0.5, 0.5) (§2.2.4).
    5. Point conservation (§2.2.5): `d = Σ_{all 10} t̂·b`, and
       `b̂ = 2b − d / Σ_{own team} t̂` (eq. 2.27).
    6. `p̂_ji = p_ji + K·b̂_ji` with the time-based K-factor `K = γ·t̂_ji` (eq. 2.10, 2.28).
  - **Player rating, `wl` variant**: the `Math_plan.pdf` form `p̂ = p + K·(S − μ)` with
    `S ∈ {0, ½, 1}`, `μ = Pr` from `m_j` vs `m_k`, and the same `K = γ_wl·t̂`. This is a
    comparison variant only (FR-009).
  - **Player-on-hero, per segment** (R16): the same six steps with the segment as the
    "time on court". For segment `g` of `d_g` minutes, in which player `i` is on hero `k`:
    `μ_g,i = d_g·(h_i,g + 4·ĥ_−i,g − 5·h̄_k,g)/α`, where `h_i,g` is the pre-map rating of the
    player's current hero, `ĥ_−i,g` the mean of the teammates' current-hero ratings, and
    `h̄_k,g` the opponents' mean. `S_g = D̃_g`. Then `b = F(S_g − μ_g)`, conservation across the
    10 entries in play, and `Δh_jik += γ_ph·t̂_g·b̂` with `t̂_g = d_g / T_map` (R17 N1). The
    `wl` variant uses `S = S_wl` with `μ_g = Pr(h̄_j,g vs h̄_k,g)`. All `Δh` for a map come from
    pre-map ratings and are applied after the map.
  - Hyperparameters `α` (rating ↔ differential scale), `β` (spread of `F`), and `γ` (K
    scale, one per entity type) are grid-tuned on the validation period by log loss. That's
    how the thesis tuned them (Tables 4.2–4.4), except the thesis used log loss on real data and
    MSE on synthetic data.
  - Starting rating 1500 for every entity type (spec). The thesis uses 1000, but the starting
    level cancels in `μ` (`1500 + 4·1500 − 5·1500 = 0`), so only `α` matters.
- **Rationale**: This follows the thesis that `Math_plan.pdf` cites: the actual score is the
  +/- differential, the expected score is built from per-minute strengths, `F` normalizes the
  error, the K-factor scales with time played, and ratings are conserved.
- **Consequence worth stating**: in Overwatch every player plays the full map, so
  `p_ji + 4·m̂_ji = 5·m_j` and `μ_ji = 5·t·(m_j − m_k)/α` is the **same for all five
  teammates**, and so is `S`. At the player level the +/- update gives identical updates to
  everyone on a team, which is the Chiyo/Fielder problem `Math_plan.pdf` raises. Player ratings
  still separate through roster changes. Hero segments separate them much more, because each
  player-on-hero entry only collects the segments it was played in.
- **Alternatives**: Plain logistic Elo per player with a 0–1 `S` (the earlier draft). It
  doesn't follow the thesis: no expected +/-, no time-based K, no conservation.

## R5. Hero Elo `H_k`, incremental

- **Decision**: For each hero keep running sums `W_k = Σ t_jnk` (career time across all
  player-on-hero entries) and `Q_k = Σ t_jnk·h_jnk`. `H_k = Q_k / W_k`. When an update changes
  `h` by `Δh` for an entry with prior career time `t_old` and adds `t_map`, apply
  `Q_k += t_old·Δh + t_map·h_new` and `W_k += t_map`. Heroes with `W_k = 0` use the default and
  are flagged `no_history`. Per-patch views come from the snapshot table, not from a separate
  state.
- **Rationale**: O(1) per update and exact (matches a full recompute; a test asserts this).
- **Alternatives**: Recomputing `H_k` from scratch per map (correct but O(entries) per map;
  fine at 1,000 maps but needless).

## R6. Composition strength vs. hero-weighted team strength

- **Decision**: Two separate metrics (spec US4):
  - **Composition strength** (per team, per segment): `comp_j,g = Σ_{i on j} H_{k(i,g)}`, the
    sum of the pre-map hero Elo of the five heroes in play during segment `g`. No time weighting,
    so a 10-second segment and a 5-minute segment with the same heroes have the same value.
    `comp_mean = comp/5` feeds `expected()` for `p_comp`. At map level, the reported feature is
    the **starting** composition (segment 1). Per-segment values go in `segment_features.csv`.
  - **Hero-weighted team strength** (per team, per map): `ts_hero_j = Σ_i Σ_k (t_jik/T_ji)·H_k`
    (sum over 5 players; `/5` for the probability). It accounts for hero swaps across the
    whole map. The same weighting applied to `h_jik` gives `ts_player_hero_j`, i.e., the team
    mean of `p_ji`.
- **Rationale**: Matches the user's definitions. Composition describes what's on the field,
  and team strength describes the map as played. Keeping them apart lets the report test
  whether swap-aware strength adds anything over the composition snapshot.
- **Alternatives**: A time-weighted "composition" (that was the earlier draft, and it is now
  `ts_hero`).

## R7. Ban impact

- **Decision**: For banning team B and each opposing player `i` on team A, using pre-map state
  and career time `t_jik`:
  `p_with = Σ_k t·h / Σ_k t`, `p_without = Σ_{k≠x} t·h / Σ_{k≠x} t`,
  `loss_i = p_with − p_without`. If the player has no time on `x`, `loss_i = 0`. If all career
  time is on `x`, `loss_i` is `undefined` (null + flag). Team loss = mean of defined player
  losses, with a count of undefined players. Computed for both variants.
- **Rationale**: Direct reading of FR-008 and US5 scenarios. Career time (not this map's time)
  is used because the ban removes a hero from the pool the player normally draws on, and this
  map's hero times are themselves a consequence of the ban.
- **Alternatives**: Using this map's hero times (leaks this map's picks, which are a consequence
  of the ban).

## R8. Score differential and mapping to `S`

- **Decision**:
  - Objective progress is supplied already normalized to 0–1 per mode by the input contract.
  - Defender points (asymmetric): `def = 1 − time_remaining / attack_clock`, clipped to [0, 1]
    (linear default; `def_curve: linear | power(γ)` in config). Banked/overtime time is part of
    `attack_clock` and `time_remaining` (spec edge case).
  - Symmetric: `D_AB = a·(K_A − K_B) + X_n·(Obj_A − Obj_B)`.
  - Asymmetric: `D_AB = a·(K_A − K_B) + [X_n·att_A + C_n·def_A] − [X_n·att_B + C_n·def_B]`.
  - `D_BA = −D_AB` by construction (computed once, negated); a property test asserts it.
  - Mapping **for team Elo's `diff` variant only** (team Elo needs `S` in 0–1):
    `S_A = 1 / (1 + exp(−D̃_AB / s))`; then if A won, `S_A = max(S_A, 0.5)`; if A lost,
    `S_A = min(S_A, 0.5)`; draw: unclamped. `S_B = 1 − S_A`. Clamped maps are counted in the
    report ("differential disagrees with result"). Player and player-on-hero `diff` updates use
    the normalized differential `D̃` directly as the actual +/- (R4), as the thesis does.
  - Unknown mode with no constant → hard error. Clash → excluded and flagged.
  - **Per segment**: the same formula on the segment's kills and objective points. Symmetric:
    objective progress gained during the segment. Asymmetric attackers: progress gained.
    Asymmetric defenders: `curve(e_end/clock) − curve(e_start/clock)`, where `e` is elapsed attack
    clock, so segment defender points sum exactly to the attack's total for any curve. Because
    the formula is linear, `Σ_g D_g = D_AB` (validated, and property-tested).
  - **Segment outcome**: win/loss variant `S_g = S_wl` (the map result, since a segment has no
    result of its own). Differential variant: the segment's normalized differential `D̃_g` is
    the actual +/- (R4). It is **not clamped**, because a map winner can lose a segment. Short
    segments have a small expected +/- (`μ` scales with `d_g`) and a small K (`t̂_g = d_g/T_map`),
    so their effect is bounded.
- **Rationale**: Exactly the spec's assumptions; `s` is one more tunable with an interpretable
  meaning (differential that gives S≈0.73).

## R9. Input format

- **Decision**: A directory of long-format CSV files (UTF-8, header row): `maps.csv`,
  `segments.csv` (one row per map × segment: times, attack clock position, per-team kills and
  objective progress during it), `segment_heroes.csv` (one row per map × segment × player: hero),
  `bans.csv`, `attacks.csv` (asymmetric modes only). Plus `entities/aliases.csv` for stable IDs.
  Per-hero seconds `t_jik` are *derived* from segments rather than input separately, so they
  can't disagree. Full schema in [contracts/input-schema.md](./contracts/input-schema.md).
- **Rationale**: Long CSVs are what the data-collection feature can emit naturally, diff well in
  git, and load directly into pandas. Nested JSON would be harder to validate and edit by hand
  for reference examples.
- **Alternatives**: JSON Lines with nested lineups (fine, but harder to hand-build fixtures);
  Parquet (needs pyarrow, not human-editable).

## R10. Output format and byte-for-byte determinism (FR-014, SC-005)

- **Decision**: Output is a run directory with CSV tables written with a fixed column order,
  rows sorted by `(map_seq, team_side, entity_id)`, floats formatted `%.10f`, `\n` line endings,
  UTF-8 without BOM. A copy of the resolved config and a `manifest.json` (input file SHA-256,
  config SHA-256, package version, row counts) — **no timestamps or absolute paths** in any
  output file. Iteration over dicts always goes through `sorted()`; no `set` iteration order
  reaches output.
- **Rationale**: Determinism is easiest to guarantee when the writer controls formatting; the
  test is literally `filecmp` on two runs.
- **Alternatives**: Parquet (metadata can embed writer version/time).

## R11. Ordering and tie handling

- **Decision**: Sort key `(date, series_start, series_id, map_number)`. `series_start` (ISO time)
  is optional. If two series on the same date lack `series_start` **and share any team or
  player**, the run stops with an ordering-conflict error listing them. If they share no
  entities, their relative order cannot change any rating, so `series_id` order is used.
- **Rationale**: Implements the spec edge case ("stop rather than guess") without stopping on
  harmless ties, which would be common on tournament days with many matches.

## R12. Chronological splits, tuning, and evaluation (FR-012, FR-017, Constitution II/V)

- **Decision**: Split boundaries are dates in config (`train_end`, `validation_end`); test is
  everything after. Ratings are always computed over the full history in one pass (that's
  legitimate: each snapshot only uses earlier maps). `tune` runs a staged grid search, one stage
  per metric family (team `K`; team-Elo mapping `s`; player `γ`, `α`, `β`; player-on-hero `γ`),
  each stage starting from the best values of earlier stages and scoring its target column's
  **validation-period** log loss only; it writes the best config and a sensitivity table (log
  loss vs. each parameter, others at the stage's best). Staging works because the families are
  mostly separable (`K_team` only moves team Elo, `γ_ph` only moves player-on-hero ratings) and
  keeps the search near 100 configs instead of a full cartesian product. The scoring constants
  `a`, `X_n`, `C_n` and the defender curve are fixed placeholders in this feature; they are tuned
  for accuracy once real data exists (FR-017), so σ_n never goes stale during `tune`. `report` scores the test
  period once with the chosen config. Metrics via `sklearn.metrics.log_loss`,
  `brier_score_loss`, `accuracy_score`, and `sklearn.calibration.calibration_curve`. Baselines:
  higher-team-Elo pick, team-Elo probability, coin flip (0.5), and the previous best metric so
  far (lowest validation log loss among `p_*` columns from earlier stories; team-Elo
  probability until a later metric beats it).
- **Rationale**: Grid search is transparent and cheap (a full run is well under a second per
  config at 1,000 maps); random search/optuna add a dependency with no need.
- **Alternatives**: Optuna (extra dependency, nondeterminism concerns).

## R13. Leakage test (SC-002, Constitution II)

- **Decision**: `check-leakage` (and a pytest test) does a **perturbation test**: for a sample
  of maps `m`, flip the result and scramble the kills/objective of `m` and every later map, rerun,
  and assert every snapshot for maps `< m`, and every `pre_map`/`map_start` column for map `m`,
  is unchanged. Plus a **truncation test**: running on maps `[0, m]` gives the same snapshot for
  `m` as the full run. A third check asserts the timing class of every `map_features.csv` column
  is declared (R16). `post_map` columns are exempt from the first test by definition.
- **Rationale**: Detects leakage regardless of where in the code it happens.

## R14. Performance (SC-006)

- **Decision**: Pure-Python loop over dicts of floats; pandas only for load/validate and
  writing. Estimated cost: ~1,000 maps × ~10 players × ~2 heroes × 2 variants ≈ 40k updates —
  well under 1 s per run. staged `tune` (93 configs with the default stages, capped by
  `tune.max_configs`) fits in the 5-minute budget;
  `tune` can use `concurrent.futures.ProcessPoolExecutor` (results sorted before writing, so
  determinism holds).

## R16. Segments and feature timing (FR-006, FR-019, Constitution II)

- **Decision**: A segment is a maximal interval with no hero change by any of the 10 players.
  It also ends at every attack switch (asymmetric) and round boundary. Every output feature
  column carries a timing class, listed in `feature_timing.csv` in the run directory:
  - `pre_map`: rating snapshots, team Elo, `m_j`, career-weighted player-on-hero team
    strength `ts_player_hero_career` (weights = career `t_jik`, like ban impact).
  - `map_start`: ban impact, starting composition strength.
  - `segment`: per-segment composition strength and `h̄_j,g` (known when the segment starts).
  - `post_map`: `ts_hero`, `ts_player_hero` (weighted by *this map's* hero times).
- **Rationale**: Hero swap timing is itself correlated with the outcome, because losing teams
  swap more. A metric weighted by this map's hero times is a valid *measurement* of the map,
  but it would leak if fed to a pre-map predictor. Labelling each column keeps both uses: the
  report evaluates `post_map` metrics in a separate, clearly marked section, and the modeling
  feature selects only `pre_map`/`map_start` columns for pre-map prediction.
- **Alternatives**: Dropping `post_map` metrics (loses the swap-aware measurement the user
  wants); unlabeled columns (invites leakage downstream).

## R17. Alignment with Marveldoss (2018) and data normalization

Source: R. E. D. Marveldoss, *An Elo-Based Approach to Model Team Players and Predict the
Outcome of Games*, M.S. thesis, Texas A&M, 2018 (the paper `Math_plan.pdf` cites). Equation
numbers below refer to the thesis.

### Principle-by-principle alignment

| Thesis principle | Where it is in our design | Status |
|------------------|---------------------------|--------|
| Elo update `R + K(S − μ)`, logistic with 400 spread (1.1, 1.2) | Team Elo, win probabilities at every level (R4) | Aligned |
| K-factor: "how much weight a recent game gets vs. prior information"; too high oscillates, too low adapts slowly (§1.3.1) | K is tuned per entity type on validation; the sensitivity table reports the oscillation/slowness trade-off (R12) | Aligned |
| **Time-based K-factor** `K = γ·t̂`, `t̂ = t/48` (2.10–2.11) | `K = γ·t̂` with `t̂ = t / T_map` for players and `t̂_g = d_g / T_map` for hero segments (N1) | **Added** (was missing) |
| Player strength = contribution per minute, scaled by a normalizing constant to a 1000 baseline (2.2) | Ratings are differential-per-minute scaled by `α`; baseline 1500 (N2) | **Added** |
| Time-weighted team strength `m_j` (2.3) | `m_j`, and the same weighting for `p_ji`, `H_k`, `ts_hero` | Aligned |
| Team strength without player `i`, `m̂_ji` (2.4) | Used in the expected +/- (R4). The same "remove one term" sum, applied to heroes, is ban impact (R7). `Math_plan.pdf` explicitly cites (2.4) for this | Aligned |
| Expected +/- `t(p + 4m̂ − 5m_k)/α` (2.6–2.8) | Player and player-on-hero `diff` updates (R4) | **Added** (was a logistic 0–1 `μ`) |
| Actual score = raw +/- while on court | `D̃` while in play: map for players, segment for heroes | **Changed** (was a 0–1 mapping) |
| `F` normalizes `S − μ` to (−0.5, 0.5) with a modified logistic (§2.2.4) | `F(x) = 1/(1+e^{−x/β}) − 0.5` (N4) | **Added** (`f` was identity) |
| Point conservation, two-step offset correction (2.12–2.27) | Applied per map (players) and per segment (hero entries) (N5) | **Added** |
| Initialize everyone at the same rating; carry ratings through the test period (§3, §4.2.2) | 1500 default; ratings keep updating through validation/test; snapshots stay pre-map | Aligned |
| Chronological train / cross-validation / test, hyperparameters on cross-validation (§4.2) | Date-based splits; `tune` uses validation only (R12) | Aligned |
| Log loss ("predictive discrepancy", 4.1) and accuracy as metrics | Log loss primary, plus Brier, accuracy, calibration | Aligned |
| Standard Elo beat the player model; prefer the simpler model unless the data justify more (§5) | Constitution V: team Elo is the baseline every metric must beat, and negative results are reported | Aligned |
| Removing a player's contribution to measure their impact (§4.3, Curry) | Ban impact; per-player "without" strength is reportable | Aligned |
| Home advantage (+100) (§1.4) | Not applicable: pro Overwatch is mostly online or at neutral LAN venues | Excluded (documented) |

### Normalization

- **N1 — Time.** The thesis divides minutes by 48 (a full regulation game) so `t̂ = 1` means a
  whole game. Overwatch map length varies by mode and by match, so we use the map's own
  duration: `t̂_ji = t_ji / T_map` (= 1 for every player, because players play the full map) and
  `t̂_g = d_g / T_map` for a segment. Overtime and banked time are inside `T_map`. That differs
  from the thesis, which assumed no overtime. The result is that every map carries equal total
  weight, and a hero's share of the update equals its share of the map.
- **N2 — Rating scale.** A rating is `α ×` (normalized differential contributed per minute),
  anchored at 1500. `α` converts rating differences into expected differential (R4 step 2), and
  is tuned.
- **N3 — Score differential across modes.** Raw `D` (kills plus mode-weighted objective
  points) isn't comparable across modes, because Control and Escort have very different kill
  rates and lengths. For each mode `n`: `D̃ = D / σ_n`, where `σ_n` is the standard deviation of
  `D_map / T_map` (differential per minute) over **training-period maps of that mode only**.
  `σ_n` is computed once by `owstudy-strength fit-normalization` and written into the config
  as fixed constants, like any other tuned parameter. It is never refit on validation or test
  data (Constitution II). Segments use the same `σ_n`, so `Σ_g D̃_g = D̃_map` still holds.
  A mode with fewer than `min_maps_for_sigma` (default 30) training maps uses the pooled `σ`
  across all modes, and this is flagged in the report.
- **N4 — Outcome error.** `F` bounds every update's error term to (−0.5, 0.5), so one blowout
  can't move a rating by more than `γ·t̂/2`, or `γ·t̂` after the conservation step's factor of 2.
- **N5 — Conservation.** After `b̂`, `Σ t̂·b̂ = 0` across the 10 entries in play, so the total of
  all player (and all player-on-hero) ratings changes only when new entities appear. Because
  `F` is odd and both teams have equal time (5 players × full map), `d = 0` in the normal case,
  so the step is an identity. It is still applied, and its invariant tested, because it matters
  whenever times are unequal.
- **N6 — Inputs.** Objective progress is normalized to 0–1 per mode at input, and defender
  points to 0–1 per attack (R8). Kills are raw counts, weighted by `a`, before `σ_n`.

## R15. Dependencies

- **Decision**: Python 3.11+, pandas, numpy, scikit-learn, PyYAML; dev: pytest, hypothesis
  (property tests for `D_AB = −D_BA`, `H_k` incremental = recompute). Pinned in
  `pyproject.toml` + a lock file (`uv.lock`).
- **Rationale**: Constitution's default stack; PyYAML and hypothesis are the only additions, both
  justified above.
