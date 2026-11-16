# Research: Match Data Collection & Verification

**Feature**: `002-match-data-collection` | **Date**: 2026-11-15 | **Plan**: [plan.md](./plan.md)

## In short: every decision on one page

| # | Question | Decision |
|---|---|---|
| R1 | How is data stored? | Plain CSV/YAML/JSON files in git; raw data never edited; videos kept outside the repo and deleted after use |
| R2 | How are videos downloaded? | `yt-dlp`, 1080p H.264, one at a time, rate-limited, only after you confirm the platform terms |
| R3 | How often are frames read? | 2 frames per second; frames without the game HUD (caster desk, ads) are skipped |
| R4 | How does the viewer recognize things? | Classic image matching on fixed HUD areas: hero icons by template matching, text by local OCR, bars by pixel measurement. No AI model, no GPU |
| R5 | Does the POV HUD show everything? | **Probe first** on 3 videos, with a fallback for each missing element |
| R6 | What is a "raw observation"? | Compressed per-frame readings; interpretation (swaps, kills) is a separate, rebuildable step |
| R7 | How are videos linked to series? | Parse the title, match teams and dates, confirm with the player names on screen; one POV per series |
| R8 | How is each map found in a video? | By the banner's map number, with the mode as a check; map names come from the references |
| R9 | How are references downloaded? | Spreadsheet from the file; Liquipedia through its API at ≤1 request per 2 s; each download kept as a dated snapshot |
| R10 | What does OWTV provide? | **Probe first** on 3 series; fallbacks decided for per-series-only or missing data |
| R11 | How are names kept consistent? | Stable IDs plus a hand-curated alias table; times stored in UTC |
| R12 | How long will it take? | Pilot ~5–10 h unattended; whole set ~3–5 days |
| R13 | Same input, same output? | Yes: fixed frame choice and settings fingerprint; restarts skip finished videos |
| R14 | How are readings turned into events? | Swap after ≥1 s on a new hero; replays rejected when the game clock runs backwards; gaps marked |
| R15 | How are disagreements handled? | Each becomes a discrepancy you settle in a `review` command; decisions are re-applied on every rebuild |
| R16 | How is accuracy measured? | 6 hand-labeled "gold" maps, at least one per mode |
| R17 | Can broadcasts fill the coverage gap? | Tested on 3 series against the POVs; used only if it passes and you approve |
| R18 | Which libraries, and why? | Listed in a table at the end |

## How to read each entry

Each entry gives the **Decision**, the **Rationale** (why), and the **Alternatives considered**.
Entries marked **Probe** depend on a small check that runs first during implementation. Each
one has a stated fallback, so nothing here is left open.

---

## R1. Storage format and layout

- **Decision**: Plain files in git, organized in the constitution's three folders:
  - `data/raw/`: immutable layers. Reference snapshots (`reference/<source>/<retrieved_date>/`),
    viewer readings (`observations/<video_id>/<extraction_key>/`), gold labels
    (`gold/`), and review decisions (`decisions/decisions.csv`, append-only).
  - `data/interim/`: everything rebuildable. Entities and aliases, catalog, video links, map
    spans, interpreted events, reconciled maps, comparisons, discrepancies.
  - `data/processed/collection/<export_id>/`: exports in feature 001's input format plus
    summary and provenance sidecars.
  - Videos go in a cache folder **outside** the repo (default `%LOCALAPPDATA%/owstudy/videos`,
    configurable) and are deleted after a successful run (FR-007c).
  - **Format**: UTF-8 CSV for every table, YAML for configs, JSON for run manifests. Writers
    sort rows and fix number formats so output is byte-stable (same writer rules as 001 R10).
- **Rationale**: The researcher asked for a recommendation and isn't a data specialist. CSV opens
  in Excel, diffs in git, and is what feature 001 reads, so no conversion layer is needed. Sizes
  are small once readings are run-length encoded (R6): about 10–30 MB of CSV for the pilot and
  under 300 MB for the whole set. The review decisions count as raw because they're human input
  that can't be regenerated.
- **Alternatives considered**: SQLite (one file, good queries, but binary diffs in git and
  harder for the researcher to inspect by hand). Parquet (compact, but not human-readable and
  bytes depend on library version, which makes SC-008 harder). DuckDB over CSV is still
  available for ad-hoc queries without changing the stored format.

