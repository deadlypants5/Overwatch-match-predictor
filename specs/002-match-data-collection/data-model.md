# Data Model: Match Data Collection & Verification

**Feature**: `002-match-data-collection` | **Date**: 2026-11-15 | **Plan**: [plan.md](./plan.md)

This covers entities, relationships, rules and state transitions. Column-level file schemas are
in [contracts/storage-layout.md](./contracts/storage-layout.md). The export format is feature 001's
[input-schema.md](../001-strength-metrics/contracts/input-schema.md), mapped in
[contracts/export.md](./contracts/export.md).

```text
                 RAW (immutable)                         INTERIM (rebuildable)                   PROCESSED
 ┌──────────────────────────────┐        ┌──────────────────────────────────────────┐   ┌────────────────┐
 │ ReferenceSnapshot ─┐         │        │ Entity + Alias                           │   │ Export         │
 │   ReferenceRecord  ├─────────┼──────▶ │ CatalogSeries ─< CatalogMap               │   │  (001 input +  │
 │                    │         │        │      │               │                   │   │   summary,     │
 │ SourceVideo ───────┼─ link ──┼──────▶ │ VideoLink      VideoMapSpan              │   │   provenance)  │
 │ ExtractionRun ─< Reading     │        │                      │                   │   │                │
 │ GoldLabel                    │        │ InterpretedEvent (swap, kill, attack…)   │──▶│                │
 │ ReviewDecision               │──────▶ │ ReconciledMap ─< Segment, SegmentHero,   │   │                │
 └──────────────────────────────┘        │   Ban, Attack; Comparison; Discrepancy   │   └────────────────┘
                                          └──────────────────────────────────────────┘
```

Rule for every arrow: interim and processed data is a **pure function** of raw data + configs +
decisions (SC-008). Nothing in raw is ever rewritten (FR-001).

---

## 1. Raw layer

### 1.1 ReferenceSnapshot / ReferenceRecord (FR-004)

- **ReferenceSnapshot**: one retrieval of one source: `source` (`spreadsheet` | `liquipedia` |
  `owtv`), `retrieved_at` (UTC), tool version, raw response files (wikitext, JSON, xlsx copy
  hash), and page revision IDs where available.
- **ReferenceRecord**: one row a source gives about a series, map, map-player or lineup,
  **values exactly as given** (names not yet resolved), plus `snapshot_id`, `locator`
  (sheet+row, page+revision+section, URL) and `record_type` (`series`, `map`, `lineup`,
  `map_player_stats`, `ban`).
- Rules: a newer snapshot never edits an older one. Reconcile uses the **latest** snapshot per
  source unless the config pins one. A snapshot diff report lists records that changed.

### 1.2 SourceVideo

`video_id`, `title`, `channel`, `kind` (`pov` | `broadcast`), `upload_date`, `duration_s`,
`pov_player_text` (from title), `parsed_team_a/b_text`, `event_text`, and the snapshot it was
listed in. Immutable listing data. Linking lives in interim (§2.2).

### 1.3 ExtractionRun (FR-002, FR-012, FR-013)

`run_id`, `video_id`, `extraction_key` (hash of extractor version + HUD layout + icon library +
OCR model + sampling settings, research R13), `extractor_version`, `layout_id`, `started_at`,
`finished_at`, `video_sha256`, `format_id`, `resolution`, `frames_sampled`, `frames_with_hud`,
`outcome` (`ok` | `failed`), `error`. Stored as `run.json` next to the readings.

### 1.4 Reading (the raw observation)

One run-length-encoded stretch in which one HUD region showed one value (research R6).

| Field | Notes |
|---|---|
| `video_id`, `run_id`, `extractor_version` | Provenance (FR-002). The extraction date comes from `run_id` → `run.json`. |
| `reading_type` | `map_info`, `team_name`, `player_name`, `hero`, `kill`, `objective`, `game_clock`, `attack_clock`, `round_state`, `ban`, `result`, `gap`, `hud_layout` (FR-003). |
| `slot` | Region instance: `L1..L5`, `R1..R5` (left/right team bar), `left`/`right`, or empty. |
| `ts_start`, `ts_end` | Video seconds (first and last sampled frame in the run). |
| `clock_start`, `clock_end` | Game clock in seconds when visible, otherwise empty. |
| `value` | Raw recognized value: OCR text, hero slug, percent, `mm:ss`, etc. Kills use structured fields instead (below). |
| `conf_min`, `conf_mean`, `frames` | Confidence over the run (FR-011). |
| `method` | `icon_ncc`, `ocr_rapid`, `bar_px`, `anchor`, … |

**Kill readings** add: `killer_slot`, `killer_name_text`, `killer_hero`, `victim_slot`,
`victim_name_text`, `victim_hero`, `ability_icon`, `side` (`left`/`right`, by row color),
`env_or_self` (bool). `ts_start`/`ts_end` = first/last seen.

Rules: a frame with confidence below `low_conf_threshold` always starts its own run, so
low-confidence stretches stay visible. Readings are sorted `(reading_type, slot, ts_start)`.
Two runs with the same `extraction_key` on the same file must produce identical readings.

