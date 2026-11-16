# Contract: `owstudy-strength` command line

Entry point: `owstudy-strength` (console script) ≡ `python -m owstudy.strength`.
All commands are deterministic given the same inputs and config. Exit codes: `0` success,
`1` validation/data error (message lists every problem), `2` usage error, `3` ordering conflict,
`4` missing mode constant, `5` leakage detected.

## `validate`

```text
owstudy-strength validate --input DIR --config FILE
```

Loads and resolves the input tables ([input-schema.md](./input-schema.md)), checks schema,
aliases, rosters, modes, and ordering, and prints a summary (maps, teams, players, heroes,
date range, would-be exclusions by reason). Writes nothing. Fails with exit 3 on ordering
conflicts and exit 4 on a mode with no constants.

## `fit-normalization`

```text
owstudy-strength fit-normalization --input DIR --config FILE --out FILE
```

Computes the per-mode normalization constants `σ_n` (std of the differential per minute) from
**training-period maps only** (research R17 N3), and writes a copy of the config with
`normalization.sigma` filled in. It also prints the number of maps per mode and which modes fell
back to the pooled σ. Run it once before `tune`/`run`, and commit the result.

## `run`

```text
owstudy-strength run --input DIR --config FILE --out RUN_DIR [--overwrite]
```

Runs the chronological pass and writes the run directory ([output-schema.md](./output-schema.md)).
Refuses to write into a non-empty `RUN_DIR` unless `--overwrite`.

## `tune`

```text
owstudy-strength tune --input DIR --config FILE --out TUNE_DIR [--jobs N]
```

Grid-searches the `tune:` grids in the config, scoring **validation-period** log loss only
(the test period is never read for scoring). Writes `best_config.yaml`, `grid_results.csv`
(every config × metric × variant × validation log loss/Brier/accuracy), and `sensitivity.csv`.
`--jobs` parallelizes; output is sorted so it is identical for any `N`.

## `report`

```text
owstudy-strength report --run RUN_DIR [--include-test]
```

Reads a run directory and writes `RUN_DIR/report/` (`report.md` and CSV tables): each metric vs.
team Elo and vs. baselines (log loss, Brier, accuracy, calibration table) per split; win/loss vs.
differential variant (FR-018, SC-008); naive-counterpart comparisons (hero Elo vs. hero win rate,
player-on-hero vs. player-hero win rate); per-patch hero strengths; ban impact vs. outcome;
exclusion counts; clamped-differential counts. Test-period columns appear only with
`--include-test` (final reporting, Constitution II).

## `check-leakage`

```text
owstudy-strength check-leakage --input DIR --config FILE [--samples 20] [--seed 0]
```

Perturbation and truncation tests (research R13). Exit 0 if no snapshot depends on its own or a
later map; exit 5 with the offending map/column otherwise.

## Python API (same contract, for notebooks and the modeling feature)

```python
from owstudy.strength import load_inputs, load_config, run_history, write_run

inputs = load_inputs("data/processed/maps_v1")      # validated, alias-resolved
config = load_config("configs/strength/default.yaml")
result = run_history(inputs, config)                 # pure function, no I/O
result.map_features    # pandas.DataFrame (see output-schema.md)
result.snapshots       # dict[str, DataFrame]: team, player, player_hero, hero
result.ban_impact, result.exclusions, result.map_scores
write_run(result, "runs/default")
```

`run_history` performs no I/O and never mutates `inputs` or `config`.