## R2. Getting the videos

- **Decision**: `yt-dlp` (Python API), video-only stream, H.264 (`avc1`) at 1080p where
  offered, otherwise the best ≤1080p stream. One download at a time, `--limit-rate` and a
  random 5–15 s sleep between downloads, resume on failure. Each run manifest records the file's
  SHA-256, format ID and resolution. Downloading is blocked until
  `platform_terms_acknowledged: true` is set in the local config (spec assumption: the
  researcher confirms personal-research use is allowed; FR-014).
- **Rationale**: Kill-feed names and hero icons are small. 720p makes them unreliable to
  read, and 1080p is the smallest size where they read cleanly. H.264 decodes 3–5× faster on a
  CPU than VP9/AV1. Audio isn't used. The hash shows whether a re-download (needed after the
  video is deleted, FR-007c) is the same file.
- **Alternatives considered**: Streaming frames without downloading (fragile, and you can't
  re-read a frame deterministically). 720p (about half the download, but lower name-reading
  accuracy, which would endanger SC-002).

## R3. Frame decoding and sampling

- **Decision**: PyAV (bundled FFmpeg), single-threaded decode. Sample by presentation timestamp
  at **2 frames per second** (every frame whose PTS crosses the next 0.5 s mark). A cheap
  **HUD-presence check** runs on each sampled frame first: matching a few fixed HUD anchors
  (the clock box and the team-bar edges). Frames without the HUD get only that check, which is
  how caster desks, intermissions and ads are skipped (spec edge case).
- **Rationale**: Kill-feed entries stay on screen for about 5 s and hero swaps need ±3 s
  (SC-002), so 2 fps gives about 10 looks at every kill-feed entry and catches every swap
  within 0.5 s. Choosing frames by PTS instead of wall clock or "every Nth frame" makes the
  selection deterministic even for variable-frame-rate files.
- **Alternatives considered**: OpenCV `VideoCapture` (frame timestamps unreliable on
  variable-frame-rate files). 1 fps (cuts per-frame work in half, but each kill-feed entry is
  seen fewer times). A higher rate only in fights (more complex, not needed for the budget, R12).

## R4. How the virtual viewer recognizes things (core decision)

- **Decision**: **Classical computer vision on fixed HUD regions**, all local and CPU-only:
  - **HUD layout config** (`configs/collect/hud/<layout_id>.yaml`): regions of interest in
    normalized coordinates for the 10 hero portraits, 10 name plates, kill-feed area, game
    clock, attack clock, objective widget per mode, team names/score, map-number banner ("MAP n"),
    and ban display. A layout is recognized automatically by its anchor templates, so a HUD change mid-season
    (e.g., at a LAN) becomes a new layout file, not a code change.
  - **Hero portraits and kill-feed hero icons**: nearest-neighbor match against an **icon
    library** (`data/interim/entities/icons/<hero_id>/*.png`). Crops are compared by normalized
    cross-correlation on a fixed-size image, and confidence comes from the margin between the
    best and second-best hero. The library is built once with a harvest tool. It groups
    portrait crops from 2–3 pilot videos and the researcher names each group (about 45 heroes,
    roughly 15 minutes).
  - **Text** (player names, clock digits, map number on the banner, team names): **RapidOCR** (PaddleOCR
    models on `onnxruntime`, CPU, thread count fixed in config). Raw OCR strings are kept,
    and names are resolved to IDs afterwards through the alias table with fuzzy matching
    (`rapidfuzz`), limited to that series' rosters.
  - **Kill feed**: each row is split into killer icon, killer name, ability icon, victim icon and
    victim name. Team comes from the row's color/side. Rows are tracked across frames and
    merged into one kill event (first seen, last seen, number of frames).
  - **Objective widgets**: progress is read per mode (capture percent, payload/robot progress
    bar, checkpoint markers, flashpoint point count). See data-model §2.3.
- **Rationale**: The observer HUD is fixed, high-contrast and uses a small closed set of
  icons, which is the best case for template matching. This approach is deterministic
  (FR-013) and fast on a CPU (R12). Every value carries a measurable confidence (FR-011), and
  every mistake can be traced to a region and a frame. Nothing needs training except the
  one-time icon naming.