### 1.5 GoldLabel (FR-022)

Hand labels per gold map: `map_id`, `field` (`winner`, `map_number`, `mode`, `ban`, `hero_segment`,
`swap_time`, `team_kills`, `attack`), `subject` (player/team/attack), `value`, `ts_video`,
`labeled_by`, `labeled_at`. Written once by the researcher, never by tools after `gold init`.

### 1.6 ReviewDecision (FR-020)

`decision_id`, `discrepancy_id`, `field`, `seen_values` (each source's value at review time,
JSON), `action` (`accept_source:<name>` | `correct`), `value` (chosen/corrected),
`reason`, `decided_by`, `decided_at`. Append-only. A later decision for the same discrepancy
replaces the earlier one in effect, but both stay in the file.

---

## 2. Interim layer

### 2.1 Entities and aliases (FR-006)

- **Team, Player, Hero, Map, Mode, Patch**: `stable_id`, display name, attributes (map → mode;
  patch → `live_from` UTC; player → Liquipedia page).
- **Alias**: `entity_type`, `alias` (normalized: case-folded, whitespace collapsed), `stable_id`,
  `valid_from`, `valid_to`, `source` (`liquipedia`, `sheet_abbr`, `manual`). Hand-curated file.
  Tools write only **AliasProposal** rows (`alias`, candidate `stable_id`, fuzzy score, where
  seen). Rules: no overlapping validity for the same alias/type. A name near an existing alias
  but not exact is proposed, never auto-added.

### 2.2 Catalog and linking (FR-008)

- **CatalogSeries**: `series_id` (stable, from the Liquipedia match key), `region`, `stage`,
  `phase`, `best_of`, `start_utc`, `local_date`, `tz`, `team_a_id`, `team_b_id` (Liquipedia
  order), `score_a`, `score_b`, `status` (`played` | `forfeit` | `walkover`), `sources`
  (which snapshots list it), `in_pilot`.
- **CatalogMap**: `map_id` = `<series_id>-m<n>`, `map_number`, `map_id_ref` (map entity),
  `mode_id`, `winner` (`a`/`b`/`draw`, as references give it), `patch_id`, `status`
  (`played` | `clash_excluded` | `forfeit`).
- **Lineup**: `series_id`, `team_id`, `player_id`, `source`, used for roster checks (series
  level; per-map rosters come only from the video).
- **VideoLink**: `video_id` → `series_id`, `link_confidence` (`high`/`medium`/`low`),
  `pov_team_id`, `pov_player_id`, `role` (`primary` | `cross_check` | `unused` | `duplicate`),
  `confirmed` (bool, set after extraction from HUD names, research R7), `status` (`linked` |
  `unmatched` | `not_owcs_2026` | `duplicate`).
- **VideoMapSpan**: `video_id`, `map_id`, `ts_start`, `ts_end`, `status` (`ok` |
  `excluded_remake` | `unaligned`).

### 2.3 Interpreted events (derived from readings, research R14)

- **HeroInterval**: `map_id`, `player_id`, `team_id`, `hero_id`, `game_start_s`, `game_end_s`,
  `conf`, flags (`short_segment`, `low_conf`).
- **KillEvent**: `map_id`, `game_s`, `killer_player_id?`, `killer_hero?`, `victim_player_id`,
  `victim_hero`, `victim_team_id`, `env_or_self`, `ts_video`, `conf`, flags (`possible_replay`,
  `low_conf`).
- **ObjectiveSample**: `map_id`, `game_s`, `team_id`, `progress` (0–1 normalized, below).
- **AttackRecord**: `map_id`, `attack_order`, `attacking_team_id`, `obj_progress`,
  `attack_clock_s`, `time_remaining_s` (asymmetric modes; matches 001 Attack).
- **Gap**: `map_id`, `game_start_s?`, `ts_start`, `ts_end`, `kind` (`no_hud`, `replay`,
  `pause`). Any gap inside a map sets `kills_incomplete` on that map.
- **MapResultObs**: winner side and final score as read from the HUD.

