# Data Model: Strength Metrics

**Feature**: `001-strength-metrics` | **Date**: 2026-11-15 | **Plan**: [plan.md](./plan.md)

Three layers: **input records** (what the script reads), **engine state** (in memory during the
chronological pass), and **output records** (what the script writes). File-level schemas are in
[contracts/](./contracts/); this document covers entities, relationships, and rules.

Notation follows `Math_plan.pdf`: team `j`, player `i`, hero `k`, banned hero `x`, time `t`.

---

## 1. Input records

### MapRecord (`maps.csv`, one row per map)

| Field | Type | Rules |
|-------|------|-------|
| `map_id` | str | Unique. |
| `series_id`, `map_number` | str, int ≥ 1 | `(series_id, map_number)` unique. |
| `date` | date | Required. |
| `series_start` | datetime? | Optional; needed only to break same-date ties (research R11). |
| `patch_id` | str | Required (Constitution III). |
| `map_name`, `mode_id` | str | `mode_id` must exist in config `modes`, or be `clash` (excluded + flagged). |
| `team_a_id`, `team_b_id` | str | Stable team IDs, distinct. |
| `winner` | `a` \| `b` \| `draw` | |
| `kills_a`, `kills_b` | int ≥ 0? | Missing → differential variant skips map (flag `missing_score`). |
| `obj_a`, `obj_b` | float in [0,1]? | Symmetric modes only; normalized objective progress. |
| `verification` | `verified` \| `unverified` | Filtered by config `include_unverified`. |
| `source_ref` | str | Provenance pointer (Constitution IV); carried through, not used in math. |

### Segment (`segments.csv`, one row per map × segment)

A time interval in which no player changes hero (and which doesn't cross an attack switch or
round boundary).

| Field | Type | Rules |
|-------|------|-------|
| `map_id`, `segment_no` | str, int ≥ 1 | Contiguous `1..G` per map. |
| `start_s`, `end_s` | float | Map game time; `end_s > start_s`; segments tile the map without gaps or overlaps. |
| `attack_order` | int? | Asymmetric only: which attack the segment belongs to. |
| `clock_elapsed_start_s`, `clock_elapsed_end_s` | float? | Asymmetric only: position on that attack's clock (for defender points). |
| `kills_a`, `kills_b` | int ≥ 0? | Kills during the segment. Missing → `no_segment_score`. |
| `obj_a`, `obj_b` | float ≥ 0? | Objective progress gained during the segment (normalized, so they sum to the map total). |

### SegmentHero (`segment_heroes.csv`, one row per map × segment × player)

`map_id`, `segment_no`, `team_id`, `player_id`, `hero_id`. Exactly 5 players per team per
segment, and the same 5 players in every segment of a map (players play the full map), otherwise
flag `bad_roster` (team Elo still updates; player-based metrics skip that team on that map).
Consecutive segments must differ in at least one hero unless the boundary is an attack/round
switch.

**Derived**: `t_jik = Σ_{g: i on k} (end_s − start_s)`, `T_ji = Σ_k t_jik`. Missing segment
heroes for a player → flag `missing_hero_time`.

### Ban (`bans.csv`)

`map_id`, `banning_team_id`, `hero_id`. At most one per team per map (spec assumption).

### Attack (`attacks.csv`, asymmetric modes only, one row per attack)

`map_id`, `attack_order` (1, 2, … for extra rounds), `attacking_team_id`, `obj_progress` [0,1],
`attack_clock_s` (> 0, includes banked time), `time_remaining_s` (0 ≤ x ≤ clock).

### Alias (`entities/aliases.csv`)

`entity_type` (`team|player|hero`), `alias`, `stable_id`, `valid_from`, `valid_to`. Input IDs are
resolved through this table on load; ratings key only on `stable_id`.

---

## 2. Configuration

### RunConfig (YAML, schema in [contracts/config-schema.md](./contracts/config-schema.md))

- `initial_rating` per entity type (default 1500), `elo_scale` (400).
- `k`: `team` (plain K), and `gamma` per `player` / `player_hero` and variant (K = γ·t̂).
- `marveldoss`: `alpha` (rating ↔ differential scale), `beta` (spread of `F`),
  `conserve_points: true`.
- `normalization`: `sigma` per mode (fitted on the training period by `fit-normalization`),
  `min_maps_for_sigma`.
