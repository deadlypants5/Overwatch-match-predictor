# Contract: `owstudy-collect` command line

Console script from the shared `owstudy` package (`python -m owstudy.collect` also works).
Global options: `--config PATH` (default `configs/collect/default.yaml`), `--scope SCOPE`
(`pilot` = Korea Stage 1, a region-stage key like `Asia/Stage 1/Korea`, or `all`), `--data-dir`
(default `data/`), `-v`.

Exit codes: `0` ok · `1` validation/audit failures (all listed) · `2` usage/config error ·
`3` external retrieval blocked (terms not acknowledged, rate limit, network) · `4` partial
success (some videos failed; see state file).

## Reference and catalog

| Command | Does | Writes |
|---|---|---|
| `refs fetch {liquipedia\|owtv} [--since-snapshot ID]` | Retrieves a new snapshot within rate limits (research R9/R10); reports differences from the previous snapshot. | `data/raw/reference/<source>/<date>/` |
| `refs import-sheet PATH` | Parses the spreadsheet into a snapshot. | `data/raw/reference/spreadsheet/<date>/` |
| `refs probe-owtv SERIES…` | R10 probe: saves what OWTV offers for a few series. | `data/interim/probes/owtv/` |
| `videos list` | Snapshot of the channel's video list (titles, IDs, lengths). | `data/raw/reference/youtube/<date>/` |
| `catalog build` | Entities, aliases proposals, catalog series/maps, lineups, video links, primary POV choice. | `data/interim/{entities,catalog}/` |
| `inventory` | Footage inventory (US0, FR-007a), replacing `scripts/inventory/`. | `data/interim/inventory/` |

## Viewer

| Command | Does |
|---|---|
| `hud probe VIDEO…` | R5 probe: downloads, samples frames, saves crops of every HUD region and a checklist. |
| `icons harvest VIDEO…` / `icons label` | Builds the icon library: groups portrait crops, then asks the researcher to name each group. |
| `extract [--videos IDS] [--force] [--keep-video] [--check-determinism]` | Pipeline over `state.csv`: download → readings → delete (FR-007c, FR-009, FR-012). `--check-determinism` runs recognition twice and compares byte for byte (implies `--keep-video` until done). |
| `broadcast-test SERIES…` | FR-007b: processes the broadcast VODs of series that also have a POV and scores them against the POV readings. Writes `data/interim/reports/broadcast_test.md`. |

## Build, verify, review

| Command | Does |
|---|---|
| `build` | interpret → reconcile → comparisons/discrepancies → status. Pure, no network. |
| `review [--kind KIND] [--map MAP_ID]` | Interactive: shows each open/stale discrepancy with all values and a `youtu.be/<id>?t=<s>` link; keys: `1..n` accept source n, `c` correct (prompt value), `s` skip; then a reason. Appends to `decisions.csv`. |
| `audit` | SC-004 check: every reconciled value traces to raw or a decision. Exit 1 on any miss. |
| `validate` | Data-model §4 checks over all layers. |
| `gold init MAP_ID…` / `gold score` | Gold label templates; accuracy per field vs SC-002 thresholds → `data/interim/reports/gold_accuracy.csv`. |
| `plant-errors --maps N --out DIR` | Copies reconciled inputs with planted errors (winner, player, kill, ban, date) and checks every one is caught (SC-006). Never touches real data. |

## Export

| Command | Does |
|---|---|
| `export [--include verified\|partial\|all] [--out DIR] [--no-analysis-tables]` | Writes feature 001 input, the analysis tables (kill events, player × hero per map and summary, FR-024a), summary and provenance (contracts/export.md). Runs the analysis-table consistency checks, then 001's validator if available (SC-007). |
| `status` | Coverage table per region-stage: in scope, with replay, processed, verified, open discrepancies by kind, excluded by reason. |

## Python API (`owstudy.collect`)

`load_config(path)`, `build_catalog(cfg)`, `extract_video(cfg, video_id) -> RunResult`,
`interpret(readings, span, cfg) -> MapEvents`, `reconcile(cfg) -> Reconciled`,
`export(reconciled, out_dir, include)`. The functions behind `build`, `audit` and `export` take
paths and return data. They don't use the network.
