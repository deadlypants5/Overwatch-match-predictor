# Implementation Plan: Match Data Collection & Verification

**Branch**: `002-match-data-collection` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-match-data-collection/spec.md`

## In short

- **What gets built:** one command-line tool, `owstudy-collect`, that runs on your PC (no cloud,
  no GPU needed).
- **The pipeline:**

  ```text
  list matches and videos → download a POV video → read the HUD every half second → delete the video
      → turn readings into swaps, kills, attacks → compare with the reference sources
      → you review disagreements → export for feature 001
  ```

- **Storage:** plain CSV, YAML and JSON files. Raw readings and source downloads are never
  edited; everything else can be rebuilt from them in one command.
- **Checks before bulk work:** two probes. Does the POV HUD show everything the viewer needs?
  What does OWTV actually provide? Each has a fallback decided in advance.
- **Time:** the pilot (~18 h of footage) should take about 5–10 hours unattended.
- **Open item:** POVs alone can't reach 95% pilot coverage, so the broadcast test decides
  (see "Open item for the researcher" below).

The step-by-step order is in [Pipeline walk-through](#pipeline-walk-through-pilot) at the end.

## Summary

Build `owstudy-collect`, a local, CPU-only command-line pipeline (part of the shared `owstudy`
package) that turns ObsSojourn replay videos and three reference sources into a verified,
map-level dataset in feature 001's input format.

- **Storage** (research R1, R6): plain CSV/YAML/JSON files in the constitution's folders.
  `data/raw/` holds immutable layers: reference snapshots per retrieval date, the viewer's
  run-length-encoded **readings** per `(video, extraction_key)`, gold labels, and the
  append-only review decisions. `data/interim/` holds everything rebuildable: entities and
  aliases, catalog, video links, map spans, interpreted events, reconciled maps, comparisons and
  discrepancies. `data/processed/collection/` holds exports. Videos stay in a cache outside the
  repo and are deleted after extraction.
- **Collection** (R2–R8, R14): `yt-dlp` downloads 1080p H.264 video. PyAV samples 2 frames per
  second by timestamp. A HUD-presence check skips downtime. The "virtual viewer" reads fixed HUD
  regions defined in a layout config: hero portraits and kill-feed icons by template matching
  against a one-time-labeled icon library, names, clocks and banners by local OCR (RapidOCR),
  and objective bars by pixel measurement. Reading is kept separate from interpretation (swaps,
  kills, segments, attacks), so rule fixes never need another download.
- **Verification** (R9–R11, R15–R16): Liquipedia, spreadsheet and OWTV snapshots are compared
  field by field with the video (FR-016/017). Each disagreement is a discrepancy with a stable
  ID, a provisional value by source priority, and a jump-to-time YouTube link. The researcher
  resolves it in an interactive `review` command, and the decision is re-applied on every
  rebuild (and marked stale if the sources change). An audit proves nothing changed without a
  decision. A hand-labeled gold set measures viewer accuracy.
- **Analysis tables** (FR-024a, contracts/export.md): next to the 001 input, every export also
  has `kill_events.csv` (one row per kill, with heroes on both sides), `player_hero_map.csv`
  (time on hero, team kills and deaths, own kills and deaths, objective for and against, per
  map) and `player_hero_summary.csv` (totals and per-10-minute rates per player × hero × mode).
  The summary is descriptive and isn't time-safe as a feature.

Work starts with two **probes** (R5: does the POV HUD show everything; R10: what OWTV
provides), each with a fallback already decided, before any bulk processing.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: pandas, PyYAML, numpy (shared with 001); `collect` extra: yt-dlp,
av (PyAV), opencv-python-headless, rapidocr-onnxruntime/onnxruntime, rapidfuzz, requests,
openpyxl; dev: pytest, hypothesis (justified in research R18)

**Storage**: Files only. CSV tables, YAML configs, JSON run manifests, in `data/raw|interim|processed`
(contracts/storage-layout.md). Video cache outside the repo, deleted after use.

**Testing**: pytest. Unit tests (encoding, interpretation, normalization, comparisons, status
rules), fixture integration tests on synthetic readings and references, planted-error test
(SC-006), determinism tests (SC-008), gold-set accuracy report (SC-002).

**Target Platform**: Researcher's Windows 11 PC (also runs on Linux/macOS). CPU only, no
cloud (FR-015).

**Project Type**: Library + CLI, in the same single `src/owstudy` package as feature 001

**Performance Goals**: Pilot (~18 h of POV footage) in ~5–10 h unattended; whole set (~200 h)
in ~3–5 days (research R12)

**Constraints**: No paid or cloud services; follow platform terms and rate limits (Liquipedia
≤1 request per 2 s); deterministic readings and byte-stable rebuilds; raw layers never edited;
no video in the repo; peak disk < ~10 GB

**Scale/Scope**: Pilot 51 series / 186 maps (25 series / 92 maps with a POV); whole 2026 set 613
series / 2,229 maps, ~1,318 POV videos (inventory 2026-11-15)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|-----------|------------------------|--------|
| I. Map is the unit | Catalog, spans, events, reconciled records, comparisons and export are all keyed by `map_id` = `<series_id>-m<n>`. Series-level data is used only for checks (lineups, series score) and never exported as a training row. | ✅ |
| II. Temporal integrity | This feature produces no features or ratings. The player × hero summary covers the whole period and is labeled descriptive only, never a pre-map feature (FR-024a). It supplies what 001 needs to enforce ordering: correct `date`, UTC `series_start` and `patch_id` per map, with dates checked across sources in one time zone (R11). Nothing here aggregates across maps, so no leakage path exists. 001's leakage tests run on this export. | ✅ (N/A for features) |
| III. Documented math | No rating math. The objective normalization per mode feeds 001's formulas and is documented in data-model §2.3 with unit tests. | ✅ |
| IV. Provenance & verification | Every reading carries video ID, timestamps, clock, type, value, confidence, method and extractor version, and resolves to its run date via `run.json` (FR-002). Raw layers are immutable with hash manifests. Corrections exist only as logged decisions. Cross-checks against Liquipedia, spreadsheet and OWTV, with every disagreement logged with both values. Verification status per map, and export with/without unverified maps (`--include`). Terms-of-use gate before downloads, rate limits, no video stored. | ✅ |
| V. Baselines first | Not a modeling feature. The analogous rule here: viewer accuracy is measured against a hand-labeled gold set before bulk use (FR-022), and broadcasts are measured against POVs before use (FR-007b). | ✅ (N/A) |
| VI. Reproducibility | `owstudy-collect build && export` regenerates the dataset from raw + configs + decisions in one command, byte-identical (R13). Pinned deps in the shared `uv.lock`. All thresholds and tolerances in `configs/collect/*.yaml`. Logic in tested modules, not notebooks. Video deletion is covered by storing file hashes and running the determinism check before deletion. | ✅ |
| Data & tech constraints | Python 3.11, pandas. Extra libraries justified in R18. `data/raw` → `interim` → `processed` layout respected. Stable IDs with a hand-curated alias table. | ✅ |

**Post-design re-check (after Phase 1)**: ✅ No violations. One item to note (not a violation):
the hand-curated `aliases.csv`, icon library and decisions are human inputs. Decisions live in
`data/raw/` (they can't be regenerated). Aliases and icons are committed but sit in
`data/interim/entities/` next to the generated entity tables they curate, and `build` never
overwrites them.

**Open item for the researcher (not a gate failure, research R17)**: only 25 of 51 pilot series
have an ObsSojourn POV, so **SC-001 (95% linked) can't be met on the pilot with POVs alone**.
The plan builds the broadcast path from the start, and the FR-007b test decides whether it's
used. If the test fails, SC-001 needs a spec change (e.g., measured over maps with a POV).

## Project Structure

### Documentation (this feature)

```text
specs/002-match-data-collection/
├── plan.md                  # This file
├── research.md              # Phase 0: decisions R1–R18
├── data-model.md            # Phase 1: entities, layers, state transitions
├── quickstart.md            # Phase 1: validation guide
├── contracts/
│   ├── cli.md               # owstudy-collect commands, exit codes, Python API
│   ├── storage-layout.md    # folder layout + table schemas
│   ├── config-schema.md     # default/local/patches/HUD layout YAML
│   ├── reference-sources.md # spreadsheet, Liquipedia, OWTV, YouTube adapters
│   └── export.md            # mapping to feature 001 input + sidecars
├── checklists/requirements.md
└── tasks.md                 # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml                         # shared with 001; extras: collect, dev; scripts: owstudy-strength, owstudy-collect
configs/collect/
├── default.yaml  patches.yaml  local.example.yaml
└── hud/  owcs2026_pov_v1.yaml  anchors/*.png  (broadcast layout added after FR-007b)

src/owstudy/collect/
├── __init__.py  __main__.py  cli.py   # argparse subcommands (contracts/cli.md)
├── config.py                          # load/merge/validate YAML, extraction_key hashing
├── io/
│   ├── tables.py                      # deterministic CSV read/write (sorted, fixed formats)
│   └── manifest.py                    # run.json, MANIFEST.sha256, immutability checks
├── refs/
│   ├── snapshot.py                    # dated snapshot folders, diff between snapshots
│   ├── ratelimit.py                   # per-host min interval + on-disk cache
│   ├── spreadsheet.py                 # ← scripts/inventory/parse_sheet.py
│   ├── liquipedia.py                  # ← scripts/inventory/parse_lp.py (+ lineups)
│   ├── owtv.py                        # after R10 probe
│   └── youtube_list.py                # channel listing
├── catalog/
│   ├── entities.py                    # stable IDs, aliases, proposals, fuzzy match
│   ├── build.py                       # catalog series/maps/lineups, patch assignment, tz → UTC
│   ├── link.py                        # ← scripts/inventory/inventory.py matching; primary POV choice
│   └── inventory.py                   # US0 report
├── viewer/
│   ├── download.py                    # yt-dlp wrapper, terms gate, cache limit, hash
│   ├── frames.py                      # PyAV PTS sampling at fps
│   ├── layout.py                      # HUD layout load + anchor detection
│   ├── icons.py                       # icon library, NCC matching, harvest/label
│   ├── ocr.py                         # RapidOCR wrapper (fixed threads)
│   ├── readers/                       # hero.py names.py killfeed.py clock.py objective.py banner.py bans.py result.py
│   ├── rle.py                         # run-length encoder for readings
│   ├── extract.py                     # one video → readings; pipeline + state.csv
│   └── probe.py                       # HUD probe (R5)
├── interpret/
│   ├── spans.py                       # map spans + alignment to catalog order (R8)
│   ├── heroes.py  kills.py  objective.py  attacks.py  gaps.py
│   └── segments.py                    # segment tiling, per-segment kills/objective (FR-010)
├── verify/
│   ├── compare.py                     # FR-016/017 comparisons
│   ├── discrepancies.py               # stable IDs, provisional values (FR-021), stale detection
│   ├── decisions.py                   # append/apply decisions
│   ├── status.py                      # FR-019 map status
│   ├── review.py                      # interactive review CLI
│   ├── audit.py                       # SC-004
│   └── gold.py                        # gold init/score (FR-022)
├── reconcile.py                       # interim events + refs + decisions → reconciled tables
├── export.py                          # 001 input dir, summary, provenance, manifest
└── analysis.py                        # kill_events, player_hero_map, player_hero_summary + consistency checks (FR-024a)

tests/collect/
├── fixtures/  synthetic_readings/  references/  planted/  hud_frames/ (a few committed PNG crops, no video)
├── unit/          # rle, interpret rules, normalization, compare, discrepancy ids, status, aliases
├── integration/   # build → export on fixtures; 001 validate on the export; determinism (build twice)
└── viewer/        # readers on committed frame crops (accuracy smoke tests)
```

**Structure Decision**: One package, `owstudy`, with `strength/` (001) and `collect/` (002)
side by side, so the export can call 001's validator directly and both share pinned
dependencies. The heavy video stack sits behind the `collect` extra. The existing
`scripts/inventory/*.py` move into `refs/` and `catalog/` (behavior kept, then extended), and
the scripts folder is removed once `owstudy-collect inventory` reproduces the 2026-11-15
outputs. `viewer/` (reads pixels, writes raw) and `interpret/` (reads raw, writes interim) never
import each other, which keeps the "fix without re-watching" rule structural.

### Pipeline walk-through (pilot)

1. **Inventory and catalog**: snapshot references, build entities/aliases and the catalog,
   link videos, and choose one primary POV per series.
2. **Probes**: HUD probe (R5) and OWTV probe (R10). Apply fallbacks if needed.
3. **Icon library and layout**: tune the HUD layout on probe frames, then harvest and label icons.
4. **Gold set**: extract the 6 gold maps' videos with `--keep-video --check-determinism`. The
   researcher labels them, then `gold score`. Iterate on readers/rules until SC-002 passes.
5. **Bulk extract**: resumable download → read → delete over the pilot's primary POVs
   (~18 h of footage).
6. **Build and review**: interpret → reconcile → compare → discrepancies → `review` → rebuild →
   `audit`.
7. **Broadcast test** (FR-007b) on 3 overlapping series. The researcher decides on gap fill.
8. **Export**, run 001's validator, and read the coverage summary. Expansion gate (FR-023).

## Complexity Tracking

No constitution violations; nothing to justify.