- `score`: `a` (kill weight), `s` (team-Elo logistic scale), `def_curve` (`linear` or `power`).
- `modes`: per `mode_id`: `symmetric: bool`, `X`, and `C` (asymmetric only; symmetric → `C := X`).
- `splits`: `train_end`, `validation_end` (dates).
- `include_unverified: bool`.
- `tune`: `max_configs` and ordered `stages`, each with a `name`, a `target` (`column`,
  `variant`) and a `grid` of rating parameters (used only by `tune`; scoring constants are not
  tunable in this feature, FR-017).

**Rule**: Every value used by the math comes from RunConfig; the resolved RunConfig is written
into each run directory (FR-010).

---

## 3. Engine state (in memory)

All maps are keyed with a dense `map_seq` (0..N−1) after sorting.

| State | Key | Value | Updated by |
|-------|-----|-------|-----------|
| `TeamRating` | `(variant, team_id)` | `R` | team Elo update |
| `PlayerRating` | `(variant, player_id)` | `p`, `maps_played` | player update |
| `PlayerHeroRating` | `(variant, player_id, hero_id)` | `h`, `career_seconds`, `maps` | player-on-hero update |
| `HeroAggregate` | `(variant, hero_id)` | `W = Σ t`, `Q = Σ t·h` → `H = Q/W` | after player-on-hero update (research R5) |
| `PlayerTeamHistory` | `player_id` | list of `(team_id, first_map_seq)` | on each appearance |

`variant ∈ {wl, diff}`. Team Elo is computed in both variants (FR-009 "MAY"); `wl` team Elo is
the baseline.

**Lifecycle of an entity rating**: *absent* → (first appearance) *initialized at default,
recorded as `is_default=true` in that map's snapshot* → *updated after each map played*. There
is no reset across patches or seasons.

**Mutation rule**: only `engine.update(map)` mutates state; `engine.snapshot(map)` receives a
read-only view. This is the structural guarantee for FR-002.

---

## 4. Derived per-map values

### MapScore (one per map)

- `points_a`, `points_b`: objective totals (`X·att + C·def` for asymmetric; `X·obj` for symmetric).
- `D_ab` (and implied `D_ba = −D_ab`).
- `S_wl_a ∈ {0, 0.5, 1}`, `S_diff_a ∈ [0,1]`, `clamped: bool` (differential disagreed with winner).
- `score_status`: `ok | missing_score | excluded`.

### SegmentScore (one per map × segment)

- `duration_s`, `t_hat_g = d_g / T_map`, `points_a`, `points_b`, `D_g`, `D_norm_g = D_g / σ_n`
  (the actual +/- for the segment, unclamped), `S_g_wl_a`.
- Invariants: `Σ_g D_g = D_AB` and `Σ_g t̂_g = 1` (tolerance 1e-9).

### Formulas (single source of truth for tests)

