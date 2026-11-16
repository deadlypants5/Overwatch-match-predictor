# Implementation Plan: Strength Metrics

**Branch**: `001-strength-metrics` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-strength-metrics/spec.md`

## In short

- **What gets built:** a Python package and command-line tool, `owstudy-strength`.
- **How it works:** one pass through the maps in time order. For each map it records every
  rating as it stood *before* the map, then scores the map, then updates the ratings. Only that
  last step changes anything, so a map can never see its own result.
- **Main output:** `map_features.csv`, one row of pre-map features per map, which the later
  model-training feature reads.
- **Other commands:** check the input (`validate`), tune settings on the validation period only
  (`tune`), write a report on the hold-out period (`report`), and test for leakage of future
  data (`check-leakage`).
- **Speed:** a full season (~1,000 maps) in well under 5 minutes on a normal PC.

## Summary

Build a Python package and command-line script, `owstudy-strength`, that reads a chronological
history of professional Overwatch maps and produces pre-map strength values for every team,
player, player-on-hero, hero, composition, and ban, in two variants (win/loss outcome and
score-differential outcome). Maps are split into **segments**, stretches with no hero swap. A
player-on-hero rating is updated only from the segments in which that hero was played, and
composition strength is a per-segment snapshot of the heroes in play. Player and player-on-hero
updates follow Marveldoss (2018), research R4/R17: an expected +/- built from player, teammate,
and opponent ratings; the normalized differential as the actual +/-; a bounded normalizing
function `F`; a time-based K-factor `K = γ·t̂`; and point conservation. Differentials are
normalized per mode by constants fitted on the training period only. It also produces
comparison reports against team Elo and the naive win-rate counterparts.

**How the script works**: it makes one chronological pass. For every map it
(1) **snapshots** the current ratings as that map's features, (2) **scores** the map (win/loss
`S`, and the differential `D_AB` mapped to `S`), then (3) **updates** team, player and
player-on-hero ratings through a shared `RatingSystem` (Elo) interface and refreshes the hero
aggregates. Only step 3 changes state, so no snapshot can see its own map's result. The
outputs are deterministic CSV tables, mainly `map_features.csv`, which the later sklearn feature
consumes. Separate subcommands validate the input, tune constants on the validation period only,
report on the hold-out period, and test for leakage.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: pandas, numpy, scikit-learn (metrics and calibration), PyYAML (config);
dev: pytest, hypothesis (research R15)

**Storage**: Files only: input CSV directory → run directory of CSV + YAML + JSON manifest
(contracts/input-schema.md, contracts/output-schema.md)

**Testing**: pytest: hand-calculated reference fixtures, property tests, leakage tests,
determinism and performance integration tests

**Target Platform**: Personal computer (Windows 11 primary; also Linux/macOS), run from the
command line or imported in notebooks

**Project Type**: Library + CLI (single project, src layout)

**Performance Goals**: Full ~1,000–1,500-map history, all metrics, both variants, in < 5 min
(SC-006); expected < 10 s per run (research R14)

**Constraints**: Strict chronological processing with no leakage (Constitution II);
byte-identical output for the same input and config (SC-005); every parameter comes from config
(FR-010)

**Scale/Scope**: ~1,000+ maps per season, ~20–40 teams, ~300 players, ~45 heroes, 5 modes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|-----------|------------------------|--------|
| I. Map is the unit | Every input row, rating update, snapshot and feature row is keyed by `map_id` / `(series_id, map_number)`; there is no series-level output. | ✅ |
| II. Temporal integrity | Snapshot → score → update loop, with the snapshot reading a frozen view of state (R2); per-segment hero updates all use pre-map ratings and are applied after the map; every feature column has a timing class (`pre_map`/`map_start`/`segment`/`post_map`, R16), and swap-time-weighted metrics are `post_map`, i.e. measurement only; chronological splits set by date (R12); per-mode normalization `σ_n` is fitted on the training period only and frozen in config (R17 N3); `tune` scores validation only, test appears only with `report --include-test`; automated perturbation and truncation leakage tests (R13). | ✅ |
| III. Documented, verifiable math | The player update is checked principle by principle against the Marveldoss thesis that `Math_plan.pdf` cites (R17), with deviations documented (time normalized by map duration rather than 48 minutes; no home advantage). Formulas in data-model.md §4 use `Math_plan.pdf` notation and cite thesis equation numbers; hand-calculated fixtures for each metric (quickstart §1); naive-counterpart comparisons in `report`; one `RatingSystem` interface (R3); `patch_id` on every map and snapshot. Glicko is out of scope, and the interface leaves room for it. | ✅ |
| IV. Provenance & verification | Not the data-collection feature. Inputs carry `source_ref` and `verification`; `include_unverified` lets runs go with or without unverified maps; input files are read only and never modified. | ✅ |
| V. Baselines first | `report` always includes higher-Elo pick, team-Elo probability, coin flip, and the previous best metric so far, with log loss as the primary metric plus Brier, accuracy and calibration. Negative results are still reported (SC-004). | ✅ |
| VI. Reproducibility | One command per result; pinned deps (`uv.lock`); config in version-controlled YAML; resolved config and input hashes saved with each run; deterministic writer (R10); no pipeline logic in notebooks. | ✅ |
| Data & tech constraints | Python 3.11, pandas and sklearn. PyYAML and hypothesis are justified in R15. Stable IDs through `aliases.csv`. Sample and fixture data lives under `tests/fixtures/`, and real data will go in `data/processed/` once collection exists. | ✅ |

**Post-design re-check (after Phase 1)**: ✅ No violations. The design keeps state mutation in a
single function (`engine.update`), which is what makes Principle II testable.

## Project Structure

### Documentation (this feature)

```text
specs/001-strength-metrics/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R15
├── data-model.md        # Phase 1: entities, state, formulas
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   ├── cli.md           # commands, exit codes, Python API
│   ├── input-schema.md  # input CSV directory
│   ├── config-schema.md # YAML run configuration
│   └── output-schema.md # run directory tables
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml                    # package, console script `owstudy-strength`, pinned deps
uv.lock
configs/strength/default.yaml