- **Alternatives considered**:
  - *A local vision-language model* (e.g., a 7B VL model): reads any screen with no layout work,
    but processing 130k pilot frames would take days to weeks on a consumer GPU (FR-015),
    output isn't reliably deterministic, and confidences aren't calibrated. Kept as a possible
    **second-opinion tool** for low-confidence frames only, not in the main path.
  - *Training a CNN detector*: more robust to layout drift, but needs labeled data we don't
    have yet. The gold set and review decisions could later become that training data.
  - *Cloud vision APIs*: ruled out by FR-015.

## R5. **Probe**: does the ObsSojourn POV show everything the viewer needs?

- **Decision**: The first implementation step runs a **HUD probe** on 3 pilot videos (one per
  mode family). It saves sample frames and a checklist: are all 10 portraits visible, all 10
  names, both teams' kill-feed entries, the clock, attack clock, objective widget, ban display,
  map number on the banner, and mode (from the objective widget). The map **name** is not on
  the POV banner and is not needed from the video: it comes from the spreadsheet/Liquipedia
  (spec Clarifications 2026-11-16). Every element that's missing is handled in one of these ways:
  - **Ban display missing** → bans come from Liquipedia/spreadsheet only (`single_source` for
    the video), which is already allowed by FR-021.
  - **Enemy names missing** (portraits only) → enemy players are mapped from that team's
    Liquipedia lineup plus their hero, and the cross-check uses the second POV from the other
    team (`povs_per_series: 2`, the third footage count in the inventory, ~35 h for the pilot).
  - **Kill feed limited to the POV player's kills** → this would break team kill totals. Fall
    back to two POVs per series, or the scoreboard-only kill totals from the reference source,
    flagged. The plan would be revisited with the researcher.
- **Rationale**: The spec assumes the standard observer layout (Assumptions). This turns that
  assumption into a check before any large processing run, with a known answer for each way it
  could fail.
- **Alternatives considered**: Assuming the layout and finding out after processing (expensive
  re-download).

## R6. What "raw observation" means at the storage level

- **Decision**: The viewer writes two kinds of output:
  1. **Readings** (raw, immutable, `data/raw/observations/…`): what each region showed,
     **run-length encoded**. Consecutive sampled frames with the same value become one row
     with `ts_start`, `ts_end`, frame count, and minimum/mean confidence. Any frame below the
     confidence threshold, or with a different value, starts a new row. Kill-feed rows are
     stored as tracked events (first/last seen). Gaps (no HUD) are stored as their own
     reading type.
  2. **Interpreted events** (interim, rebuildable): hero swaps, deduplicated kills, map spans,
     attack boundaries, final results and segments, derived from readings by deterministic
     rules (smoothing, debouncing, clock-monotonic replay rejection).
- **Rationale**: Run-length encoding is lossless for categorical values and keeps the raw
  layer small (R1). Separating reading from interpreting means a better swap-detection rule
  or alias fix only needs a rebuild, not another download, which is the spec's main storage
  goal ("fixed without re-watching video").
- **Alternatives considered**: Per-frame rows (≈3M rows for the pilot, ≈36M for the whole set,
  with little extra value). Storing only interpreted events (would make an interpretation bug
  require another download).

## R7. Video ↔ series linking and choosing the POV

- **Decision**: Reuse and harden the inventory logic (`scripts/inventory/inventory.py` →
  `owstudy.collect.catalog.link`). Parse the title (`[ Player ] Nickname | Team A vs Team B |
  Event`), resolve teams through aliases, filter candidate series by event and date window
  (series date ≤ upload date, nearest first), and break ties with phase words. Link confidence
  is `high` (one candidate), `medium` (resolved by phase/date), or `low`. Low goes to review.
  The link is **confirmed** after extraction when the HUD team names and ≥8 of the 10 player names
  match the series' rosters. Otherwise it's a `link` discrepancy.
  **Primary POV per series**: the video whose length best covers the summed map spans,
  ties broken by `video_id`. With `povs_per_series: 2`, the longest video from the other team
  is also processed, for cross-checking.
- **Rationale**: The inventory already matched 1,318 videos, and its known weak spot (repeated
  pairings within a window) gets a hard check from the HUD names. The spec says one POV per series is
  the minimum (US0).
- **Alternatives considered**: Matching on video content alone (would need to process
  unrelated videos), or processing all POVs (5–6× the footage, ~107 h for the pilot).

## R8. Finding where each map is in a video (map spans)