| Quantity | Formula |
|----------|---------|
| Expectation | `μ_AB = 1 / (1 + 10^((R_B − R_A)/400))` |
| Team update | `R ← R + K_team (S − μ)` |
| Player team strength | `m_j = Σ_n t_jn p_jn / Σ_n t_jn` |
| Normalized time | `t̂ = t / T_map` (player: 1; segment: `d_g / T_map`) |
| Normalized differential | `D̃ = D / σ_n`, `σ_n` = training-period std of `D_map / T_map` for mode `n` (minutes) |
| Team strength without `i` | `m̂_ji = Σ_{n≠i} t_jn p_jn / Σ_{n≠i} t_jn` (thesis eq. 2.4) |
| Expected +/- (`diff`) | `μ_ji = t_ji (p_ji + 4 m̂_ji − 5 m_k) / α` (thesis eq. 2.8, `t` in minutes) |
| Normalizing function | `F(x) = 1/(1 + e^{−x/β}) − 0.5`, range (−0.5, 0.5) |
| Conservation | `b = F(S − μ)`; `d = Σ_{10} t̂ b`; `b̂ = 2b − d / Σ_{own team} t̂` (thesis eq. 2.27) |
| Player update (`diff`) | `p ← p + γ_player · t̂ · b̂` with `S = D̃_map` (thesis eq. 2.10, 2.28) |
| Player update (`wl`) | `p ← p + γ_player,wl · t̂ · (S_wl − Pr(m_j > m_k))` |
| Hero-weighted player strength | `p_ji = Σ_k t_jik h_jik / Σ_k t_jik` (this map's times) |
| Segment strength (player-on-hero) | `h̄_j,g = (1/5) Σ_{i on j} h_{j,i,k(i,g)}` (pre-map `h` of heroes in play during `g`) |
| Player-on-hero update (`diff`) | `h_jik ← h_jik + Σ_{g: i on k} γ_ph · t̂_g · b̂_g,i` with `μ_g,i = d_g (h_i,g + 4 ĥ_−i,g − 5 h̄_k,g)/α`, `S_g = D̃_g`, conservation over the 10 entries in `g`. All from pre-map `h`, applied after the map |
| Player-on-hero update (`wl`) | same sum with `b = S_wl − Pr(h̄_j,g > h̄_k,g)` |
| Hero Elo | `H_k = Σ t_jnk h_jnk / Σ t_jnk` over all player-on-hero entries (career time) |
| Composition strength | `comp_j,g = Σ_{i on j} H_{k(i,g)}` (heroes in play during `g`, no time weighting); `comp_mean = comp/5` |
| Hero-weighted team strength | `ts_hero_j = Σ_i Σ_k (t_jik / T_ji) H_k` (this map's times, `post_map`) |
| Player-on-hero team strength | `ts_player_hero_j = (1/5) Σ_i p_ji` (this map's times, `post_map`); `ts_player_hero_career_j` same with career times (`pre_map`) |
| Ban impact | `loss_i = p_with − p_without`, `p_without` sums over `k ≠ x` with career time |
| Differential | map and segment: see research R8 |

---

## 5. Output records

### RatingSnapshot (`snapshots_team.csv`, `snapshots_player.csv`, `snapshots_player_hero.csv`, `snapshots_hero.csv`)

The pre-map value of a rating attached to a map — what downstream models consume.
Common fields: `map_seq`, `map_id`, `date`, `patch_id`, `variant`, `entity ids`, `rating_pre`,
`is_default`, and where relevant `rating_post` (for audit; never a feature).

### MapFeatures (`map_features.csv`, one row per map × variant)

Wide table, the main deliverable for the modeling feature. Each column has a timing class
(research R16), listed in `feature_timing.csv`:

- `pre_map`: `team_elo_a/b`, `p_team_elo_a`, `m_a/b`, `p_player_a`,
  `ts_player_hero_career_a/b`, `p_ts_player_hero_career_a`.
- `map_start`: `comp_start_a/b`, `p_comp_start_a`, `ban_loss_a/b` (loss suffered by that team
  from the opponent's ban), `ban_undefined_a/b`.
- `post_map`: `ts_hero_a/b`, `p_ts_hero_a`, `ts_player_hero_a/b`, `p_ts_player_hero_a`,
  `n_segments`.
- labels: `label_outcome_a`, `label_S_a`, `label_D_ab`. Plus `split` (`train|validation|test`).

### SegmentFeatures (`segment_features.csv`, one row per map × segment × variant)

The swap-level view: `map_seq`, `map_id`, `segment_no`, `start_s`, `end_s`, `variant`,
`heroes_a`, `heroes_b` (sorted `|`-joined hero IDs), `comp_a/b`, `p_comp_a`, `hbar_a/b`
(`h̄_j,g`), `mu_g_a`, plus labels `label_D_g`, `label_S_g_a`. Composition columns are `segment`
timing; labels are the segment's own result.

### BanImpactRecord (`ban_impact.csv`)

`map_id`, `variant`, `banning_team_id`, `affected_team_id`, `hero_id`, `player_id`,
`p_with`, `p_without`, `loss`, `status (ok|zero_no_history|undefined_only_hero)`.

### ExclusionRecord (`exclusions.csv`, FR-013)

`map_id`, `team_id?`, `player_id?`, `metric_scope` (`all|player|player_hero|hero|diff|ban`),
`reason` (`clash_mode | unverified | bad_roster | missing_hero_time | missing_score |
no_segment_score`).
The report summarizes counts by reason × scope.

### Relationships

```text
MapRecord 1─* Segment 1─10 SegmentHero *─1 Player, *─1 Hero
Segment 1─1 SegmentScore
MapRecord 1─0..2 Ban *─1 Hero
MapRecord 1─0..* Attack
MapRecord 1─1 MapScore
MapRecord 1─* RatingSnapshot (per entity, per variant)
Player 1─* PlayerHeroRating *─1 Hero ─1 HeroAggregate
Team 1─1 TeamRating (per variant)
```