src/owstudy/
├── __init__.py
└── strength/
    ├── __init__.py               # public API: load_inputs, load_config, run_history, write_run
    ├── __main__.py               # `python -m owstudy.strength`
    ├── cli.py                    # argparse subcommands: validate, fit-normalization, run, tune, report, check-leakage
    ├── config.py                 # RunConfig dataclasses, YAML load/validate/resolve, hashing
    ├── io/
    │   ├── load.py               # read CSVs → typed MapRecord + Segment objects, alias resolution
    │   ├── segments.py           # segment validation (tiling, boundaries), derive t_jik
    │   ├── validate.py           # schema + data checks → errors vs. exclusions
    │   ├── order.py              # chronological sort + tie/conflict detection (R11)
    │   └── write.py              # deterministic CSV/YAML/manifest writer (R10)
    ├── rating/
    │   ├── base.py               # RatingSystem protocol (R3)
    │   ├── elo.py                # EloRating(k, scale): team Elo and wl variants
    │   └── marveldoss.py         # expected +/-, F, K = γ·t̂, point conservation (R4, R17)
    ├── normalization.py          # fit σ_n on training maps; D → D̃; t̂ (R17 N1–N3)
    ├── scoring/
    │   ├── differential.py       # D per mode for map and segments, defender clock curve (R8)
    │   └── outcome.py            # map S (winner clamp), segment S_g from +/- rate (unclamped)
    ├── metrics/
    │   ├── team.py               # team Elo
    │   ├── player.py             # player ratings, m_j
    │   ├── player_hero.py        # per-segment h_jik updates, p_ji, ts_player_hero(_career)
    │   ├── hero.py               # incremental H_k aggregates (R5), ts_hero (R6)
    │   ├── composition.py        # per-segment composition snapshot Σ H_k (R6)
    │   └── ban.py                # ban impact (R7)
    ├── timing.py                 # column → timing class registry (R16)
    ├── engine.py                 # State, snapshot(), update(), run_history() loop (R2)
    ├── evaluate/
    │   ├── splits.py             # date-based train/validation/test labels
    │   ├── scoring.py            # log loss, Brier, accuracy, calibration (sklearn)
    │   ├── naive.py              # hero win rate, player-hero win rate (pre-map, cumulative)
    │   ├── tune.py               # grid search on validation, sensitivity (R12)
    │   └── report.py             # report.md + tables
    └── leakage.py                # perturbation + truncation checks (R13)

