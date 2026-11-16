---

description: "Task list for Match Data Collection & Verification"
---

# Tasks: Match Data Collection & Verification

**Input**: Design documents from `/specs/002-match-data-collection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli, storage-layout,
config-schema, reference-sources, export), quickstart.md

**Tests**: Included. The constitution requires schema/provenance validation on new data, and the
spec has testable criteria for planted errors (SC-006), audit (SC-004) and determinism (SC-008).
Test tasks come first in each story and should fail until the story is built.

**Organization**: Grouped by user story (US0–US4 from spec.md). Tasks marked **👤 You** need
the researcher (watching video, naming icons, approving).

## At a glance

| Phase | What you get at the end | Tasks | Your steps |
|---|---|---|---|
| 1. Setup | Project file, folders, settings, dependencies | T001–T008 | – |
| 2. Foundations | Settings loader, CSV writer, IDs and aliases, command-line shell | T009–T019 | – |
| 3. Footage inventory (US0) | Today's inventory as one tested command | T020–T025 | – |
| 4. Catalog and links (US1) 🎯 MVP | Every pilot series and map, each linked to a video | T026–T035 | T030, T035 |
| 5. Virtual viewer (US2) | Heroes, kills, objective and attacks read from each video | T036–T063 | T039, T060, T062, T063 |
| 6. Verification (US3) | Every map checked against the references; disagreements reviewed | T064–T081 | T065, T081 |
| 7. Export (US4) | Feature 001's input files plus kill and player × hero tables | T082–T089 | T089 |
| 8. Broadcast test and pilot gate | Decide on broadcast VODs, then whether to expand past the pilot | T090–T093 | T092, T093 |
| 9. Polish | READMEs, safety tests, speed measurements | T094–T098 | – |

### Your steps, in order

1. **T030** Fill in the 2026 patch dates
2. **T035** Approve name aliases and hand-check 30 video links
3. **T039** Confirm platform terms and run the HUD probe on 3 videos
4. **T060** Name the hero icons (about 15 minutes)
5. **T062** Label 6 gold maps and tune until the viewer is accurate
6. **T063** Run extraction on the whole pilot (~18 h of footage; can run overnight)
7. **T065** Check OWTV's terms and run the OWTV probe
8. **T081** Review every discrepancy
9. **T089** Export the pilot and check it
10. **T092** Run the broadcast test and decide on gap fill
11. **T093** Pilot gate: decide whether to expand

## How to read a task

Each task is one checkbox. The **bold headline** says what it does in plain words. The indented
text under it holds the exact files, columns and rules an implementer needs.

- **T###**: task ID, in rough build order
- **[P]**: can be done at the same time as other [P] tasks (different files, nothing unfinished blocking it)
- **[US0]–[US4]**: which part of the feature it belongs to: US0 inventory · US1 catalog and links · US2 virtual viewer · US3 verification · US4 export
- **👤 You**: a step only you can do (watching video, naming icons, approving). Everything else can be built by an implementer
- Paths are relative to the repo. Code lives in `src/owstudy/collect/`, tests in `tests/collect/`

## Shared rules (apply to every task)

- **CSV writer rules** (contracts/storage-layout.md): UTF-8, header row, `,` separator, `\n`
  line endings, "empty cell = missing", rows sorted by the table's listed key, fixed decimals
  ("times 0.01 s, confidences 0.001, progress 0.0001").
- **Immutability** (FR-001): code never opens a file under `data/raw/` for writing except to
  create a new snapshot/run folder, or to append to `data/raw/decisions/decisions.csv`.
- **No network** in `build`, `audit`, `validate`, `export` or any test.
- IDs, thresholds and tolerances come from `configs/collect/*.yaml`, never constants in code.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package, dependencies, configs and folders

- [ ] T001 **Set up the Python project file**
  Create `pyproject.toml` if it doesn't exist yet (feature 001 task T001 creates the same file; if it exists, extend it): package `owstudy` in src layout, `requires-python = ">=3.11"`, base deps pandas, numpy, PyYAML; optional extra `collect = [yt-dlp, av, opencv-python-headless, rapidocr-onnxruntime, onnxruntime, rapidfuzz, requests, openpyxl]`; dev group pytest, hypothesis; console script `owstudy-collect = "owstudy.collect.cli:main"`; pytest marker `network` (skipped by default) and `video` (needs a cached video)
- [ ] T002 **Create the empty package folders**
  Create the package skeleton from plan.md: `src/owstudy/__init__.py` (if missing), `src/owstudy/collect/__init__.py`, `src/owstudy/collect/__main__.py` (calls `cli.main()`), and empty `__init__.py` in `src/owstudy/collect/{io,refs,catalog,viewer,viewer/readers,interpret,verify}/`
- [ ] T003 [P] **Create the test folders and shared test helpers**
  Create the test tree `tests/collect/{unit,integration,viewer}/` and `tests/collect/fixtures/{synthetic_readings,references,planted,hud_frames}/`, plus `tests/collect/conftest.py` with fixtures `fixtures_dir`, `tmp_data_dir` (a temporary copy of the `data/` layout) and `cfg` (default config with `local.yaml` values stubbed)
- [ ] T004 [P] **Write the default settings file**
  Create `configs/collect/default.yaml` with exactly the keys and values in contracts/config-schema.md §default.yaml (scope, video, sampling, recognition, interpret, retrieval, verify incl. `source_priority`, export incl. `analysis_tables: true`, `summary_min_time_s: 60`)
- [ ] T005 [P] **Write the local-settings example and an empty patch list**
  Create `configs/collect/local.example.yaml` (keys `platform_terms_acknowledged: false`, `video_cache_dir`, `user_agent_contact`, `reviewer`) and `configs/collect/patches.yaml` (list of `{patch_id, live_from_utc, note}`; empty list plus a comment until the researcher fills it in T030)
- [ ] T006 **Keep videos and local settings out of git**
  Add to `.gitignore`: `configs/collect/local.yaml`, `data/interim/probes/**/*.png` (probe frame dumps), `*.mp4`, `*.webm`, `*.mkv`, `.cache/`. Video files must never enter the repo (FR-007)
- [ ] T007 **Move the existing reference downloads into dated folders**
  Move the existing reference snapshots into dated folders **without changing their bytes** (`git mv`): `data/raw/reference/liquipedia/*` → `data/raw/reference/liquipedia/2026-11-15/`, `data/raw/reference/spreadsheet/*` → `data/raw/reference/spreadsheet/2026-11-15/`, `data/raw/reference/youtube/obssojourn_videos_dated_2026-11-15.json` → `data/raw/reference/youtube/2026-11-15/obssojourn_videos.json`; write a `snapshot.json` in each (`source`, `retrieved_at: 2026-11-15`, `tool: scripts/inventory (exploratory)`, file list with SHA-256). Update the paths in `data/interim/inventory/README.md`
- [ ] T008 **Install and lock the dependencies**
  Run `uv lock` and `uv sync --extra collect --group dev`; commit `uv.lock`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, deterministic tables, manifests, entities and the CLI shell that every story uses

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T009 **Load and check the settings**
  Implement `src/owstudy/collect/config.py`: frozen dataclasses mirroring contracts/config-schema.md; `load_config(path, local_path=None)` merges `local.yaml` on top, rejects unknown keys (exit 2), validates `verify.source_priority` values are in `{liquipedia, spreadsheet, owtv, video}`, `export.include ∈ {verified, partial, all}`, `video.povs_per_series ∈ {1, 2}`, `video.source_kinds ⊆ {pov, broadcast}`; `extraction_key(cfg, layout_path, icon_lib_dir, ocr_model_files)` = first 8 hex chars of SHA-256 over (extractor version, layout file hash, icon library hash, OCR model hash, `sampling` block) per research R13
- [ ] T010 [P] **Test: settings loading**
  Write `tests/collect/unit/test_config.py`: unknown key rejected; local overrides merged; bad `include` value rejected; `extraction_key` changes when the layout file, an icon file, or `sampling.fps` changes, and doesn't change otherwise
- [ ] T011 **Write CSV tables exactly the same way every time**
  Implement `src/owstudy/collect/io/tables.py`: `write_table(rows_or_df, path, columns, key, decimals: dict[col, n])` enforcing the shared CSV rules and sorting by `key`; `read_table(path, columns)` that rejects unknown/missing columns; `append_rows(path, columns, rows)` for append-only files (never rewrites existing lines; checks the existing header matches)
- [ ] T012 **Record file fingerprints for every run and snapshot**
  Implement `src/owstudy/collect/io/manifest.py`: `write_run_json(folder, run)` with the fields in contracts/storage-layout.md §run.json; `write_folder_manifest(folder)` → `MANIFEST.sha256` over every other file in the folder (sorted); `verify_folder(folder) -> list[str]` returning changed or missing files; `snapshot_json(folder, source, retrieved_at, tool, files)`
- [ ] T013 [P] **Test: tables and fingerprints**
  Write `tests/collect/unit/test_tables_manifest.py`: two writes of the same rows are byte-identical and contain no `\r`; rows come out sorted by key; floats use the configured decimals; `append_rows` keeps earlier lines byte-for-byte and refuses a header mismatch; `verify_folder` reports an edited file
- [ ] T014 **Stable IDs and the name-alias table**
  Implement `src/owstudy/collect/catalog/entities.py`: stable ID helpers (`team:<slug>`, `player:<lp_page_slug>`, `hero:<slug>`, `map:<slug>`; `slug()` = lower-case ASCII, non-alphanumerics → `_`); `normalize_alias(text)` ("case-folded, whitespace collapsed"); `AliasTable.load(path)` reading `data/interim/entities/aliases.csv` (`entity_type,alias,stable_id,valid_from,valid_to,source`) and rejecting overlapping validity ("no overlapping validity for the same alias/type"); `resolve(entity_type, text, on_date, candidates=None) -> (stable_id | None, score)` with exact match first, then `rapidfuzz` ratio limited to `candidates`; `propose(...)` appends to `aliases_proposed.csv` (`alias,entity_type,candidate_stable_id,score,seen_in,seen_at`) and **never** writes `aliases.csv`
- [ ] T015 [P] **Test: IDs and aliases**
  Write `tests/collect/unit/test_entities.py`: exact alias resolves by date (rename case: old and new name → same ID); overlapping validity rejected; a near-miss name returns `None` plus a proposal and is not auto-created (spec edge case); resolution limited to a candidate roster
- [ ] T016 **Seed the hero, map and alias lists**
  Seed `data/interim/entities/`: `heroes.csv` (`hero_id,name`; all heroes in the 2026 pool, `hero_id` slugs matching Liquipedia ban names such as `dva`, `ana`), `maps.csv` (`map_id,name,mode_id` with `mode_id ∈ {control, escort, hybrid, push, flashpoint, clash}`; all 2026 competitive maps), and an empty `aliases.csv` with header. These are hand-curated files that `build` never overwrites
- [ ] T017 **Command-line shell with every command stubbed out**
  Implement `src/owstudy/collect/cli.py`: argparse with global options `--config`, `--scope` (`pilot` | region-stage key | `all`), `--data-dir`, `-v`, and every subcommand in contracts/cli.md registered as a stub; exception → exit code mapping: validation/audit failure `1`, usage/config `2`, retrieval blocked `3`, partial success `4`. `resolve_scope(cfg, scope)` returns the region-stage keys (`pilot` → `scope.pilot`; an unapproved key is a usage error unless `--force-scope`, FR-023)
- [ ] T018 **Polite web client (rate limits and caching)**
  Implement `src/owstudy/collect/refs/ratelimit.py`: `HttpClient(host_min_interval_s, cache_dir, user_agent)` that waits at least the configured interval per host (Liquipedia 2.0 s, OWTV 5.0 s), sends gzip and the User-Agent built from `user_agent_contact` in `local.yaml`, caches responses on disk keyed by URL+params, and raises `RetrievalBlocked` (exit 3) on HTTP 429/403 or a missing contact
- [ ] T019 **Dated snapshots of reference data, with diffs**
  Implement `src/owstudy/collect/refs/snapshot.py`: `new_snapshot(source, date) -> folder` under `data/raw/reference/<source>/<YYYY-MM-DD>/` (refuses if it exists); `latest_snapshot(source, pinned=None)`; `diff_snapshots(old, new, key_columns) -> DataFrame` of added/removed/changed records, written to `data/interim/reports/snapshot_diff_<source>_<date>.csv`

**Checkpoint**: config, tables, manifests, aliases and the CLI shell work; `uv run pytest tests/collect/unit` passes

---

## Phase 3: User Story 0 - Footage inventory (Priority: P0, first task)

**Goal**: The exploratory inventory becomes a tested `owstudy-collect inventory` command with the same results

**Independent Test**: For Korea Stage 1, count series and maps by hand on Liquipedia and compare with the inventory (51 series, 186 maps, 25 with a POV); open 10 listed videos and confirm each is the right series

### Tests for User Story 0

- [ ] T020 [P] [US0] **Test: the inventory reproduces today's numbers**
  Write `tests/collect/integration/test_inventory.py`: running `owstudy-collect inventory --scope all` on the committed 2026-11-15 snapshots reproduces `data/interim/inventory/inventory_summary.csv` row for row (same series, maps, video counts; hours equal to 0.1); the pilot row reads 51 series, 186 maps, 25 series with video, 18.4 h one-POV
- [ ] T021 [P] [US0] **Test: reading ObsSojourn video titles**
  Write `tests/collect/unit/test_title_parse.py`: the title format `[ Player ] Nickname | Team A vs Team B | Event` parses into player, team texts and event text; titles with typos, abbreviations (from sheet `abbr1/abbr2`) and extra separators; non-OWCS titles (e.g., FaceIt Masters) → `not_owcs_main`

### Implementation for User Story 0

- [ ] T022 [P] [US0] **Move the spreadsheet reader into the package (and read bans)**
  Port `scripts/inventory/parse_sheet.py` into `src/owstudy/collect/refs/spreadsheet.py`: `import_sheet(xlsx_path, snapshot_folder)` writes `sheet_series.csv`, `sheet_maps.csv` and **new** `sheet_bans.csv` (`series_key,map_number,team_text,hero_text,locator`) with a `locator` (`sheet!row` / `sheet!cell`) on every record (FR-004, contracts/reference-sources.md); behavior otherwise unchanged
- [ ] T023 [P] [US0] **Move the Liquipedia reader into the package**
  Port `scripts/inventory/parse_lp.py` into `src/owstudy/collect/refs/liquipedia.py` as `parse_batch(json_files) -> (lp_series, lp_maps)` with behavior unchanged and a `locator` column (`page@revid#match<n>`)
- [ ] T024 [US0] **Move video matching and inventory reports into the package**
  Port the matching logic of `scripts/inventory/inventory.py` into `src/owstudy/collect/catalog/link.py` (`parse_title`, `event_hint`, `candidate_series`, `assign`) and the reporting into `src/owstudy/collect/catalog/inventory.py`, replacing the hard-coded `LP_CANON`/alias dict with `AliasTable` (seed those entries into `data/interim/entities/aliases.csv` with `source = manual`) and keeping outputs `inventory_summary.csv`, `series_inventory.csv`, `series_missing_video.csv`, `pilot_korea_stage1_series.csv`, `gap_coverage.csv`, `sheet_vs_liquipedia.csv`, `video_matches.csv` with their current columns
- [ ] T025 [US0] **Add the `inventory` command and delete the old scripts**
  Wire `owstudy-collect inventory` in `src/owstudy/collect/cli.py` to read the latest snapshots and write `data/interim/inventory/`; once T020 passes, delete `scripts/inventory/` and update the "Regenerate" section of `data/interim/inventory/README.md` to the single command

**Checkpoint**: Inventory reproducible with one command; old scripts removed

---

## Phase 4: User Story 1 - Build the match catalog and link replays (Priority: P1) 🎯 MVP

**Goal**: One catalog of every series and map in scope with stable IDs, lineups, patches and dates, each map linked to a POV video (or marked `no_replay`)

**Independent Test**: For Korea Stage 1, compare `catalog/series.csv` and `maps.csv` with Liquipedia by hand; open 30 random links from `video_links.csv` and confirm each is the right series (SC-001 link check)

### Tests for User Story 1

- [ ] T026 [P] [US1] **Small fake reference data for the catalog tests**
  Create fixture `tests/collect/fixtures/references/`: a tiny Liquipedia snapshot (4 series, 12 maps incl. one Clash map, one forfeit, one pair of teams meeting twice in the window), a matching spreadsheet snapshot (one series present only in the sheet), and a video list (one POV per series, one duplicate re-upload, one unmatched title)
- [ ] T027 [P] [US1] **Test: building the catalog and linking videos**
  Write `tests/collect/integration/test_catalog.py` on that fixture: each series appears once with `sources` listing both snapshots (US1 scenario 1); the sheet-only series is flagged; Clash map gets `status = clash_excluded` and the forfeit `status = forfeit`; repeated pairing resolved by phase words with `link_confidence = medium`; duplicate upload gets `role = duplicate`; unmatched title gets `status = unmatched` and no guess (scenario 5); series without a video keep their maps (scenario 4); `start_utc` is the Liquipedia local time converted from its `tz`; `patch_id` is the patch with the latest `live_from_utc ≤ start_utc`

### Implementation for User Story 1

- [ ] T028 [US1] **Download Liquipedia pages and read team lineups**
  Extend `src/owstudy/collect/refs/liquipedia.py`: `fetch(event_pages, client)` using MediaWiki `action=query&prop=revisions&rvprop=content|ids` (never `action=parse`, research R9), saving each raw response under `<snapshot>/responses/` and skipping pages whose revision ID is already cached; parse **lineups** per series into `lp_lineups.csv` (`series_key,team_text,player_page,player_display,source_kind ∈ {match, event_roster},locator`), falling back to the team's event roster when the match has none
- [ ] T029 [US1] **List ObsSojourn's videos (no downloading)**
  Implement `src/owstudy/collect/refs/youtube_list.py`: `list_channel(channel_url) -> snapshot` using `yt-dlp` flat playlist (no video download), writing `obssojourn_videos.json` (`video_id,title,duration_s,upload_date`) to a new `youtube/<date>/` snapshot
- [ ] T030 [US1] **👤 You: fill in the 2026 patch dates**
  fill `configs/collect/patches.yaml` with every 2026 patch's `patch_id` and `live_from_utc` from the official patch notes
- [ ] T031 [US1] **Build the catalog of series, maps and lineups**
  Implement `src/owstudy/collect/catalog/build.py`: from the latest Liquipedia + spreadsheet snapshots write `data/interim/catalog/series.csv` (`series_id,region,stage,phase,best_of,start_utc,local_date,tz,team_a_id,team_b_id,score_a,score_b,status,sources,in_pilot`; `status ∈ {played, forfeit, walkover}`), `maps.csv` (`map_id,series_id,map_number,map_ref,mode_id,winner,patch_id,status`; `map_id = <series_id>-m<n>`; `winner ∈ {a, b, draw}`; `status ∈ {played, clash_excluded, forfeit}`) and `lineups.csv` (`series_id,team_id,player_id,source`); seed team/player aliases from Liquipedia page names and sheet abbreviations into `aliases_proposed.csv` for the researcher to accept; `series_id` = slug of the Liquipedia match key, so it stays stable across snapshots
- [ ] T032 [US1] **Link each video to its series**
  Implement linking in `src/owstudy/collect/catalog/link.py`: `link_videos(catalog, videos, aliases, cfg)` → `video_links.csv` (`video_id,series_id,status,link_confidence,role,pov_player_id,pov_team_id,confirmed,note`; `status ∈ {linked, unmatched, not_owcs_2026, duplicate}`; `link_confidence ∈ {high, medium, low}`; `role ∈ {primary, cross_check, unused, duplicate}`); candidate = same teams, matching event, series date ≤ upload date, nearest first, ties broken by phase words (research R7); primary POV per series = longest video, ties by `video_id`; with `povs_per_series: 2`, the longest video from the other team becomes `cross_check`; duplicates = same series + same player + |duration difference| < 60 s; `confirmed` starts `false`
- [ ] T033 [US1] **Hook up the fetch, import and catalog commands**
  Wire `owstudy-collect refs fetch liquipedia`, `refs import-sheet`, `videos list` and `catalog build` in `src/owstudy/collect/cli.py`; `refs fetch` prints the snapshot diff summary from T019
- [ ] T034 [US1] **Add the `status` command (coverage per region-stage)**
  Implement `owstudy-collect status` in `src/owstudy/collect/cli.py` (and `src/owstudy/collect/catalog/inventory.py`): per region-stage — series, maps in scope, maps with replay, `no_replay`, low-confidence links waiting for review
- [ ] T035 [US1] **👤 You: approve name aliases and hand-check 30 video links**
  run `catalog build --scope pilot`, review `aliases_proposed.csv` and copy accepted rows into `data/interim/entities/aliases.csv`, then do the 30-link hand check from quickstart §2 and note the result in `data/interim/reports/link_check_pilot.md`

**Checkpoint**: Pilot catalog with links. Map winners are already enough for team Elo (feature 001 US1)

---

## Phase 5: User Story 2 - Virtual viewer extracts map events from a replay (Priority: P2)

**Goal**: Each linked POV video is processed unattended into immutable readings, then interpreted into hero intervals, kills, objective progress, attacks, gaps and segments

**Independent Test**: On the hand-labeled gold set (6 maps, every mode), `gold score` meets SC-002: 100% winners/map numbers/modes/bans; ≥98% heroes per segment; ≥95% swaps within 3 s; ≥95% maps with team kills within ±1

### Probe first (research R5)

- [ ] T036 [US2] **Download a video (only once platform terms are acknowledged)**
  Implement `src/owstudy/collect/viewer/download.py`: `download(video_id, cfg) -> path` with `yt-dlp` Python API, format string from `video.format`, `rate_limit`, random sleep in `sleep_between_downloads_s`, resume on failure, refuses (exit 3) unless `platform_terms_acknowledged: true`; returns SHA-256, `format_id`, resolution; keeps at most `cache_max_videos` files in `video_cache_dir` (outside the repo); `delete(video_id)`
- [ ] T037 [US2] **Pull frames from a video at a fixed rate**
  Implement `src/owstudy/collect/viewer/frames.py`: `sample_frames(path, fps) -> Iterator[(pts_s, ndarray)]` with PyAV, single-threaded decode, picking the first frame whose PTS crosses each `1/fps` mark (research R3); identical output on repeated calls
- [ ] T038 [US2] **HUD probe: save sample frames and a checklist**
  Implement `src/owstudy/collect/viewer/probe.py` and `hud probe`: for each video, sample one frame every 30 s, save full frames and the crops of every region in a draft layout to `data/interim/probes/hud/<video_id>/`, and write `data/interim/probes/hud/checklist.md` with one line per R5 item (10 portraits, 10 names, both teams in kill feed, game clock, attack clock, objective widget, ban display, map number on banner, mode from objective widget)
- [ ] T039 [US2] **👤 You: confirm platform terms and run the HUD probe**
  confirm platform terms allow downloading for personal research, set `platform_terms_acknowledged: true` in `configs/collect/local.yaml`, run `hud probe` on 3 pilot videos (one Control, one Escort/Hybrid, one Push/Flashpoint) and answer the checklist. If any item fails, apply the research R5 fallback (bans single-source; `povs_per_series: 2`; or stop and revisit with the kill-feed issue) and record the choice in research.md R5
- [ ] T040 [US2] **Write the POV HUD layout from the probe frames**
  Create `configs/collect/hud/owcs2026_pov_v1.yaml` and anchor templates `configs/collect/hud/anchors/*.png` from the probe frames, with every region in contracts/config-schema.md §hud (normalized 0–1 boxes), and commit 2–3 crops per region type as test fixtures in `tests/collect/fixtures/hud_frames/` (PNG crops only, no video)

### Tests for User Story 2

- [ ] T041 [P] [US2] **Test: compressing per-frame readings**
  Write `tests/collect/unit/test_rle.py` (hypothesis): encoding then expanding a per-frame value sequence returns it exactly; a frame below `low_conf_threshold` always starts its own run; `conf_min`/`conf_mean`/`frames` are correct
- [ ] T042 [P] [US2] **Test: reading heroes, names, clocks and the kill feed from crops**
  Write `tests/collect/viewer/test_readers.py` on `tests/collect/fixtures/hud_frames/`: each committed portrait crop identifies the right hero with margin ≥ `icon_min_margin`; clock crops read the right `mm:ss`; name crops resolve to the right player through a fixture alias table; a kill-feed crop yields killer/victim heroes, side and `env_or_self`; frames without the HUD fail the anchor check
- [ ] T043 [P] [US2] **Fake readings for the interpretation tests**
  Create fixture `tests/collect/fixtures/synthetic_readings/` (hand-written readings for 3 maps: Control, Hybrid, Push) with a hero swap, a 6 s spawn swap, a kill-feed entry seen for 10 frames, an environmental death, a no-HUD gap mid-map, a replay where the clock rewinds, a remade map (two spans with the same name, first without a result) and the expected interpreted outputs in `expected/`
- [ ] T044 [P] [US2] **Test: turning readings into swaps, kills, attacks and gaps**
  Write `tests/collect/unit/test_interpret.py` on that fixture: swap starts a new segment at the first frame of the new run and both segments list the right hero (US2 scenario 1); the 10-frame kill-feed entry becomes one kill with game time, killer, victim, heroes and video time (scenario 2); each Hybrid attack has attacking team, progress, attack clock and time remaining incl. banked time (scenario 3); the gap is recorded as a gap, no events are invented in it, and the map gets `kills_incomplete` (scenario 4); low-confidence readings are flagged `low_conf` (scenario 5); the 6 s swap is kept and flagged `short_segment`; the rewound-clock stretch is a `replay` gap and its kill is not counted; the repeated kill is flagged `possible_replay`; the abandoned span is `excluded_remake`
- [ ] T045 [P] [US2] **Test: segments and objective scoring**
  Write `tests/collect/unit/test_segments_objective.py`: segments tile `[0, map_end)` with no gaps; per-segment kills per team = opponent deaths in `[start, end)` incl. environmental; objective gains per mode follow the data-model §2.3 table (Control: "mean over rounds played of team x's final capture percent"; Push: "furthest robot distance ÷ map's full push distance"; Flashpoint: "(points captured + partial progress on the last contested point) ÷ points played"; Escort/Hybrid: attacker progress) and segment gains sum to the map total

### Implementation for User Story 2

- [ ] T046 [P] [US2] **Load a HUD layout and detect it in a frame**
  Implement `src/owstudy/collect/viewer/layout.py`: load and validate a HUD layout YAML (all boxes within [0,1]), `detect_layout(frame, layouts) -> layout_id | None` by anchor template scores ≥ `hud_anchor_min_score`, `crop(frame, box)`
- [ ] T047 [P] [US2] **Hero icon library and matching**
  Implement `src/owstudy/collect/viewer/icons.py`: icon library at `data/interim/entities/icons/<hero_id>/*.png`; `match(crop) -> (hero_id, conf)` by normalized cross-correlation on a fixed-size crop, with confidence from the best-vs-second margin; `harvest(videos)` clusters portrait crops into `data/interim/probes/icons/cluster_<n>/`; `label()` prompts the researcher to name each cluster and copies the chosen crops into the library
- [ ] T048 [P] [US2] **Text reading (OCR)**
  Implement `src/owstudy/collect/viewer/ocr.py`: a RapidOCR wrapper with `onnxruntime` thread count from `recognition.ocr_threads`, `read(crop) -> (text, conf)`, and `model_files()` for the extraction key
- [ ] T049 [US2] **A reader for each HUD element**
  Implement readers in `src/owstudy/collect/viewer/readers/`: `hero.py` (10 portrait slots `L1..L5`, `R1..R5`), `names.py` (OCR name plates, raw text kept), `clock.py` (game and attack clock → seconds), `objective.py` (per-mode widget → progress 0–1 or point counts, `method = bar_px`), `banner.py` (map number "MAP n" at map start; mode from the objective widget style), `bans.py` (ban display, if the probe found one), `result.py` (final result screen), `killfeed.py` (rows → killer icon/name, ability icon, victim icon/name, side by `team_colors`, `env_or_self`; tracked across frames into one event with first/last seen); each returns `(value, conf, method)`
- [ ] T050 [US2] **Compress per-frame readings into runs**
  Implement `src/owstudy/collect/viewer/rle.py`: turn per-frame reader outputs into run-length rows (`reading_type ∈ {map_info, team_name, player_name, hero, kill, objective, game_clock, attack_clock, round_state, ban, result, gap, hud_layout}`) with `ts_start, ts_end, clock_start, clock_end, value, conf_min, conf_mean, frames, method`; no-HUD stretches become `gap` rows with `value = no_hud`
- [ ] T051 [US2] **Save one video's readings as a locked run**
  Implement `src/owstudy/collect/viewer/extract.py`: `extract_video(cfg, video_id)` → `data/raw/observations/<video_id>/<extraction_key>/` with `readings.csv`, `kills.csv` (columns per contracts/storage-layout.md), `run.json` and `MANIFEST.sha256`; refuses if the folder already holds an `ok` run; run date only in `run.json`, never in rows (research R13); writes into a temp folder and renames on success so a crash leaves no partial run
- [ ] T052 [US2] **Batch pipeline: download, read, delete (resumable)**
  Implement the pipeline in `src/owstudy/collect/viewer/extract.py` and `data/interim/runs/state.csv` (`video_id,extraction_key,state,attempts,last_error,updated_at`; `state ∈ {pending, downloaded, extracted, deleted, failed}`, transitions per data-model §3.1): `extract` processes primary (and `cross_check` if configured) videos in scope, downloads the next video while processing the current one, skips `(video_id, extraction_key)` already `extracted` unless `--force` (FR-012), deletes the video after success unless `--keep-video` (FR-007c), and returns exit 4 if any video failed
- [ ] T053 [US2] **Determinism check (same video gives the same output)**
  Implement `--check-determinism` in `src/owstudy/collect/viewer/extract.py`: run recognition twice on the cached file into two temp folders, compare `readings.csv` and `kills.csv` byte for byte, report the first differing row, and keep the video until both passes finish (FR-013)
- [ ] T054 [P] [US2] **Find each map in the video and line it up with the catalog**
  Implement `src/owstudy/collect/interpret/spans.py`: map spans from banner/HUD/result readings and alignment to catalog maps by map number with a mode check (research R8; map names come from the catalog, not the video) → `data/interim/catalog/map_spans.csv` (`video_id,map_id,ts_start,ts_end,status`; `status ∈ {ok, excluded_remake, unaligned}`); set `confirmed = true` in `video_links.csv` when HUD team names match and ≥8 of 10 player names resolve to the series lineups, otherwise emit a `link` issue for US3
- [ ] T055 [P] [US2] **Hero swaps, gaps and replay rejection**
  Implement `src/owstudy/collect/interpret/heroes.py` (HeroInterval: swap after `swap_min_frames` frames at confidence ≥ threshold, `short_segment` below `short_segment_s`) and `src/owstudy/collect/interpret/gaps.py` (no-HUD gaps; clock-must-advance replay rejection → `replay` gaps; `kills_incomplete` on maps with any gap)
- [ ] T056 [P] [US2] **Kill events**
  Implement `src/owstudy/collect/interpret/kills.py`: KillEvent from kill readings (game time = clock at `first_seen`, players resolved via aliases limited to the series lineups, `possible_replay` when killer/victim/heroes repeat within `replay_repeat_window_s`, `env_or_self` with empty killer, kills inside a `replay` gap dropped)
- [ ] T057 [P] [US2] **Objective progress and attacks**
  Implement `src/owstudy/collect/interpret/objective.py` (ObjectiveSample normalized per mode, data-model §2.3) and `src/owstudy/collect/interpret/attacks.py` (AttackRecord: `attack_order, attacking_team_id, obj_progress ∈ [0,1], attack_clock_s > 0 incl. banked time, 0 ≤ time_remaining_s ≤ attack_clock_s`)
- [ ] T058 [US2] **Split maps into segments and write the event tables**
  Implement `src/owstudy/collect/interpret/segments.py`: segment boundaries = union of hero interval edges and round/attack boundaries; per-segment kills per team and objective gain; segments tile the map; write `data/interim/events/{hero_intervals,kills,objective,attacks,gaps,results}.csv` (FR-010)
- [ ] T059 [US2] **Hook up the probe, icon and extract commands**
  Wire `hud probe`, `icons harvest`, `icons label` and `extract` in `src/owstudy/collect/cli.py`, and add the interpret step to `build` (interpret only, until US3 adds reconcile)
- [ ] T060 [US2] **👤 You: name the hero icons**
  run `icons harvest` on 2–3 pilot videos and `icons label` (~45 heroes, about 15 minutes)
- [ ] T061 [US2] **Gold-set labeling and scoring commands**
  Implement `src/owstudy/collect/verify/gold.py` and wire `gold init` / `gold score`: `gold init <map_id>` writes `data/raw/gold/<map_id>/labels.csv` (`map_id,field,subject,value,ts_video,labeled_by,labeled_at`; `field ∈ {winner, map_number, mode, ban, hero_segment, swap_time, team_kills, attack}`) prefilled with players and expected segments but empty values, refusing if labels already exist; `gold score` writes `data/interim/reports/gold_accuracy.csv` (field, n, correct, accuracy, SC-002 threshold, pass)
- [ ] T062 [US2] **👤 You: label 6 gold maps and tune until the viewer is accurate**
  pick 6 pilot gold maps (one per mode, plus a second Control; different series and teams), run `extract --videos <ids> --keep-video --check-determinism`, fill in the labels while watching, run `gold score`; tune the layout and interpretation thresholds in `configs/collect/` until SC-002 passes, then let the videos be deleted
- [ ] T063 [US2] **👤 You: run extraction on the whole pilot**
  run `extract --scope pilot` (~18 h of footage, resumable); interrupt once and rerun to confirm finished videos are skipped (FR-012)

**Checkpoint**: Pilot readings and interpreted events exist; viewer accuracy measured on the gold set

---

## Phase 6: User Story 3 - Verify against the reference sources (Priority: P3)

**Goal**: Every map is compared field by field with the references, disagreements become reviewable discrepancies, decisions are re-applied on rebuild, and each map gets a verification status

**Independent Test**: Plant known errors (wrong winner, wrong player, missing kill, wrong ban, wrong date) in a copy of a few reconciled maps; every one is caught and logged with both values (SC-006). Works entirely on fixtures, so it doesn't depend on US2 having processed real video

### OWTV probe (research R10)

- [ ] T064 [US3] **OWTV probe command**
  Implement `refs probe-owtv` in `src/owstudy/collect/refs/owtv.py` (probe mode only): for given series, fetch the OWTV pages through `HttpClient` (≥5 s interval), save them to `data/interim/probes/owtv/`, and print which stats appear and at what level
- [ ] T065 [US3] **👤 You: check OWTV's terms and run the OWTV probe**
  check OWTV's terms, run the probe on 3 pilot series, and write the real field list, granularity (per map or per series) and access method into contracts/reference-sources.md §OWTV and research.md R10
- [ ] T066 [US3] **OWTV reader, built from the probe result**
  Implement the OWTV adapter in `src/owstudy/collect/refs/owtv.py` per the probe result: `fetch(series, client) -> snapshot` writing `owtv_map_player_stats.csv` (`series_key_text,map_number,player_text,team_text,deaths,eliminations,final_blows,locator`; `map_number` empty if per series) to `data/raw/reference/owtv/<date>/`; wire `refs fetch owtv`

### Tests for User Story 3

- [ ] T067 [P] [US3] **Fake maps with planted errors**
  Create fixture `tests/collect/fixtures/planted/`: interim events + reference snapshots for 5 maps where everything agrees, and a planting script spec listing one error each: wrong winner, wrong player (not on the Liquipedia lineup), a missing kill, wrong ban, wrong date
- [ ] T068 [P] [US3] **Test: comparing sources**
  Write `tests/collect/unit/test_compare.py`: outcomes per FR-017 (`agree`, `agree_within_tolerance`, `disagree`, `single_source`); tolerances "exact for names, dates (after time-zone normalization), winners, bans and rosters; ±1 for a team's kill total per map; exact for per-player deaths"; one-day time-zone difference → `agree_within_tolerance` with a note; team kills compared as opponent deaths, never eliminations; a field only one source has → `single_source` (US3 scenario 5); per-series OWTV data compared at series level
- [ ] T069 [P] [US3] **Test: discrepancies, decisions and map status**
  Write `tests/collect/unit/test_discrepancies_status.py`: discrepancy ID is stable across rebuilds (hash of map_id, field, subject); the provisional value follows FR-021 priority and is marked `provisional`; a decision applies on rebuild and the raw reading is unchanged (scenario 4); a decision whose `seen_values` no longer match makes the discrepancy `stale`; nothing closes without a decision (FR-020); status order per data-model §3.3 (`conflict` → `unverified` → `partial` → `verified`); a low-confidence required field blocks `verified`; `kills_incomplete` without scoreboard agreement gives `partial`
- [ ] T070 [P] [US3] **Test: every planted error is caught**
  Write `tests/collect/integration/test_planted_errors.py`: `owstudy-collect plant-errors` on the fixture catches all 5 planted errors with both values logged and the right `kind` (SC-006); the all-agree maps come out `verified` (scenario 1)
- [ ] T071 [P] [US3] **Test: audit and repeatable builds**
  Write `tests/collect/integration/test_audit.py`: after `build`, `audit` exits 0; editing one reconciled value by hand makes `audit` exit 1 naming it (SC-004); `build` twice gives byte-identical `data/interim/reconciled/` and `verify/` (SC-008)

### Implementation for User Story 3

- [ ] T072 [US3] **Combine video and references into one record per map**
  Implement `src/owstudy/collect/reconcile.py`: for each catalog map, assemble every 001 field (maps, segments, segment heroes, bans, attacks) from interim events and the latest reference snapshots, tagging each value with `value_source ∈ {video, liquipedia, spreadsheet, owtv, decision:<id>}`, `provisional` and a `raw_ref` (`obs:<video>/<key>#<type>:<slot>@<ts>` or `ref:<source>/<snapshot>#<locator>`); write `data/interim/reconciled/{maps,segments,segment_heroes,bans,attacks,field_sources}.csv`
- [ ] T073 [US3] **Compare each field across sources**
  Implement `src/owstudy/collect/verify/compare.py`: one Comparison per map × FR-016 field × subject (series date; teams; each team's roster per map vs series lineup; map names and order (references only; the video contributes map number and mode); map winner and series score; bans; game mode; per-player deaths and team kill totals; per-player final blows where given) with tolerances from `verify.*`; write `data/interim/verify/comparisons.csv` (`map_id,series_id,field,subject,video,liquipedia,spreadsheet,owtv,outcome,tolerance,note`)
- [ ] T074 [US3] **Turn disagreements into discrepancies**
  Implement `src/owstudy/collect/verify/discrepancies.py`: every `disagree`, every `link` issue from T054, every `map_order` mismatch and every low-confidence required value → Discrepancy (`discrepancy_id,map_id,kind,field,subject,values_json,provisional_value,provisional_source,ts_video_from,ts_video_to,video_id,status,decision_id`; `kind ∈ {roster, scoreboard, winner, ban, date, map_order, link, low_confidence, mode}`; `status ∈ {open, resolved, stale}`); `ts_video_from/to` = the span of the affected segment(s) or map
- [ ] T075 [US3] **Record your decisions and re-apply them on rebuild**
  Implement `src/owstudy/collect/verify/decisions.py`: `append_decision(...)` to `data/raw/decisions/decisions.csv` (`decision_id,discrepancy_id,field,seen_values_json,action,value,reason,decided_by,decided_at`; `action ∈ {accept_source:<name>, correct}`) via `append_rows`; `apply(discrepancies, decisions)` uses the latest decision per discrepancy only if `seen_values` match the current values, otherwise marks `stale`
- [ ] T076 [US3] **Give each map a verification status**
  Implement `src/owstudy/collect/verify/status.py`: map status per data-model §3.3 written into `reconciled/maps.csv` as `verification_status ∈ {verified, partial, conflict, unverified}`
- [ ] T077 [US3] **Add the `review` command for settling discrepancies**
  Implement `src/owstudy/collect/verify/review.py` and `review`: iterate open/stale discrepancies (filter by `--kind`, `--map`), show field, every source's value, confidence and a `https://youtu.be/<video_id>?t=<ts_video_from>` link; keys `1..n` accept source n, `c` correct (prompt for value), `s` skip; then prompt for a reason (required) and record `decided_by` from `local.yaml` `reviewer`; rebuild the affected map after each decision
- [ ] T078 [US3] **Add the `audit` and `validate` commands**
  Implement `src/owstudy/collect/verify/audit.py` (`audit`: every value in `field_sources.csv` equals its raw reading/record value or is covered by an applied decision; also runs `verify_folder` on every observation run and snapshot) and `validate` (data-model §4 checks); both exit 1 listing every problem
- [ ] T079 [US3] **Add the `plant-errors` self-test command**
  Implement `plant-errors` in `src/owstudy/collect/verify/audit.py`: copy the reconciled inputs of N maps into `--out`, plant the 5 error types, run build + compare on the copy, and report caught/missed; never touches `data/`
- [ ] T080 [US3] **Full `build`: interpret, reconcile, compare, set status**
  Extend `build` in `src/owstudy/collect/cli.py` to interpret → reconcile → compare → discrepancies → apply decisions → status, all without network
- [ ] T081 [US3] **👤 You: fetch references, build, and review every discrepancy**
  run `refs fetch liquipedia` and `refs fetch owtv` for the pilot, `build`, then `review` all open discrepancies, timing a sample to check SC-009 (< 2 min each); confirm `audit` exits 0 and `status` shows ≥85% of processed maps `verified` without a decision (SC-005)

**Checkpoint**: Pilot maps have verification statuses; every disagreement is logged and reviewed

---

## Phase 7: User Story 4 - Export the verified dataset (Priority: P4)

**Goal**: Feature 001 input, the analysis tables (kill events, player × hero), coverage summary and provenance, all in one reproducible export

**Independent Test**: Export and run feature 001's `owstudy-strength validate` on `input/` with 0 errors (SC-007); export twice and diff (SC-008)

### Tests for User Story 4

- [ ] T082 [P] [US4] **Test: the export matches feature 001's input format**
  Write `tests/collect/integration/test_export.py` on the planted-error fixture after decisions: `input/` has exactly the files and columns of feature 001's contracts/input-schema.md; `verification` is `verified` only for `verified` maps; `--include verified` drops the others and lists them in `summary/excluded_maps.csv` with `reason ∈ {no_replay, forfeit, clash, remake_only, open_conflict, unverified_excluded, not_processed}` (FR-025); every catalog map is either exported or excluded; every exported map has a `provenance/map_provenance.csv` row with video, span, extraction key and confirming sources (SC-003); two exports are byte-identical except `manifest.json` `created_at`; if `owstudy.strength` is importable, its validator returns 0 errors on `input/`
- [ ] T083 [P] [US4] **Test: kill-event and player × hero tables**
  Write `tests/collect/unit/test_analysis_tables.py` on a hand-computed 2-map fixture (one Control, one Hybrid, with a mid-map swap, an environmental death and a gap): `kill_events.csv` rows, `kill_no` order and `segment_no`; `player_hero_map.csv` values for the swapping player on each hero (`time_s`, `time_share`, `team_kills`, `team_deaths`, `own_kills`, `own_deaths`, `obj_for`, `obj_against`, `attack_time_s`, `defense_time_s`, `defense_clock_used`, `incomplete_s`) equal hand values; `player_hero_summary.csv` per-mode and `all` rows (objective empty on `all`), per-10-minute rates, rates empty when `time_s < summary_min_time_s`; each consistency check in contracts/export.md fails on a deliberately broken copy

### Implementation for User Story 4

- [ ] T084 [US4] **Export feature 001's input files**
  Implement `src/owstudy/collect/export.py`: `export(cfg, include, out_dir)` writing `data/processed/collection/<YYYYMMDD>-<hash>/input/` from `reconciled/` with the field mapping in contracts/export.md (`date` = event-local date, `series_start` = UTC, `source_ref = yt:<primary video>@<span start>`, `kills_*` empty if `kills_incomplete` and unresolved, `obj_*` only for symmetric modes, `entities/aliases.csv` with team/player/hero aliases only)
- [ ] T085 [US4] **Kill-event and player × hero tables**
  Implement `src/owstudy/collect/analysis.py`: `kill_events.csv` (key `(map_id, kill_no)`; `kill_no` in game-time order, ties by video time then victim slot; `flags ⊆ {low_conf, possible_replay, name_unresolved}` joined by `;`), `player_hero_map.csv` (key `(map_id, player_id, hero_id)`; shared-credit team kills/objective over that player's segments on that hero, Escort/Hybrid split by attacking/defending), `player_hero_summary.csv` (key `(player_id, hero_id, mode_id)` plus `mode_id = all`; totals, `*_per10` rates, empty below `summary_min_time_s`, objective columns empty on `all`); all with the columns in contracts/export.md §Analysis tables; skipped when `analysis_tables: false` or `--no-analysis-tables`
- [ ] T086 [US4] **Consistency checks for the analysis tables**
  Implement the analysis-table consistency checks in `src/owstudy/collect/analysis.py` (kill events per team = map kills; Σ `time_s` per player = map length; `team_kills` = kill events in that player's hero segments; Σ `own_kills` + opponent environmental deaths = team kills; summary = sum of per-map rows); `export` exits 1 if any fail
- [ ] T087 [US4] **Coverage, quality and provenance reports**
  Implement `summary/coverage.csv` (per region-stage: maps in scope, with replay, processed, verified, open discrepancies by kind, excluded by reason), `summary/quality.csv` (gold accuracy, link-check result, discrepancy counts) and `summary/excluded_maps.csv`, plus `provenance/map_provenance.csv`, `provenance/field_sources.csv` and `manifest.json` (hashes of snapshots, reading keys, decisions file, configs; tool version; include setting; `created_at`) in `src/owstudy/collect/export.py`
- [ ] T088 [US4] **Hook up `export` and run feature 001's validator**
  Wire `export` in `src/owstudy/collect/cli.py`; after writing, call `owstudy.strength.io.validate.load_inputs` on `input/` when feature 001 is installed and report its errors (SC-007), otherwise print that the check was skipped
- [ ] T089 [US4] **👤 You: export the pilot and check it**
  run `export --scope pilot --include verified`, run `owstudy-strength validate` on it, export again and diff, and spot-check one gold map's swapping player in `player_hero_map.csv` against the hand labels (quickstart §8)

**Checkpoint**: Pilot dataset handed to feature 001, with analysis tables and coverage summary

---

## Phase 8: Broadcast test and pilot gate (FR-007b, FR-023, cross-cutting)

**Purpose**: Decide whether broadcast VODs fill the 26 pilot series with no POV (research R17), then decide on expansion

- [ ] T090 **Write the broadcast HUD layout**
  Create `configs/collect/hud/owcs2026_broadcast_v1.yaml` from probe frames of a Korea Stage 1 broadcast VOD (`hud probe` on a Liquipedia VOD link), including anchors that tell gameplay HUD from caster desk/ads
- [ ] T091 **Add the `broadcast-test` command**
  Implement `broadcast-test` in `src/owstudy/collect/cli.py` (logic in `src/owstudy/collect/viewer/extract.py`): extract the broadcast VOD of each given series (video kind `broadcast`, sliced from the Liquipedia `?t=` offset), align its maps with the POV readings of the same series, and write `data/interim/reports/broadcast_test.md` with replayed kills accepted (must be 0), downtime seconds skipped vs. not, and per-field agreement against the POV using SC-002 thresholds
- [ ] T092 **👤 You: run the broadcast test and decide on gap fill**
  run `broadcast-test` on 3 pilot series with both sources; if it passes and you approve, add `broadcast` to `video.source_kinds`, link the 26 no-POV series to their broadcast VODs, extract, build and export again; if it fails, decide whether SC-001 is restated for the pilot (spec change) and record the decision in spec.md
- [ ] T093 **👤 You: pilot gate (decide whether to expand)**
  pilot gate. Check SC-001 (≥95% of maps linked; 30-link hand check clean), SC-002 (gold accuracy) and SC-007 (001 validation) in `summary/quality.csv`; if all pass and you approve, add the next region-stage to `scope.approved` in `configs/collect/default.yaml` (one at a time, FR-023)

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T094 [P] **READMEs for the data folders**
  Write `data/raw/README.md`, `data/interim/README.md` and `data/processed/collection/README.md` describing each folder's tables, which files are hand-curated (`aliases.csv`, `icons/`, `decisions.csv`, gold labels), what may be deleted and rebuilt, and the one command that rebuilds everything (`owstudy-collect build && owstudy-collect export`) (Constitution VI)
- [ ] T095 [P] **Test: build, audit and export never change raw data or use the network**
  Add `tests/collect/integration/test_no_raw_writes.py`: run `build`, `audit`, `export` with `data/raw/` made read-only (or with a write-tracking shim) and confirm nothing under `data/raw/` changes and no network call is made
- [ ] T096 [P] **Measure extraction speed**
  Add a `--measure` flag to `extract` that writes per-video timings (download, decode, recognition) to `data/interim/reports/throughput.csv`, and replace the estimates in research.md R12 with measured pilot numbers
- [ ] T097 **Walk through the quickstart end to end**
  Run every quickstart.md section end to end on the pilot and fix any mismatch between the docs and the commands
- [ ] T098 **Add a data collection section to the main README**
  Update the top-level `README.md` with a short "Data collection" section linking to `specs/002-match-data-collection/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs Setup; **blocks every story**
- **US0 (Phase 3)**: needs Foundational
- **US1 (Phase 4)**: needs US0's ported parsers (T022–T024)
- **US2 (Phase 5)**: needs US1's catalog and links for real runs. Its unit tests and interpretation code (T041–T045, T054–T058) only need Foundational and fixtures
- **US3 (Phase 6)**: code and tests run on fixtures after Foundational; real pilot review (T081) needs US2's pilot extraction (T063)
- **US4 (Phase 7)**: code and tests run on fixtures once US3's reconcile exists (T072); the real export (T089) needs T081
- **Broadcast test (Phase 8)**: needs US2 (viewer) and pilot POV readings
- **Polish (Phase 9)**: after the stories you want shipped

### Critical path (pilot)

T001–T019 → T022–T025 → T028–T035 → T036–T040 (probe) → T046–T053 → T060–T063 (icons, gold, bulk extract) → T064–T066, T072–T081 → T084–T089 → T090–T093

### Human steps on the critical path

T030 patches · T035 alias + link check · T039 terms + HUD probe · T060 icon naming · T062 gold labels · T063 bulk run · T065 OWTV probe · T081 review · T089 export check · T092 broadcast decision · T093 gate

---

## Parallel Examples

### Foundational

```text
T010 test_config.py   |  T013 test_tables_manifest.py  |  T015 test_entities.py
T018 ratelimit.py     |  T019 snapshot.py              (after T011/T012)
```

### User Story 2 (after T040 layout exists)

```text
Tests:   T041 test_rle.py | T042 test_readers.py | T043 fixture | T044 test_interpret.py | T045 test_segments_objective.py
Viewer:  T046 layout.py   | T047 icons.py        | T048 ocr.py
Interp:  T054 spans.py    | T055 heroes.py+gaps.py | T056 kills.py | T057 objective.py+attacks.py
```

### User Story 3 (fixtures only, can start right after Foundational)

```text
T067 planted fixture | T068 test_compare.py | T069 test_discrepancies_status.py | T070 test_planted_errors.py | T071 test_audit.py
```

### User Story 4

```text
T082 test_export.py | T083 test_analysis_tables.py
```

---

## Implementation Strategy

### MVP (US0 + US1)

1. Phases 1–2: setup and foundational
2. Phase 3 (US0): the inventory becomes a tested command
3. Phase 4 (US1): pilot catalog with links
4. **Stop and validate**: 30-link check. Map winners from the catalog are already enough for feature 001's team Elo

### Incremental delivery

1. **+ US2**: probe → layout → icons → gold set passes SC-002 → bulk pilot extraction
2. **+ US3**: OWTV probe → verification → review → `audit` clean
3. **+ US4**: export to feature 001, plus kill events and player × hero tables
4. **+ Broadcast test**: decide gap fill, then the pilot gate, then one region-stage at a time

### Working alone

US2's pixel work (T046–T053) is the riskiest part. Build the US3/US4 code on fixtures in the
waiting time of human steps (icon naming, gold labeling, overnight extraction), so verification
and export are ready when the pilot readings land.

---

## Notes

- [P] tasks touch different files and have no unfinished dependencies
- Commit after each task or logical group; never commit video files or `local.yaml`
- Every file under `data/raw/` is append-only or write-once; if a task seems to need editing one,
  it belongs in interim or in a decision instead