- **Decision**: The viewer reads the whole video. Map spans come from the readings: a map
  starts at the first HUD frame after a map-banner or loading screen, or after a change in the
  map number/mode reading, and ends at the final-result reading or the last HUD frame before the
  next map. Spans are matched to catalog maps **by map number** (the banner's "MAP n"), and the
  mode read from the objective widget must match the catalog map's mode. A mismatch in count,
  map number or mode is a `map_order` discrepancy. Map names come from the catalog (spreadsheet,
  cross-checked against Liquipedia), not from the video. A remade map (two spans with the same
  map number, the first without a result) keeps the completed span and records the abandoned one as `excluded_remake`.
- **Rationale**: POV videos cover a whole series. Map number plus mode is enough to align them,
  and a mismatch is itself useful information.
- **Alternatives considered**: Reading chapter markers from the video description (not
  reliably present).

## R9. Reference sources: retrieval and snapshotting

- **Decision**:
  - **Spreadsheet**: parsed from the fixed `.xlsx` with `openpyxl` (existing
    `parse_sheet.py`), recording the sheet and row for each record. Bans per map and team
    abbreviations come from here.
  - **Liquipedia**: MediaWiki API (`action=query&prop=revisions` for page wikitext, parsed
    locally), following Liquipedia's API terms: a descriptive User-Agent, gzip, **≤1 request per
    2 s** (and ≤1 per 30 s for `action=parse`, which we avoid), plus local caching by
    page revision ID. The User-Agent contact string comes from a local, uncommitted
    environment setting. Supplies dates and time zone, teams, series lineups, map list, map
    winners and scores, bans, VOD links (existing `parse_lp.py`, extended to read lineups).
  - Each retrieval goes in a new dated snapshot folder with the raw responses and the parsed
    CSV. The existing 2026-11-15 files are moved unchanged into
    `reference/<source>/2026-11-15/`. Re-retrieving creates a new snapshot, and differences from
    the previous one are reported (spec edge case).
- **Rationale**: Snapshots make every comparison reproducible against exactly what was seen
  (FR-004). Page revision IDs make re-retrieval cheap.
- **Alternatives considered**: Scraping rendered HTML (against Liquipedia's terms and more
  fragile).

## R10. **Probe**: OWTV fantasy results

- **Decision**: A probe task looks at 3 pilot series on OWTV to find out whether results are
  **per map or per series**, which stats are given (deaths, eliminations, final blows), and
  whether the data comes from a page or a JSON endpoint the page itself calls. The result goes
  in `contracts/reference-sources.md` §OWTV before the adapter is written. Behavior by outcome:
  - Per map with deaths → per-player deaths (exact) and team kill totals (±1), per FR-016/017.
  - Per series only → the same checks summed over the series' maps (spec assumption). Map-level
    kill fields become `single_source`.
  - Not available or not permitted for a series → those fields are `single_source`.
  Retrieval runs at ≤1 request per 5 s with caching, and only if the site's terms allow it.
- **Rationale**: A web search (2026-11-15) found OWTV match recaps and per-match pages but
  couldn't confirm the stat format. The spec already defines the fallback. A probe costs
  minutes and prevents writing the wrong adapter.
- **Alternatives considered**: Other public stat sites (e.g., OWTics) as the scoreboard source.
  These need the researcher's approval because the spec names OWTV. Noted as a fallback only.

## R11. Entities, IDs and aliases

- **Decision**: Stable IDs are short slugs (`team:t1`, `player:<lp_page_slug>`,
  `hero:<slug>`, `map:<slug>`). Liquipedia page names seed teams and players, so IDs survive
  renames. `data/interim/entities/aliases.csv` is **hand-curated and version-controlled**.
  Tools only *propose* new aliases (`aliases_proposed.csv`, with fuzzy score and context). A name
  that's within fuzzy distance of an existing player but not aliased is flagged, never
  auto-created (spec edge case). Exported aliases match 001's `entities/aliases.csv` schema.
- **Patches**: `configs/collect/patches.yaml` lists `patch_id` and its live date (UTC). Each map
  gets the patch live at its series start.
- **Time**: Liquipedia gives local time and time zone. Times are stored in UTC, and comparisons
  happen in UTC. A one-day difference caused only by time zone is recorded as
  `agree_within_tolerance` with a note (spec edge case). The exported `date` is the event-local
  date (as Liquipedia shows it), and `series_start` is UTC.

## R12. Throughput on the researcher's computer (FR-015)

- **Decision / estimate** (typical 6–8-core desktop CPU, no GPU required, 16 GB RAM):
  | Step | Pilot (18.4 h, one POV) | Whole set (~200 h) |
  |---|---|---|
  | Download (1080p H.264, ~2 GB/h, rate-limited) | ~37 GB, 2–5 h | ~400 GB moved, peak disk < 10 GB, 1–3 days |
  | Decode (~250–400 fps) | ~1.5–2.5 h | ~16–27 h |
  | Recognition (2 fps, ~30–60 ms per HUD frame) | ~1–2 h | ~11–22 h |
  | Interpret, reconcile, export | minutes | < 1 h |
  | **Total** | **~5–10 h** (plus broadcast test) | **~3–5 days unattended** |
  Download and processing run as a pipeline (download the next video while the current one is
  processed). Disk holds at most `cache_max_videos` (default 2) at a time.
- **Rationale**: Well inside "a few days" for the pilot and "a few weeks" for the whole set.
  The estimates get replaced by measured numbers after the HUD probe (R5).
- **Alternatives considered**: Multiprocessing several videos at once. Allowed by config
  (`workers`), but default 1 to keep the computer usable. Determinism doesn't depend on it.

## R13. Determinism and resumability (FR-012, FR-013, SC-008)

- **Decision**:
  - `extraction_key` = short hash of (extractor package version, HUD layout file hash, icon
    library hash, OCR model hash, sampling settings). Readings are stored per
    `(video_id, extraction_key)`.
  - Determinism: fixed frame selection by PTS (R3), single-threaded decode, fixed ORT threads,
    no randomness, sorted output. The run date and timing go **only** in `run.json`, never in
    observation rows. Observation rows carry `run_id` and `extractor_version`, so each row
    still resolves to its extraction date (FR-002).
  - A determinism check (`extract --check-determinism`) runs recognition twice on a cached video
    and compares the readings byte for byte. It runs on the gold-set videos before they're
    deleted.
  - Resumability: each video has a state in `data/interim/runs/state.csv` (`pending →
    downloaded → extracted → deleted`, or `failed` with a reason). On restart, videos already
    `extracted` with the current key are skipped. A key change or `--force` reprocesses.
  - Rebuild determinism: `build` (interpret → reconcile → export) is a pure function of the
    raw layer, configs and decisions. CI-style test: build twice, compare exports byte for byte.
- **Rationale**: Directly satisfies FR-012/013 and SC-008 even though videos are deleted. The
  stored file hash shows whether a re-download is the same file.
- **Alternatives considered**: Putting the extraction date in each row (would break byte-identical
  re-runs).

## R14. Interpretation rules (readings → events)

- **Decision** (all thresholds in `configs/collect/default.yaml`):
  - **Hero swap**: a portrait reading that holds a new hero for ≥ 2 consecutive sampled frames
    (≥ 1 s) at confidence ≥ threshold. The swap time is the first frame of the new run. Swaps
    in spawn shorter than 10 s are kept and flagged `short_segment`.
  - **Kills**: tracked kill-feed events. The game time is the clock at `first_seen`. An event
    whose killer, victim and heroes repeat an earlier event within 15 s is flagged
    `possible_replay`. Environmental and self deaths have `killer = null` and count toward the
    victim's team deaths.
  - **Replay rejection** (mainly for broadcasts): a reading is accepted only while the game
    clock moves forward from the last accepted reading. Clock rewinds or repeats mark a
    `replay` gap.
  - **Segments**: a new segment at every swap and every round/attack boundary (FR-010).
    Segment kills come from kill events inside it, and objective gain from the difference in
    progress readings (data-model §2.3).
  - **Gaps**: time inside a map span with no HUD is a `gap`. Kills in a gap are unknown, so the
    map's kill totals are marked `incomplete`, which forces a scoreboard comparison and blocks
    `verified` unless the scoreboard agrees.

## R15. Verification engine and review workflow

- **Decision**:
  - The `reconcile` step builds, for each catalog map and each field in FR-016, one
    **Comparison** row across all available sources (video, Liquipedia, spreadsheet, OWTV).
    Outcomes and tolerances follow FR-017 (configurable).
  - Every `disagree` becomes a **Discrepancy** with a **stable ID**: hash of (map_id, field,
    subject), so it keeps its ID across rebuilds.
  - The provisional value follows FR-021 source priority and is shown as `provisional`.
  - **Decisions** (`data/raw/decisions/decisions.csv`, append-only) store the discrepancy ID,
    the values the researcher saw, the chosen source or corrected value, reason, who, and when.
    On rebuild, a decision applies only if the current source values still match the values it
    recorded. Otherwise it's marked `stale` and the discrepancy reopens (covers Liquipedia
    edits after review).
  - **Review CLI** (`owstudy-collect review`): goes through open discrepancies one at a time,
    showing all values, confidence, and a YouTube link that jumps to the time range
    (`&t=<s>`), then records the decision with one keypress plus a short reason. This is what
    makes SC-009 (< 2 min each) achievable.
  - The SC-004 audit (`owstudy-collect audit`) checks every reconciled value against its raw
    source or a decision. Any unexplained difference fails the audit (exit 1).