tests/
├── fixtures/
│   ├── reference/<case>/         # hand-calculated cases (quickstart §1)
│   └── sample_season/            # ~150-map synthetic season with seeded data problems
├── unit/                         # elo, differential, outcome mapping, aggregates, ordering, config
├── reference/                    # runs each reference case, compares to expected/ at 4 dp
├── property/                     # hypothesis: D_AB = −D_BA, incremental H_k = recompute, S bounds
├── leakage/                      # perturbation + truncation on sample_season
├── integration/                  # CLI end to end, determinism, tune never scores test
└── perf/                         # synthetic 1,500-map timing
```

**Structure Decision**: A single library + CLI project in src layout. The spec's metric levels
map one-to-one onto `metrics/`, the Elo rule sits alone in `rating/` (FR-011), and
`engine.py` is the only orchestrator of state. `evaluate/` is kept out of `engine.py` so the
rating pass has no knowledge of splits or labels.

### Script walk-through (`owstudy-strength run`)

0. **Once, beforehand**: `fit-normalization` fits each mode's `σ_n` on training-period maps
   and writes it into the config.
1. **Load and resolve**: `config.py` loads the YAML and fills in defaults. `io/load.py` reads the
   CSVs and maps aliases to stable IDs. `io/segments.py` checks that segments tile each map and
   derives each player's hero seconds `t_jik` from them. `io/validate.py` stops on hard errors and turns
   soft problems (Clash, bad roster, missing hero time or score, unverified) into exclusion
   records.
2. **Order**: `io/order.py` sorts by `(date, series_start, series_id, map_number)` and assigns
   `map_seq`. It stops with exit 3 on a same-date tie between series that share a team or player.
3. **Loop** (`engine.run_history`), for each map and for each variant `wl` and `diff`:
   - `snapshot(state, map)` gets pre-map `R_A, R_B` and `μ`. For each player: `p` (initialized to
     1500 and flagged if new) and `m_A, m_B`. For each player-hero: `h`, which gives `p_ji`.
     Then `H_k` for each hero played or banned and ban losses for both teams. **Per segment**:
     the heroes in play give composition strength `comp_j,g = Σ H_k` and `h̄_j,g`, with
     `μ_g`. The map-level team strengths `ts_hero` and `ts_player_hero` time-weight those
     heroes.
   - `score(map)` computes the map `D_AB`, normalizes it to `D̃ = D/σ_n`, and derives team Elo's
     0–1 `S` (logistic, clamped to the winner's side). It also gives each segment's `D_g`, `D̃_g`
     and `t̂_g = d_g/T_map`, and checks `Σ D_g = D_AB` and `Σ t̂_g = 1`.
   - `update(state, map, …)` first updates team Elo with plain `K`. Player ratings then get the
     Marveldoss update (`diff`): expected +/- `μ = t(p + 4m̂ − 5m_k)/α`, `b = F(D̃ − μ)`,
     conservation `b̂`, and `p += γ·t̂·b̂`. The `wl` variant uses `S_wl − Pr`. Each
     player-on-hero entry then gets the same update per segment, over **only** the segments
     where that hero was played, computed from pre-map values and applied together. Last come the
     hero aggregates `(W_k, Q_k)`. Excluded scopes are skipped, and for the `diff` variant a map
     with `missing_score` / `no_segment_score` skips the differential updates.
4. **Write**: `io/write.py` emits the run directory (contracts/output-schema.md), sorted and
   fixed-format, with the manifest and resolved config.
5. **After the run**: `report` labels splits by date and scores every `p_*` column against
   `label_outcome_a`, with `post_map` metrics in their own marked section. It compares each metric with team Elo, its naive counterpart and the other
   variant, using validation (and test only with `--include-test`).

## Complexity Tracking

No constitution violations; nothing to justify.
