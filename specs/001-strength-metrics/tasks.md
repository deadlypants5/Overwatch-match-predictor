---

description: "Task list for the Strength Metrics feature (owstudy-strength)"
---

# Tasks: Strength Metrics

**Input**: Design documents from `/specs/001-strength-metrics/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli, input-schema, config-schema, output-schema), quickstart.md

**Tests**: INCLUDED. The spec requires hand-calculated reference examples for every metric (FR-015, SC-001, SC-007), and the constitution requires unit tests for rating math and an automated leakage test for every feature-producing stage (Principles II, III). Reference fixtures and tests come before implementation in each story. They must fail first.

**Organization**: Tasks are grouped by user story so each story can be built and tested on its own. Story labels match spec.md: US1, US2a, US2, US3, US4, US5. **US2a (score differential) is scheduled before US2** because the player `diff` variant needs the normalized differential `D̃`.

**Conventions used in every task**:
- Paths are relative to the repo root (`C:\Users\mwill\Desktop\ow_study`). Source is in `src/owstudy/strength/`, tests are in `tests/`.
- "Formula X" means the row of that name in the formulas table of `specs/001-strength-metrics/data-model.md` §4. Implement it exactly as written and cite the Marveldoss (2018) equation number in the docstring.
- A **reference fixture** `tests/fixtures/reference/<case>/` contains `input/` (CSVs per contracts/input-schema.md), `config.yaml`, `expected/*.csv` (only the columns being checked, values computed by hand), and a `README.md` with the arithmetic written out step by step. `tests/reference/test_reference_cases.py` (T020) discovers it automatically.
- Every output column must be registered in `timing.py` (T014) with its timing class from output-schema.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: The user story the task belongs to (US1, US2a, US2, US3, US4, US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create `pyproject.toml`: package `owstudy` in src layout, `requires-python = ">=3.11"`, dependencies pandas, numpy, scikit-learn, PyYAML; dev group pytest, hypothesis; console script `owstudy-strength = "owstudy.strength.cli:main"`; `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and a `perf` marker
- [ ] T002 Create the package skeleton from plan.md: `src/owstudy/__init__.py`, `src/owstudy/strength/__init__.py`, `src/owstudy/strength/__main__.py` (calls `cli.main()`), and empty `__init__.py` files in `src/owstudy/strength/io/`, `rating/`, `scoring/`, `metrics/`, `evaluate/`
- [ ] T003 [P] Create the test tree `tests/unit/`, `tests/reference/`, `tests/property/`, `tests/leakage/`, `tests/integration/`, `tests/perf/`, `tests/fixtures/reference/`, plus `tests/conftest.py` with fixtures `fixtures_dir`, `reference_cases` (list of case directories) and `tmp_run_dir`
- [ ] T004 [P] Create `configs/strength/default.yaml` with exactly the keys and placeholder values in contracts/config-schema.md (`schema_version: 1`, `initial_rating`, `elo_scale`, `k`, `marveldoss`, `normalization`, `score`, `modes`, `excluded_modes: [clash]`, `include_unverified: false`, `splits`, `tune`)
- [ ] T005 Run `uv lock` and `uv sync` to produce `uv.lock` and install in editable mode. Add `runs/` to `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, input loading and validation, ordering, the deterministic writer, the timing registry, the rating interface, and the engine loop. Every story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Implement `src/owstudy/strength/config.py`: frozen `RunConfig` dataclasses mirroring contracts/config-schema.md; `load_config(path)` that rejects unknown keys, fills defaults (`initial_rating` 1500 per entity type, `elo_scale` 400, `min_maps_for_sigma` 30), requires every mode to have `symmetric` and `X`, rejects `C` on symmetric modes ("For symmetric modes `C` must be absent (it is fixed to `X`)") and sets `C := X` for them, requires `C` on asymmetric modes; `resolve()` → plain dict; `dump_resolved_yaml()` with sorted keys; `config_sha256()` over the canonical resolved YAML; `with_overrides(dotted_key → value)` for `tune` (keys like `k.gamma.player.diff`)
- [ ] T007 [P] Write `tests/unit/test_config.py`: unknown key error, symmetric mode with `C` rejected, asymmetric without `C` rejected, defaults filled, the same config gives the same hash, `with_overrides` on dotted keys
- [ ] T008 Implement `src/owstudy/strength/io/load.py`: frozen dataclasses `MapRecord`, `Segment`, `SegmentHero`, `Ban`, `Attack`, `Alias` with the fields in data-model.md §1; `read_input_dir(path)` that reads `maps.csv`, `segments.csv`, `segment_heroes.csv`, `bans.csv`, `attacks.csv`, `entities/aliases.csv` (optional, identity mapping if absent) as UTF-8 with empty cell = missing; resolve team/player/hero aliases to `stable_id` by `valid_from`/`valid_to` against the map `date`; when map-level `kills_*`/`obj_*` are empty, sum them from segments. Input files are read only and never modified
- [ ] T009 Implement `src/owstudy/strength/io/segments.py`: check per map that `segment_no` is "Contiguous `1..G` per map", `end_s > start_s`, segments "tile the map without gaps or overlaps", no segment crosses an `attack_order` boundary, clock positions lie in `[0, attack_clock_s]`; check "Exactly 5 players per team per segment, and the same 5 players in every segment of a map" else soft flag `bad_roster`; a player missing a hero row in any segment → soft flag `missing_hero_time`; derive `t_jik = Σ_{g: i on k} (end_s − start_s)` and `T_ji = Σ_k t_jik` and `T_map`
- [ ] T010 Implement `src/owstudy/strength/io/validate.py`: collect **all** hard errors listed in contracts/input-schema.md "Validation errors" (unknown/missing column, duplicate `map_id` or `(series_id, map_number)`, unknown `map_id` references, segment tiling errors from T009, map totals disagreeing with summed segments, `time_remaining_s > attack_clock_s`, progress outside [0,1], asymmetric map without attacks for both teams, alias overlaps, `team_a_id == team_b_id`, `winner` not in `a|b|draw`, more than one ban per team per map) and raise one `InputValidationError` listing them; raise `MissingModeConstantError` for a `mode_id` that is neither in `config.modes` nor in `excluded_modes`; turn soft problems into `ExclusionRecord(map_id, team_id?, player_id?, metric_scope, reason)` with `metric_scope ∈ all|player|player_hero|hero|diff|ban` and `reason ∈ clash_mode | unverified | bad_roster | missing_hero_time | missing_score | no_segment_score`; Clash → `(all, clash_mode)`; unverified when `include_unverified: false` → `(all, unverified)`; missing map kills/objective → `(diff, missing_score)`; missing segment kills/objective → `(player_hero diff, no_segment_score)`. Expose `load_inputs(path, config) -> Inputs`
- [ ] T011 Implement `src/owstudy/strength/io/order.py`: sort by `(date, series_start, series_id, map_number)` and assign dense `map_seq` 0..N−1; when two series on the same date both lack `series_start` **and share any team or player**, raise `OrderingConflictError` listing them; otherwise fall back to `series_id` order (research R11)
- [ ] T012 [P] Implement `src/owstudy/strength/io/write.py`: `write_table(df, path, columns)` with a fixed column order, rows sorted by `(map_seq, team_side, entity_id)` (or the table's declared key), floats formatted `%.10f`, empty string for missing, `\n` line endings, UTF-8 without BOM; `write_manifest()` with package version, SHA-256 of each input file, config SHA-256, row counts, and **no timestamps or absolute paths**; `write_run(result, run_dir, overwrite=False)` that refuses a non-empty `run_dir` unless `overwrite`
- [ ] T013 [P] Write `tests/unit/test_io.py`: one test per hard error in T010 (each built from a tiny inline input dir), each soft flag produces the right `ExclusionRecord`, alias rename resolves to the same stable ID, ordering conflict raised only when series share an entity, writer output is byte-identical across two calls and contains no `\r`
- [ ] T014 [P] Implement `src/owstudy/strength/timing.py`: a registry `COLUMN_TIMING: dict[str, str]` mapping every `map_features.csv` and `segment_features.csv` column in contracts/output-schema.md to `key | pre_map | map_start | segment | post_map | label`; `feature_timing_table()` for `feature_timing.csv`; `assert_all_registered(columns)` raising on any unregistered column
- [ ] T015 [P] Implement `src/owstudy/strength/rating/base.py`: `RatingSystem` Protocol with `expected(r_a: float, r_b: float) -> float` and `delta(s: float, mu: float, weight: float = 1.0) -> float` (research R3). Metric modules call only this protocol, never an Elo formula directly
- [ ] T016 Implement `src/owstudy/strength/engine.py`: `State` holding dicts keyed per data-model.md §3 (`TeamRating[(variant, team_id)]`, `PlayerRating[(variant, player_id)]`, `PlayerHeroRating[(variant, player_id, hero_id)]`, `HeroAggregate[(variant, hero_id)]`, `PlayerTeamHistory[player_id]`) with `variant ∈ {wl, diff}`; `snapshot(view, map)` that receives a read-only view (`types.MappingProxyType`); `score(map)`; `update(state, map, scores)` as the **only** function that mutates state; `run_history(inputs, config) -> RunResult` that loops maps by `map_seq` calling snapshot → score → update for each enabled metric module (a registry list that later phases append to), is pure (no I/O, never mutates `inputs`/`config`), and iterates dicts only through `sorted()`. `RunResult` has `map_features`, `segment_features`, `snapshots` (dict of DataFrames), `map_scores`, `segment_scores`, `ban_impact`, `exclusions`
- [ ] T017 Implement `src/owstudy/strength/__init__.py` public API (`load_inputs`, `load_config`, `run_history`, `write_run`) and `src/owstudy/strength/cli.py`: argparse subcommands `validate`, `fit-normalization`, `run`, `tune`, `report`, `check-leakage` with the arguments in contracts/cli.md; map exceptions to exit codes `1` data error (print every problem), `2` usage, `3` ordering conflict, `4` missing mode constant, `5` leakage. Fully implement `validate` (prints maps, teams, players, heroes, date range, would-be exclusions by reason; writes nothing). The other subcommands are stubs that later tasks fill in
- [ ] T018 Write `tests/fixtures/make_sample_season.py` (fixed seed 0, deterministic) that generates and commits `tests/fixtures/sample_season/` (~150 maps, ~8 teams, all five in-scope modes, hero swaps, bans, dates spanning the default `splits`) with exactly one of each seeded problem: a Clash map, a bad-roster map, a map with missing hero time, a map with missing kills, a map with segment heroes but no segment kills/objective, and an unverified map. Run it and commit the CSVs
- [ ] T019 [P] Write `tests/integration/test_validate_cli.py`: `owstudy-strength validate` on `tests/fixtures/sample_season` exits 0 and lists all six seeded exclusions; an input with a hard error exits 1; an ordering conflict exits 3; a mode missing from config exits 4
- [ ] T020 Write `tests/reference/test_reference_cases.py`: parametrized over every directory in `tests/fixtures/reference/`; runs `run_history` on `input/` with `config.yaml` and, for each `expected/<table>.csv`, joins on the key columns and asserts every given value matches to 4 decimal places (SC-001); fails if a case has no `README.md`

**Checkpoint**: `validate` works on the sample season; the engine loop runs with no metrics registered.

---

## Phase 3: User Story 1 - Team Elo and pre-map win probability (Priority: P1) 🎯 MVP

**Goal**: For every map, each team's pre-map Elo and the implied win probability, updated with `R_new = R_old + K(S − μ)`; plus the evaluation and leakage tooling every later metric reuses.

**Independent Test**: `uv run pytest tests/reference -k elo` passes on the hand-calculated cases, and `owstudy-strength run` + `report` on the sample season give team-Elo validation log loss below 0.693.

### Tests for User Story 1 ⚠️ (write first, must fail)

- [ ] T021 [P] [US1] Create reference fixture `tests/fixtures/reference/elo_first_map/`: two new teams, one map, `k.team: 20`; expected `p_team_elo_a = 0.5`, winner `rating_post = 1510`, loser `1490` (US1 scenario 1)
- [ ] T022 [P] [US1] Create reference fixture `tests/fixtures/reference/elo_draw/`: one drawn map; expected `S = 0.5` for both and no rating change between equal teams, plus a second draw between unequal teams with the hand-calculated change (US1 scenario 3)
- [ ] T023 [P] [US1] Create reference fixture `tests/fixtures/reference/elo_5maps_3teams/`: 5 maps, 3 teams, including one team changing display name through `entities/aliases.csv`; expected `rating_pre`/`rating_post` per map computed by hand (US1 scenario 2, rebrand edge case)
- [ ] T024 [P] [US1] Write `tests/unit/test_elo.py`: `expected` is `1 / (1 + 10^((R_B − R_A)/400))`, symmetric (`expected(a,b) + expected(b,a) = 1`), `delta(s, mu) = K·(s − mu)`

### Implementation for User Story 1

- [ ] T025 [P] [US1] Implement `src/owstudy/strength/rating/elo.py`: `EloRating(k, scale=400)` satisfying `RatingSystem` with Formula "Expectation" and "Team update"
- [ ] T026 [P] [US1] Implement `src/owstudy/strength/scoring/outcome.py` part 1: `s_wl(winner) -> (S_A, S_B)` with `a → (1, 0)`, `b → (0, 1)`, `draw → (0.5, 0.5)`
- [ ] T027 [US1] Implement `src/owstudy/strength/metrics/team.py` (`wl` variant): snapshot `team_elo_a`, `team_elo_b`, `p_team_elo_a`, `is_default` (new team initialized at `initial_rating.team` and flagged); update via `EloRating` with `k.team`. Ratings key on stable team ID only, so a player changing teams never moves team Elo. Team Elo updates even when a map has player-level exclusions; it is skipped only for `metric_scope = all` exclusions
- [ ] T028 [US1] Register the team metric in `src/owstudy/strength/engine.py` and emit `snapshots_team.csv` rows (`map_seq, map_id, patch_id, variant, team_id, rating_pre, rating_post, is_default`), the key columns and `label_outcome_a`, `label_S_a` of `map_features.csv`, and `S_wl_a` in `map_scores.csv`; register the new columns in `timing.py`
- [ ] T029 [US1] Implement the `run` subcommand in `src/owstudy/strength/cli.py`: load config + inputs, `run_history`, `write_run` producing every file in contracts/output-schema.md (empty-but-headed tables for metrics not yet built), `config.resolved.yaml`, `feature_timing.csv`, `exclusions.csv`, `manifest.json`; refuse a non-empty `--out` without `--overwrite`
- [ ] T030 [P] [US1] Implement `src/owstudy/strength/evaluate/splits.py`: label each map `train` (`date ≤ train_end`), `validation` (`≤ validation_end`), else `test`; fill the `split` column of `map_features.csv` from it in `report` and `run`
- [ ] T031 [P] [US1] Implement `src/owstudy/strength/evaluate/scoring.py`: `score_probs(p, y)` → log loss, Brier, accuracy via `sklearn.metrics` and a 10-bin reliability table via `sklearn.calibration.calibration_curve`; baselines: coin flip 0.5, always-pick-higher-team-Elo (`wl` team Elo), team-Elo probability, and **previous best**: the `p_*` column (any variant) with the lowest validation log loss among metrics from earlier stories (falls back to team-Elo probability in US1). Draws (`label_outcome_a = 0.5`) are excluded from scoring and counted
- [ ] T032 [US1] Implement `src/owstudy/strength/evaluate/report.py` and the `report` subcommand: read a run directory, write `RUN_DIR/report/report.md` plus CSV tables with, per split, every `p_*` column scored against `label_outcome_a` next to the four baselines, a calibration table, and exclusion counts by `reason × metric_scope` (FR-013). Test-period numbers appear only with `--include-test`. `post_map` columns go in a separate section titled "Post-map measurements (not pre-map features)". The report is organized as a list of section builders that later stories append to
- [ ] T033 [US1] Implement `src/owstudy/strength/leakage.py` and the `check-leakage` subcommand (research R13): **perturbation**: for `--samples` maps `m` chosen with `--seed`, flip the result and scramble kills/objective of `m` and every later map, rerun, and assert every snapshot for maps `< m` and every `pre_map`/`map_start` column for `m` is unchanged; **truncation**: running on maps `[0, m]` gives the same snapshot for `m`; **coverage**: every `map_features.csv` column is registered in `timing.py`. Print `0 maps with leakage` and exit 0, or exit 5 naming the map and column
- [ ] T034 [P] [US1] Write `tests/leakage/test_leakage.py`: calls `leakage.check(...)` on `tests/fixtures/sample_season` and asserts no violations (SC-002); a deliberately leaky dummy metric registered in the test is detected
- [ ] T035 [P] [US1] Write `tests/integration/test_determinism.py` (two `run`s → `filecmp.dircmp` shows no differences, SC-005) and `tests/integration/test_run_cli.py` (run output contains every file in output-schema.md; `--overwrite` refusal; `report` without `--include-test` has no test-period numbers; team-Elo validation log loss < 0.693 on the sample season, SC-003)

**Checkpoint**: MVP. Team Elo, pre-map probabilities, report against baselines, leakage check, determinism.

---

## Phase 4: User Story 2a - Map score differential (Priority: P2)

**Goal**: A per-map and per-segment score differential `D_AB = a·(Kills_A − Kills_B) + X_n·Obj_A − C_n·Obj_B`, normalized per mode by `σ_n` fitted on the training period, mapped to a 0–1 `S` for team Elo's `diff` variant.

**Independent Test**: `uv run pytest tests/reference -k "diff_ or segment_diff or normalization" tests/property/test_differential_props.py` passes; differentials match hand-scored maps for every mode exactly (SC-007).

### Tests for User Story 2a ⚠️ (write first, must fail)

- [ ] T036 [P] [US2a] Create reference fixtures `tests/fixtures/reference/diff_control/`, `diff_push/`, `diff_flashpoint/`: symmetric maps with expected `points_a/b = X·obj`, `D_ab`, and one Control map with kills 30–20 and equal objective giving `D_ab = a × 10` (US2a scenario 1, US2 scenario 4)
- [ ] T037 [P] [US2a] Create reference fixtures `tests/fixtures/reference/diff_escort/` and `diff_hybrid/`: both teams attack; each team gets `X·att` for its own attack and `C·def` with `def = 1 − time_remaining/attack_clock`; one attack using banked time; a second map where attackers finish with more time remaining gives defenders fewer points (US2a scenarios 2–4, overtime edge case)
- [ ] T038 [P] [US2a] Create reference fixture `tests/fixtures/reference/diff_clamp/`: map loser wins kills by a wide margin so `D_ab` favors the loser; expected `S_diff_a` clamped to 0.5 on the winner's side and `clamped = true` (US2a scenario 6)
- [ ] T039 [P] [US2a] Create reference fixture `tests/fixtures/reference/segment_diff_sum/`: an escort map with several segments in both attack halves; expected `D_g` per segment that sum to `D_ab`, defender segment points `curve(e_end/clock) − curve(e_start/clock)`, and `t_hat_g` summing to 1
- [ ] T040 [P] [US2a] Create reference fixture `tests/fixtures/reference/normalization_sigma/`: training maps in two modes plus validation maps with extreme differentials; expected `σ_n` (std of `D_map / T_map` in minutes over training maps of that mode only) unchanged by the validation maps, and `D_norm_ab = D_ab / σ_n` (US2a scenario 7)
- [ ] T041 [P] [US2a] Write `tests/property/test_differential_props.py` (hypothesis): `D_BA = −D_AB`; `Σ_g D_g = D_AB` and `Σ_g t̂_g = 1` within 1e-9 for random segmentations; for any curve, segment defender points sum to the attack's total; `S_diff_a ∈ [0, 1]`, winner's `S ≥ 0.5`, loser's `≤ 0.5`, `S_diff_b = 1 − S_diff_a`; two maps with the same kill/objective differences differ only through `X_n`, `C_n` (US2a scenario 5)
- [ ] T042 [P] [US2a] Write `tests/unit/test_differential.py`: linear defender curve and `power(γ)` curve are monotone, clipped to [0, 1]; symmetric mode uses `C = X`; a mode with no constants raises `MissingModeConstantError`; Clash is excluded and flagged; fewer than `min_maps_for_sigma` training maps → pooled σ and a flag

### Implementation for User Story 2a

- [ ] T043 [US2a] Implement map-level differential in `src/owstudy/strength/scoring/differential.py` (research R8): defender points `def = 1 − time_remaining_s / attack_clock_s` clipped to [0, 1] through `def_curve` (`linear`, or `power` with `gamma`); symmetric `D_AB = a·(K_A − K_B) + X_n·(Obj_A − Obj_B)`; asymmetric `D_AB = a·(K_A − K_B) + [X_n·att_A + C_n·def_A] − [X_n·att_B + C_n·def_B]`; compute `D_AB` once and return `D_BA = −D_AB`; return `points_a`, `points_b`, `D_ab`, `score_status` (`ok | missing_score | excluded`)
- [ ] T044 [US2a] Add per-segment differential to `src/owstudy/strength/scoring/differential.py`: same formula on segment kills and objective gained; asymmetric defenders get `curve(clock_elapsed_end_s/clock) − curve(clock_elapsed_start_s/clock)`; `t̂_g = d_g / T_map`; raise if `|Σ D_g − D_AB| > 1e-9` or `|Σ t̂_g − 1| > 1e-9`; segments with missing kills/objective get `score_status = no_segment_score`
- [ ] T045 [US2a] Implement `src/owstudy/strength/normalization.py` (research R17 N1–N3): `fit_sigma(inputs, config)` using **only maps with `date ≤ splits.train_end`**, σ_n = std of `D_map / T_map` (minutes) per mode, pooled σ for modes with fewer than `min_maps_for_sigma` training maps (returned with a flag list); `normalize(D, mode) = D / σ_n`; `run` refuses the `diff` variant (clear error) when `normalization.sigma` is empty, while `wl` still runs
- [ ] T046 [US2a] Implement the `fit-normalization` subcommand in `src/owstudy/strength/cli.py`: write a copy of `--config` to `--out` with `normalization.sigma` filled in (sorted keys), print maps per mode and the modes that fell back to pooled σ
- [ ] T047 [US2a] Extend `src/owstudy/strength/scoring/outcome.py`: `s_diff(D_norm_ab, winner, s)` = `1 / (1 + exp(−D̃_AB / s))`, then `max(·, 0.5)` if A won, `min(·, 0.5)` if A lost, unclamped on a draw, `S_B = 1 − S_A`, returning `clamped`; segment `S_g_wl_a = S_wl_a` (the map result) and segment `D_norm_g` unclamped
- [ ] T048 [US2a] Add the `diff` variant of team Elo to `src/owstudy/strength/metrics/team.py` using `S_diff_a`; maps with `missing_score` skip the `diff` update and record a `(diff, missing_score)` exclusion
- [ ] T049 [US2a] Wire scoring into `src/owstudy/strength/engine.py` `score()` and emit `map_scores.csv` (`map_seq, map_id, mode_id, duration_s, kills_a, kills_b, points_a, points_b, D_ab, sigma_mode, D_norm_ab, S_wl_a, S_diff_a, clamped, score_status`), `segment_scores.csv` (`map_seq, map_id, segment_no, duration_s, kills_a, kills_b, t_hat_g, points_a, points_b, D_g, D_norm_g, S_g_wl_a, score_status`), and `label_D_ab` in `map_features.csv`; register columns in `timing.py`
- [ ] T050 [US2a] Add report sections in `src/owstudy/strength/evaluate/report.py`: count of "differential disagrees with result" (clamped) maps, σ_n per mode with pooled-fallback flags, team Elo `wl` vs `diff` on the same split (FR-018, SC-008)
- [ ] T051 [P] [US2a] Write `tests/leakage/test_normalization_training_only.py`: changing any validation- or test-period map leaves `fit_sigma` output identical, and `fit_sigma` reads no map after `train_end`

**Checkpoint**: Differentials match hand scores for every mode; team Elo runs in both variants.

---

## Phase 5: User Story 2 - Player ratings and team strength built from players (Priority: P2)

**Goal**: A rating for every player, updated after each map with the Marveldoss (2018) +/- update (`diff`) and a win/loss comparison variant (`wl`), and the time-weighted team strength `m_j` with its win probability.

**Independent Test**: `uv run pytest tests/reference -k "player_substitution or marveldoss" tests/unit/test_marveldoss.py` passes; on a history with a substitution, the substitute's rating changes only on maps they played.

### Tests for User Story 2 ⚠️ (write first, must fail)

- [ ] T052 [P] [US2] Create reference fixture `tests/fixtures/reference/player_substitution/`: a 3-map series where one player is substituted after map 1; expected `m_a` per map uses the five who played; the substitute's `rating_post` changes only on maps played; the new player starts at 1500 with `is_default = true`; a player who moves to another team keeps their rating while team Elo stays with the team (US2 scenarios 1–2, edge case)
- [ ] T053 [P] [US2] Create reference fixture `tests/fixtures/reference/marveldoss_expected_pm/`: unequal pre-map player ratings; hand-calculated `m_j`, `m̂_ji`, `μ_ji = t_ji (p_ji + 4 m̂_ji − 5 m_k) / α` (t in minutes), `b = F(D̃ − μ)` with `F(x) = 1/(1 + e^{−x/β}) − 0.5`, `K = γ·t̂`, final `p̂` for both `diff` and `wl` variants side by side (FR-020, US2 scenario 3)
- [ ] T054 [P] [US2] Create reference fixture `tests/fixtures/reference/marveldoss_conservation/`: an unequal-time case (use a segment-level hero update built on the same function, or a direct call through a unit-level fixture) where `d = Σ t̂ b ≠ 0` before correction; expected `b̂ = 2b − d / Σ_{own team} t̂` and the sum of ratings unchanged after the update
- [ ] T055 [P] [US2] Write `tests/unit/test_marveldoss.py`: `F` is odd and bounded to (−0.5, 0.5); `μ = 0` when all ratings are equal; after conservation `Σ t̂·b̂ = 0` within 1e-9; with equal times and `F` odd, `d = 0` so the step is an identity; `K = γ·t̂`; with all players playing the full map, all five teammates get the same update (research R4 consequence)

### Implementation for User Story 2

- [ ] T056 [P] [US2] Implement `src/owstudy/strength/rating/marveldoss.py`: `expected_pm(t_min, p_i, m_hat_i, m_opp, alpha)` (Formula "Expected +/- (`diff`)", thesis eq. 2.8), `F(x, beta)` (§2.2.4), `conserve(b, t_hat, team_of)` (Formula "Conservation", eq. 2.27, applied only when `marveldoss.conserve_points`), `k_factor(gamma, t_hat)` (eq. 2.10)
- [ ] T057 [US2] Implement snapshot in `src/owstudy/strength/metrics/player.py`: per player `rating_pre` and `is_default` (new player initialized at `initial_rating.player`), `m_j = Σ_n t_jn p_jn / Σ_n t_jn` and `m̂_ji` (Formulas "Player team strength", "Team strength without `i`"), `p_player_a = expected(m_a, m_b)`, `n_default_players_a/b`; maintain `PlayerTeamHistory` as `(team_id, first_map_seq)` on each appearance
- [ ] T058 [US2] Implement update in `src/owstudy/strength/metrics/player.py`: `diff` variant `p ← p + γ_player·t̂·b̂` with `S = D̃_map` (Formula "Player update (`diff`)"); `wl` variant `p ← p + γ_player,wl·t̂·(S_wl − Pr(m_j > m_k))` (Formula "Player update (`wl`)"); `t̂ = t / T_map`; all updates for a map computed from pre-map ratings and applied together; teams with `bad_roster` skip player metrics (team Elo still updates) and maps with `missing_score` skip only the `diff` update, each with an exclusion record
- [ ] T059 [US2] Register the player metric in `src/owstudy/strength/engine.py` and emit `snapshots_player.csv` (`map_seq, map_id, patch_id, variant, team_id, player_id, rating_pre, rating_post, is_default`) and `map_features.csv` columns `m_a, m_b, p_player_a, n_default_players_a/b, player_metrics_ok_a/b` (empty values when skipped); register columns in `timing.py` as `pre_map`
- [ ] T060 [US2] Add a report section in `src/owstudy/strength/evaluate/report.py`: `p_player_a` vs team Elo and baselines per split, `wl` vs `diff` (FR-012, FR-018)

**Checkpoint**: Player ratings in both variants; roster changes move `m_j`.

---

## Phase 6: User Story 3 - Player-on-hero strength (Priority: P3)

**Goal**: A rating `h_jik` per player per hero, updated per segment only from the segments in which that hero was played, and the player's combined strength `p_ji = Σ_k t_jik·h_jik / Σ_k t_jik`.

**Independent Test**: `uv run pytest tests/reference -k "hero_split or hero_segment"` passes; a hero swap partway through a map updates each hero only from its own segments.

### Tests for User Story 3 ⚠️ (write first, must fail)

- [ ] T061 [P] [US3] Create reference fixture `tests/fixtures/reference/hero_split_60_40/`: a player on hero A for 360 s and hero B for 240 s; expected `p_ji` weights A at 0.6 and B at 0.4; `seconds` per hero in `snapshots_player_hero.csv` (US3 scenario 1)
- [ ] T062 [P] [US3] Create reference fixture `tests/fixtures/reference/hero_segment_only/`: a 600 s map where a player is on hero A for the first 300 s then swaps; expected hero A `delta` uses only segment 1's opponents' heroes (for `μ_g`), segment 1's `D̃_g` (diff variant), and `t̂_g = 300/600`; changing anything after the swap leaves hero A's `delta` unchanged; also a map with no segment kills (`no_segment_score`) where only the `wl` variant updates (US3 scenario 1a, edge case)
- [ ] T063 [P] [US3] Write `tests/unit/test_player_hero.py`: two players with identical map histories but different heroes get different `h` (US3 scenario 2); `delta` equals the sum of that hero's per-segment updates; all segment updates use pre-map `h` and apply after the map; a player with `missing_hero_time` is skipped and flagged while team Elo still updates

### Implementation for User Story 3

- [ ] T064 [US3] Implement snapshot in `src/owstudy/strength/metrics/player_hero.py`: per `(variant, player_id, hero_id)` `rating_pre`, `career_seconds_pre`, `is_default` (initialized at `initial_rating.player_hero`); `p_ji` (Formula "Hero-weighted player strength", this map's times); per segment `h̄_j,g` (Formula "Segment strength (player-on-hero)") and `mu_g_a`; `ts_player_hero_j = (1/5) Σ_i p_ji` (`post_map`) and `ts_player_hero_career_j` with career times (`pre_map`) and their probabilities `p_ts_player_hero_a`, `p_ts_player_hero_career_a`
- [ ] T065 [US3] Implement update in `src/owstudy/strength/metrics/player_hero.py`: for each segment `g` and each of the 10 entries in play, `μ_g,i = d_g (h_i,g + 4 ĥ_−i,g − 5 h̄_k,g)/α` (d_g in minutes), `S_g = D̃_g`, `b = F(S_g − μ_g)`, conservation over the 10 entries in `g`, `Δh_jik += γ_ph·t̂_g·b̂` (Formula "Player-on-hero update (`diff`)"); `wl` variant `b = S_wl − Pr(h̄_j,g > h̄_k,g)` (Formula "Player-on-hero update (`wl`)"); all from pre-map `h`, applied after the map; add segment seconds to `career_seconds` and increment `maps`; skip `missing_hero_time` players and `no_segment_score` maps (diff only) with exclusion records. Reuse `rating/marveldoss.py`
- [ ] T066 [US3] Register the player-on-hero metric in `src/owstudy/strength/engine.py` and emit `snapshots_player_hero.csv` (`map_seq, map_id, patch_id, variant, player_id, hero_id, seconds, n_segments, rating_pre, delta, rating_post, career_seconds_pre, is_default`), the `segment_features.csv` columns `map_seq, map_id, segment_no, start_s, end_s, duration_s, variant, heroes_a, heroes_b` (sorted hero IDs joined with `|`), `hbar_a, hbar_b, mu_g_a, label_D_g, label_D_norm_g, label_S_g_a`, and `map_features.csv` columns `ts_player_hero_career_a/b, p_ts_player_hero_career_a, ts_player_hero_a/b, p_ts_player_hero_a, n_segments`; register timing classes
- [ ] T067 [P] [US3] Implement player-hero win rate in `src/owstudy/strength/evaluate/naive.py`: cumulative wins/maps per `(player_id, hero_id)` using only maps before each map (pre-map), time-weighted by seconds on the hero
- [ ] T068 [US3] Add report sections in `src/owstudy/strength/evaluate/report.py`: player-on-hero rating vs player-hero win rate (rank correlation and a table of the largest disagreements, US3 scenario 3); `p_ts_player_hero_career_a` vs team Elo, `wl` vs `diff`; `ts_player_hero` in the post-map section

**Checkpoint**: Teammates who always play together can now be told apart through their heroes.

---

## Phase 7: User Story 4 - Hero strength and composition strength (Priority: P4)

**Goal**: Hero Elo `H_k`, per-segment composition strength `comp = Σ H_k` of heroes in play, and hero-weighted team strength `Σ_i Σ_k (t_jik / T_ji)·H_k`, each compared to raw hero win rates.

**Independent Test**: `uv run pytest tests/reference -k "hero_elo or comp_vs" tests/property/test_hero_aggregate_props.py` passes; the report shows hero Elo vs hero win rate per patch.

### Tests for User Story 4 ⚠️ (write first, must fail)

- [ ] T069 [P] [US4] Create reference fixture `tests/fixtures/reference/hero_elo_weights/`: one hero played by three players for different career times; expected `H_k = Σ t h / Σ t`; a hero with no prior play uses the default 1500 and `no_history = true` (US4 scenarios 1–2)
- [ ] T070 [P] [US4] Create reference fixture `tests/fixtures/reference/comp_vs_team_strength/`: a team starting {A, B, C, D, E} with one player swapping E → F after 240 s; expected segment 1 `comp = H_A + H_B + H_C + H_D + H_E`, segment 2 `comp = H_A + H_B + H_C + H_D + H_F` regardless of segment length; `ts_hero` weights E and F by that player's time shares (US4 scenarios 2a, 2b)
- [ ] T071 [P] [US4] Write `tests/property/test_hero_aggregate_props.py` (hypothesis): the incremental `(W_k, Q_k)` update gives the same `H_k` as a full recompute from all player-on-hero entries within 1e-9, for random sequences of updates

### Implementation for User Story 4

- [ ] T072 [US4] Implement `src/owstudy/strength/metrics/hero.py` (research R5): per `(variant, hero_id)` running sums `W_k = Σ t` and `Q_k = Σ t·h`, `H_k = Q_k / W_k`; after each player-on-hero update apply `Q_k += t_old·Δh + t_map·h_new` and `W_k += t_map`; `W_k = 0` → `initial_rating.hero` with `no_history = true`; snapshot `H_pre, W_pre, no_history` for every hero played or banned on the map; `ts_hero_j = Σ_i Σ_k (t_jik / T_ji) H_k` (Formula "Hero-weighted team strength", `post_map`) and `p_ts_hero_a` with `/5`
- [ ] T073 [US4] Implement `src/owstudy/strength/metrics/composition.py` (research R6): per team per segment `comp_j,g = Σ_{i on j} H_{k(i,g)}` from pre-map `H` (no time weighting), `comp_mean = comp/5`, `p_comp_a = expected(comp_mean_a, comp_mean_b)`; map-level `comp_start_a/b`, `p_comp_start_a` from segment 1; `n_no_history_heroes_a/b`
- [ ] T074 [US4] Register hero and composition metrics in `src/owstudy/strength/engine.py` (hero aggregates refresh last in `update`), emit `snapshots_hero.csv` (`map_seq, map_id, patch_id, variant, hero_id, H_pre, W_pre, no_history`), `segment_features.csv` columns `comp_a, comp_b, p_comp_a` (`segment`), and `map_features.csv` columns `comp_start_a/b, p_comp_start_a, n_no_history_heroes_a/b` (`map_start`) and `ts_hero_a/b, p_ts_hero_a` (`post_map`)
- [ ] T075 [P] [US4] Add hero win rate to `src/owstudy/strength/evaluate/naive.py`: cumulative pre-map, time-weighted win rate per hero (and per patch)
- [ ] T076 [US4] Add report sections in `src/owstudy/strength/evaluate/report.py`: hero Elo vs hero win rate overall and per `patch_id` (US4 scenario 3), `p_comp_start_a` vs team Elo, `wl` vs `diff`, `ts_hero` in the post-map section

**Checkpoint**: Meta described independently of players; composition changes exactly at hero swaps.

---

## Phase 8: User Story 5 - Ban impact (Priority: P5)

**Goal**: For each map, how much each team's ban weakens each opposing player and the team, using pre-map ratings and career hero time.

**Independent Test**: `uv run pytest tests/reference -k ban_` passes; the report shows ban loss against map outcome.

### Tests for User Story 5 ⚠️ (write first, must fail)

- [ ] T077 [P] [US5] Create reference fixture `tests/fixtures/reference/ban_never_played/`: ban on a hero an opposing player has never played; expected `loss = 0`, `status = zero_no_history` (US5 scenario 1); plus a player who mostly plays the banned hero with the hand-calculated drop in `p` and team `ban_loss`
- [ ] T078 [P] [US5] Create reference fixture `tests/fixtures/reference/ban_only_hero/`: ban on the only hero a player has ever played; expected `loss` empty, `status = undefined_only_hero`, `ban_undefined_a = 1`, team loss averaged over the defined players only (US5 scenario 2)

### Implementation for User Story 5

- [ ] T079 [US5] Implement `src/owstudy/strength/metrics/ban.py` (research R7): for banning team B with hero `x` and each player `i` on team A, from pre-map `h` and career seconds: `p_with = Σ_k t·h / Σ_k t`, `p_without = Σ_{k≠x} t·h / Σ_{k≠x} t`, `loss = p_with − p_without`; `status ∈ ok | zero_no_history | undefined_only_hero`; team `ban_loss` = mean of defined losses, `ban_undefined` = count of undefined players; both variants; never uses this map's hero times. Teams with `bad_roster` or players with `missing_hero_time` are skipped with `(ban, …)` exclusions
- [ ] T080 [US5] Register the ban metric in `src/owstudy/strength/engine.py` and emit `ban_impact.csv` (`map_id, variant, banning_team_id, affected_team_id, hero_id, player_id, p_with, p_without, loss, status`) and `map_features.csv` columns `ban_loss_a/b, ban_undefined_a/b` (`map_start`)
- [ ] T081 [US5] Add a report section in `src/owstudy/strength/evaluate/report.py`: ban loss difference (`ban_loss_a − ban_loss_b`) binned into quantiles against team A's win rate, and its log loss as a probability feature next to team Elo (US5 scenario 3)

**Checkpoint**: All user stories are independently functional.

---

## Phase 9: Tuning on the validation period (FR-017, cross-cutting)

**Purpose**: Choose `K_team`, `s`, `γ`, `α`, `β` on the validation period only, in stages per metric family, and report sensitivity. The scoring constants `a`, `X_n`, `C_n` and the defender curve stay fixed placeholders until real data exists (FR-017). Needs every metric above.

- [ ] T082 Implement `src/owstudy/strength/evaluate/tune.py` (research R12): before running, count configs across all `tune.stages` and refuse (exit 2) if the total exceeds `tune.max_configs`, and reject any stage grid that names `score.a`, `score.def_curve` or a `modes.*` key (FR-017). Run the stages in order: each stage expands its `grid` with `RunConfig.with_overrides` on top of the base config plus every earlier stage's best values, runs `run_history` for each (optionally in a `ProcessPoolExecutor` with `--jobs`), scores every `p_*` column × variant on **validation-period maps only** (never read test-period labels), and picks the config with the lowest validation log loss on the stage's `target` column and variant. Write `grid_results.csv` (sorted by stage order then config key so output is identical for any `--jobs`), `best_config.yaml` (base config with every stage's best values), and `sensitivity.csv` (per stage, log loss vs each parameter with the others at that stage's best values)
- [ ] T083 Implement the `tune` subcommand in `src/owstudy/strength/cli.py` per contracts/cli.md
- [ ] T084 [P] Write `tests/integration/test_tune_no_test_access.py`: `grid_results.csv` contains only validation-period scores; scrambling every test-period label leaves `grid_results.csv` and `best_config.yaml` byte-identical; `--jobs 1` and `--jobs 4` give identical output; a later stage starts from the earlier stages' best values; a stage grid naming `score.a` or `modes.escort.C` is rejected; a search larger than `tune.max_configs` exits 2
- [ ] T085 Add a report section in `src/owstudy/strength/evaluate/report.py` that, when the run's config came from `tune`, lists the chosen values of `K_team`, `s`, `γ`, `α`, `β` per stage and the sensitivity table, and states that `a`, `X_n`, `C_n` and the defender curve are untuned placeholders (FR-017)

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Performance, edge cases, report completeness, documentation

- [ ] T086 [P] Write `tests/perf/test_perf.py` (marker `perf`): generate a synthetic 1,500-map history in a temp dir with `tests/fixtures/make_sample_season.py` scaled up, and assert `owstudy-strength run` finishes in under 300 s (SC-006; target < 10 s)
- [ ] T087 [P] Write `tests/integration/test_edge_cases.py`: `include_unverified: true` and `false` both run and differ only in the unverified map (Constitution IV); a player rename via aliases keeps one rating history; a game mode missing from config exits 4; a same-date tie between series sharing a team exits 3
- [ ] T088 [P] Write `tests/integration/test_report_completeness.py`: `report.md` on the sample season has a row for every metric (team Elo, player, player-on-hero, composition, hero-weighted, ban) vs team Elo and vs its naive counterpart, for both variants, and for each metric a statement of whether `wl` or `diff` has lower validation log loss (SC-004, SC-008)
- [ ] T089 Review docstrings in `src/owstudy/strength/rating/` and `src/owstudy/strength/metrics/` so every formula cites its `data-model.md` §4 row and thesis equation number, and the documented deviations (time normalized by map duration rather than 48 minutes; no home advantage) are stated in `src/owstudy/strength/rating/marveldoss.py`
- [ ] T090 [P] Add a "Strength metrics" section to `README.md` with the quickstart commands (validate → fit-normalization → run → report → check-leakage → tune) and a pointer to `specs/001-strength-metrics/`
- [ ] T091 Run every command in `specs/001-strength-metrics/quickstart.md` §1–§6 end to end, commit the generated `configs/strength/sample.yaml`, and fix any mismatch between the docs and the behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational
- **US2a (Phase 4)**: Depends on US1 (adds the `diff` variant to `metrics/team.py` and sections to the US1 report)
- **US2 (Phase 5)**: Depends on US1; its `diff` variant depends on US2a (`D̃`). The `wl` variant alone could start after US1
- **US3 (Phase 6)**: Depends on US2 (reuses `rating/marveldoss.py`) and US2a (segment `D̃_g`)
- **US4 (Phase 7)**: Depends on US3 (`H_k` aggregates player-on-hero ratings)
- **US5 (Phase 8)**: Depends on US3 (player-on-hero ratings and career times). Independent of US4
- **Tuning (Phase 9)**: Depends on every story it tunes (all of Phases 3–8)
- **Polish (Phase 10)**: Depends on everything above

### Story completion order

```text
Setup → Foundational → US1 (MVP) → US2a → US2 → US3 ─┬→ US4 ─┐
                                                      └→ US5 ─┴→ Tuning → Polish
```

### Within each story

- Reference fixtures and unit/property tests first; they must fail before implementation
- Rating math (`rating/`) and scoring before metric modules
- Metric snapshot before metric update
- Engine wiring and output columns after the metric module
- Report section last

### Parallel Opportunities

- Setup: T003, T004 in parallel after T001–T002
- Foundational: T007, T012, T013, T014, T015 in parallel; T019 in parallel with T020
- Every reference fixture task within a story is [P] (each is its own directory)
- US1: T025 and T026 in parallel; T030 and T031 in parallel; T034 and T035 in parallel
- US2a: T036–T042 all in parallel; T051 in parallel with T049–T050
- US2: T052–T056 in parallel
- US3: T061–T063 in parallel; T067 in parallel with T064–T066
- US4: T069–T071 in parallel; T075 in parallel with T072–T074
- US4 and US5 can be built at the same time once US3 is done (different metric files; they only meet in `engine.py` and `report.py`, so serialize T074/T080 and T076/T081)
- Polish: T086, T087, T088, T090 in parallel

---

## Parallel Example: User Story 2a

```bash
# All fixtures and tests for US2a together:
Task: "Create reference fixtures diff_control/, diff_push/, diff_flashpoint/ in tests/fixtures/reference/"
Task: "Create reference fixtures diff_escort/ and diff_hybrid/ in tests/fixtures/reference/"
Task: "Create reference fixture diff_clamp/ in tests/fixtures/reference/"
Task: "Create reference fixture segment_diff_sum/ in tests/fixtures/reference/"
Task: "Create reference fixture normalization_sigma/ in tests/fixtures/reference/"
Task: "Write tests/property/test_differential_props.py"
Task: "Write tests/unit/test_differential.py"
```

## Parallel Example: User Story 1

```bash
Task: "Create reference fixture elo_first_map/ in tests/fixtures/reference/"
Task: "Create reference fixture elo_draw/ in tests/fixtures/reference/"
Task: "Create reference fixture elo_5maps_3teams/ in tests/fixtures/reference/"
Task: "Write tests/unit/test_elo.py"
# then
Task: "Implement EloRating in src/owstudy/strength/rating/elo.py"
Task: "Implement s_wl in src/owstudy/strength/scoring/outcome.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup, Phase 2 Foundational
2. Phase 3 US1: team Elo, run, report, leakage check, determinism
3. **STOP and VALIDATE**: `uv run pytest tests/reference -k elo tests/leakage tests/integration`; team-Elo validation log loss < 0.693 on the sample season (SC-003)
4. This is the baseline every later metric must beat (Constitution V)

### Incremental Delivery

1. US1 → baseline report
2. US2a → differentials match hand scores for every mode; team Elo `diff` vs `wl`
3. US2 → player ratings and `m_j` compared to team Elo
4. US3 → player-on-hero ratings compared to player-hero win rate
5. US4 → hero Elo and composition compared to hero win rate, per patch
6. US5 → ban impact against outcomes
7. Tuning → chosen constants and sensitivity, then a final `report --include-test`

Each increment adds report rows without changing earlier output columns, so negative results are recorded as they come (SC-004).

---

## Notes

- [P] tasks touch different files and have no dependency on an incomplete task
- `engine.py`, `report.py`, `timing.py` and `cli.py` are touched by several stories; tasks on them are never [P] with each other
- Only `engine.update` may mutate state. Any metric that needs a value from the current map's result must compute it in `update`, never in `snapshot`
- Commit after each task or logical group; stop at any checkpoint to validate the story on its own