- **Alternatives considered**: Editing the reconciled CSV by hand (no audit trail, violates
  FR-001). A web UI (more to build, and the CLI with links is enough for ~100s of
  discrepancies).

## R16. Gold set and accuracy measurement (FR-022, SC-002)

- **Decision**: `gold init <map_id>` writes empty label templates for a map from its readings
  (players, expected segments) into `data/raw/gold/<map_id>/`: map winner, map number, mode, bans, the
  hero per player per segment with swap times, team kills, and attack results. The researcher
  fills them in while watching. `gold score` compares interpreted events to the labels and
  writes an accuracy table per field with the SC-002 thresholds. Gold set: 6 pilot maps, at
  least one per mode (Control, Escort, Hybrid, Push, Flashpoint), plus one extra Control map
  because Control is the most common mode. Gold maps come from different series and teams.
- **Rationale**: SC-002 thresholds are per field. Templates cut labeling time and keep labels
  in the same IDs as the output.

## R17. Broadcast VOD test (FR-007b) and pilot coverage

- **Finding**: The inventory shows only **25 of 51** pilot series (92 of 186 maps, 49%) have an
  ObsSojourn POV. The other 26 all have an official broadcast VOD linked on Liquipedia.
  **With POVs only, the pilot can't reach SC-001's 95% linked**, and SC-001 gates expansion
  (FR-023).
