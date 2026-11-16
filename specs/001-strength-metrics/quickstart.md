# Quickstart & Validation: Strength Metrics

**Feature**: `001-strength-metrics` | **Plan**: [plan.md](./plan.md)

How to prove the strength script works end to end. Formats are defined in
[contracts/](./contracts/); formulas in [data-model.md §4](./data-model.md).

## Prerequisites

- Python 3.11+ and `uv` (already used for `specify-cli`).
- From repo root: `uv sync` (installs pinned deps from `uv.lock`, package in editable mode).

## 1. Hand-calculated reference examples (SC-001, SC-007, FR-015)

```bash
uv run pytest tests/reference -q
```

Fixtures live in `tests/fixtures/reference/<case>/` (an input directory + `config.yaml` +
`expected/*.csv` computed by hand, with the arithmetic written out in `README.md`). Cases:

| Case | Proves |
|------|--------|
| `elo_first_map` | 50% expectation; winner +K/2, loser −K/2 (US1-1) |
| `elo_draw` | draw → S = 0.5 (US1-3) |
| `elo_5maps_3teams` | multi-map team Elo matches hand calc |
| `player_substitution` | substitute's rating changes only on maps played; m_j uses actual five (US2-1) |
| `marveldoss_expected_pm` | expected +/- `t(p + 4m̂ − 5m_k)/α`, `F` bounds, `K = γ·t̂`, final `p̂` match a hand calc (FR-020) |
| `marveldoss_conservation` | unequal-time case: `d ≠ 0` before correction, sum of ratings unchanged after |
| `normalization_sigma` | `σ_n` fitted on training maps only; `D̃` comparable across two modes (US2a-7) |
| `diff_control` / `diff_push` / `diff_flashpoint` | symmetric differential, `C = X` (US2a-1, US2a-4) |
| `diff_escort` / `diff_hybrid` | both attack halves, time-remaining defender points (US2a-2..4) |
| `diff_clamp` | loser wins kills by a lot → S capped at 0.5, counted (US2a-6) |
| `hero_split_60_40` | 6 min / 4 min → 60/40 weighting in `p_ji` (US3-1) |
| `hero_segment_only` | hero A's update uses only its 5-minute segment: its opponents' heroes, its own differential, weight 5/10 (US3-1a) |
| `segment_diff_sum` | segment differentials sum to the map differential, both escort halves |
| `hero_elo_weights` | H_k weighted by time across players (US4-1) |
| `comp_vs_team_strength` | E→F swap: composition = snapshot sums per segment, independent of duration; `ts_hero` time-weights E and F (US4-2a, 2b) |
| `ban_never_played` / `ban_only_hero` | zero loss / undefined flag (US5-1, US5-2) |

**Expected**: all pass; values match to 4 decimal places.

## 2. Leakage (SC-002)

`configs/strength/sample.yaml` is produced by `fit-normalization` in §3, so run that line first.

```bash
uv run pytest tests/leakage -q
uv run owstudy-strength check-leakage --input tests/fixtures/sample_season --config configs/strength/sample.yaml
```

**Expected**: tests pass; command exits 0 and prints `0 maps with leakage`. Every
`map_features.csv` column has a timing class in `feature_timing.csv`. A test also confirms that
`fit-normalization` reads no validation- or test-period map.

## 3. Full run on the sample season

```bash
uv run owstudy-strength validate          --input tests/fixtures/sample_season --config configs/strength/default.yaml
uv run owstudy-strength fit-normalization --input tests/fixtures/sample_season --config configs/strength/default.yaml --out configs/strength/sample.yaml
uv run owstudy-strength run               --input tests/fixtures/sample_season --config configs/strength/sample.yaml --out runs/sample
uv run owstudy-strength report   --run runs/sample
```

**Expected**:
- `validate` prints counts and the exclusions it would make (e.g., the Clash map and the
  bad-roster map seeded in the sample) and exits 0.
- `runs/sample/` contains every file in [output-schema.md](./contracts/output-schema.md).
- `exclusions.csv` lists each seeded data problem with its reason (FR-013).
- `report/report.md` shows team-Elo validation log loss < 0.693 (SC-003) and a row for every
  metric vs. team Elo and vs. its naive counterpart, for both variants (SC-004, SC-008).
  `post_map` metrics (`ts_hero`, `ts_player_hero`) appear in a separate, labeled section.
- `segment_features.csv` has one row per segment, and composition values change exactly at
  hero swaps.

## 4. Determinism (SC-005)

```bash
uv run owstudy-strength run --input tests/fixtures/sample_season --config configs/strength/sample.yaml --out runs/sample_b
diff -r runs/sample runs/sample_b --exclude=report
```

**Expected**: no output (byte-identical). Also covered by `tests/integration/test_determinism.py`.

## 5. Tuning on validation only (FR-017)

```bash
uv run owstudy-strength tune --input tests/fixtures/sample_season --config configs/strength/sample.yaml --out runs/tune_sample --jobs 4
```

**Expected**: `best_config.yaml`, `grid_results.csv`, `sensitivity.csv`; `grid_results.csv`
contains only validation-period scores. `tests/integration/test_tune_no_test_access.py` asserts
test-period rows are never scored.

## 6. Performance (SC-006)

```bash
uv run pytest tests/perf -q   # generates a synthetic 1,500-map history and times `run`
```

**Expected**: `run` completes in well under 5 minutes (target: < 10 s).