**Game time** is seconds since the map's first HUD frame with a running clock, with gaps
counted at clock time (the clock is the authority, so pauses don't add time).

**Objective normalization per mode** (feature 001 expects 0–1 per mode, 001 research R8/N6):

| Mode | `obj_x` for the map | Segment gain |
|---|---|---|
| Control | mean over rounds played of team x's final capture percent (0–1) | increase in x's percent during the segment ÷ rounds played |
| Push | x's furthest robot distance ÷ map's full push distance | increase in x's furthest distance ÷ full distance |
| Flashpoint | (points x captured + x's partial progress on the last contested point) ÷ points played | increase in that sum during the segment ÷ points played |
| Escort / Hybrid | — (attacks.csv: `obj_progress` = fraction of total route, checkpoints included) | attacker's progress gained in the segment |

So segment gains sum to the map total, as 001 requires.

**Segments** (FR-010): boundaries = union of all HeroInterval starts/ends and round/attack
boundaries within the map span. For each segment: kills per team = number of opponent
deaths (`victim_team_id` = opponent, including environmental/self deaths) with `game_s` in
`[start, end)`, plus objective gain. Segments tile `[0, map_end)` with no gaps. A Gap doesn't
split segments, but marks them `kills_incomplete`.

### 2.4 Player-on-hero aggregates (FR-024a)

Built in export from reconciled segments, segment heroes and kill events
(contracts/export.md §Analysis tables):

- **KillEvent (exported)**: the interpreted KillEvent with stable IDs, plus `kill_no`,
  `segment_no` and `attack_order` so it joins to segments.
- **PlayerHeroMap**: one per `(map, player, hero)`. It sums the segments where the player was on
  the hero: time, team kills and deaths, own kills and deaths, objective for and against (attack
  and defense split for Escort/Hybrid), incomplete seconds.
- **PlayerHeroSummary**: one per `(player, hero, mode)` plus `mode = all`, with totals and
  per-10-minute rates over the exported maps. It's descriptive only and spans the whole
  period, so it isn't time-safe as a feature. 001 provides pre-map values.

Team kills and objective progress in a segment are credited in full to **every** player on the
team during that segment (shared credit, like 001's time weighting). Own kills and deaths are
the player's personal kill-feed entries.

### 2.5 Reconciliation

- **ReconciledMap**: one per CatalogMap with every field 001 needs (maps, segments,
  segment_heroes, bans, attacks), each value tagged with `value_source` (`video`, `liquipedia`,
  `spreadsheet`, `owtv`, `decision:<id>`) and `provisional` (bool). Plus `verification_status`
  (below) and `primary_video_id`, `extraction_key`.
- **Comparison** (FR-016/017): `map_id` (or `series_id`), `field`, `subject`, `values` per
  source, `outcome` (`agree` | `agree_within_tolerance` | `disagree` | `single_source`),
  `tolerance_used`, `note`.
- **Discrepancy** (FR-018): `discrepancy_id` = hash(map_id, field, subject), `values`,
  `provisional_value` + `provisional_source` (FR-021 priority), `ts_video_from`, `ts_video_to`,
  `status` (`open` | `resolved` | `stale`), `decision_id?`, `kind` (`roster`, `scoreboard`,
  `winner`, `ban`, `date`, `map_order`, `link`, `low_confidence`, `mode`).

Low-confidence values in required fields (below `low_conf_threshold`) produce a
`low_confidence` discrepancy even with no second source, so the researcher sees them
(FR-011).

**FR-021 provisional priority**: Liquipedia (dates, teams, rosters, series result, map winners)
→ spreadsheet (bans, map names; Liquipedia cross-check) → OWTV (scoreboard) → video (heroes, segment timing, objective, attacks).

---

## 3. State transitions

### 3.1 Video processing state (`data/interim/runs/state.csv`, FR-012)

```text
pending ──download──▶ downloaded ──extract ok──▶ extracted ──delete──▶ deleted
   │                      │                          ▲
   │                      └──extract fail──▶ failed ─┘ (retry)
   └── key changes or --force: extracted/deleted ──▶ pending (re-download)
```

`extracted` is keyed by `(video_id, extraction_key)`. A new key makes every video `pending`
for that key, and old readings remain.

### 3.2 Discrepancy

```text
(created by reconcile) open ──review decision──▶ resolved
                         ▲                          │
                         └──── source values change ─┴──▶ stale ──(treated as open)
```

No automatic transition to `resolved` (FR-020).

### 3.3 Map verification status (FR-019)

Computed on every rebuild, in this order:

1. `conflict`: any open or stale discrepancy on the map.
2. `unverified`: no field has a second source (e.g., video only, no references).
3. `partial`: no conflicts, but at least one required field is `single_source` or
   provisional (including `kills_incomplete` without scoreboard agreement).
4. `verified`: every compared field agrees (or agrees within tolerance), no open
   discrepancies, and no low-confidence values in required fields.

Export mapping to 001: `verified` → `verified`; the other three → `unverified` (with the full
status in the provenance sidecar, contracts/export.md).

### 3.4 Catalog map → export

```text
played + linked + extracted + reconciled ──▶ exported (if status allowed by --include)
otherwise excluded with reason: no_replay | forfeit | clash | remake_only | open_conflict |
                                 unverified_excluded | not_processed
```

Every catalog map appears in the export summary, exported or with its reason (FR-025).

---

## 4. Validation rules (checked by `owstudy-collect validate`)

- Every Reading references an existing `run.json`. Every ReconciledMap references existing
  catalog, readings (by key) and snapshots.
- No `(video_id, extraction_key)` folder is modified after its `run.json` says `ok` (checked
  by a stored hash of the folder's files).
- Segments tile each map; 10 SegmentHero rows per segment; kill totals = sum of segments.
- Every alias resolves to exactly one stable ID per date.
- **Audit (SC-004)**: each reconciled value equals its `value_source` raw value, or a decision
  covers it.
- The export passes feature 001's `owstudy-strength validate` (SC-007).