- **Decision**: The design supports a second video source type (`broadcast`) from the start:
  the same viewer with a broadcast HUD layout, replay rejection (R14) and downtime skipping
  (R3). The FR-007b test runs on 3 pilot series that have both a POV and a broadcast, using the
  POV readings as the answer key. It passes if replays are rejected (0 replayed kills accepted),
  downtime is skipped, and per-field accuracy is within SC-002. If it passes **and the
  researcher approves**, broadcasts fill the 26 gaps. If it doesn't, the researcher must decide
  whether SC-001 for the pilot is measured against "maps with an ObsSojourn POV" (a spec
  change). **Raised to the researcher as an open item.** It doesn't block the plan, because
  the architecture is the same either way.
- **Rationale**: Avoids discovering the coverage ceiling only after the pilot is finished.

## R18. Dependencies (constitution: additional libraries must be justified)

| Library | Why |
|---|---|
| `yt-dlp` | Only maintained, scriptable way to fetch the videos with resume and format selection (R2). |
| `av` (PyAV) | Exact PTS-based frame selection, bundled FFmpeg, no system install (R3). |
| `opencv-python-headless`, `numpy` | Cropping, template matching, color tests (R4). |
| `rapidocr-onnxruntime` (+ `onnxruntime`) | Local, pip-installable OCR, CPU, deterministic with fixed threads; no Tesseract install on Windows (R4). |
| `rapidfuzz` | Fuzzy name → alias matching (R7, R11). |
| `requests` | Liquipedia/OWTV retrieval with rate limiting and caching (R9, R10). |
| `openpyxl` | Reading the spreadsheet (R9). |
| `pandas`, `PyYAML` | Constitution default / shared with 001. |
| dev: `pytest`, `hypothesis` | Shared with 001. Property tests for run-length encoding round-trips and segment tiling. |

All are pinned in the shared `pyproject.toml` / `uv.lock` (the same package as feature 001,
under an optional `collect` extra so feature 001 doesn't need the video stack).
