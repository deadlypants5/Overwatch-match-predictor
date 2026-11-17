# Contract: storage layout and file schemas

## In short

Where every file lives and what columns it has. `data/raw/` is never edited.
`data/interim/` can be deleted and rebuilt with `owstudy-collect build`, except the hand-curated
files marked below. `data/processed/` holds exports. Videos never go in the repo.

All tables are UTF-8 CSV with a header, `,` separator, `\n` line endings, empty cell = missing,
rows sorted by the listed key, floats written with fixed decimals (times 0.01 s, confidences
0.001, progress 0.0001). Entity semantics: [data-model.md](../data-model.md).

```text
data/
├── raw/                                         # immutable (FR-001)
│   ├── reference/
│   │   ├── spreadsheet/<YYYY-MM-DD>/            # sheet_series.csv, sheet_maps.csv, sheet_bans.csv, snapshot.json
│   │   ├── liquipedia/<YYYY-MM-DD>/             # responses/*.json, lp_series.csv, lp_maps.csv, lp_lineups.csv, snapshot.json
│   │   ├── owtv/<YYYY-MM-DD>/                   # responses/*, owtv_map_player_stats.csv, snapshot.json
│   │   └── youtube/<YYYY-MM-DD>/                # channel video list (obssojourn_videos.json), snapshot.json
│   ├── observations/<video_id>/<extraction_key>/
│   │   ├── run.json                             # ExtractionRun
│   │   ├── readings.csv                         # all non-kill readings
│   │   ├── kills.csv                            # kill-feed readings
│   │   └── MANIFEST.sha256                      # hashes of the files above (immutability check)
│   ├── gold/<map_id>/labels.csv
│   └── decisions/decisions.csv                  # append-only
├── interim/                                     # rebuildable; safe to delete and `build`
│   ├── entities/  teams.csv players.csv heroes.csv maps.csv aliases.csv (hand-curated) aliases_proposed.csv icons/<hero_id>/*.png
│   ├── catalog/   series.csv maps.csv lineups.csv video_links.csv map_spans.csv patch_day_series.csv
│   ├── events/    hero_intervals.csv kills.csv objective.csv attacks.csv gaps.csv results.csv
│   ├── reconciled/ maps.csv segments.csv segment_heroes.csv bans.csv attacks.csv field_sources.csv
│   ├── verify/    comparisons.csv discrepancies.csv
│   ├── runs/      state.csv
│   ├── inventory/ (existing US0 outputs)
│   ├── probes/    hud/ owtv/
│   └── reports/   gold_accuracy.csv broadcast_test.md snapshot_diff_<source>_<date>.csv
└── processed/collection/<export_id>/            # see export.md
```

`aliases.csv`, `icons/` and the HUD layouts in `configs/` are curated by hand and committed,
even though they sit in interim. `build` never overwrites them. Video files never enter
`data/` (FR-007).

## Key schemas

### `observations/.../readings.csv` — key `(reading_type, slot, ts_start)`

```csv
video_id,run_id,extractor_version,reading_type,slot,ts_start,ts_end,clock_start,clock_end,value,conf_min,conf_mean,frames,method
dQw4w9WgXcQ,r20261120-0001,0.1.0,hero,L2,612.50,705.00,10.00,102.50,tracer,0.912,0.957,186,icon_ncc
dQw4w9WgXcQ,r20261120-0001,0.1.0,gap,,1820.00,1874.50,,,no_hud,1.000,1.000,110,anchor
```

### `observations/.../kills.csv` — key `(ts_start, side, victim_slot)`

```csv
video_id,run_id,extractor_version,ts_start,ts_end,clock_start,side,killer_slot,killer_name_text,killer_hero,ability_icon,victim_slot,victim_name_text,victim_hero,env_or_self,conf_min,conf_mean,frames
```

### `run.json`

```json
{"run_id": "r20261120-0001", "video_id": "...", "extraction_key": "a1b2c3d4",
 "extractor_version": "0.1.0", "layout_id": "owcs2026_pov_v1", "icon_lib_hash": "...",
 "ocr_model_hash": "...", "sampling": {"fps": 2}, "video_sha256": "...", "format_id": "137",
 "resolution": "1920x1080", "started_at": "2026-11-20T10:00:00Z", "finished_at": "...",
 "frames_sampled": 0, "frames_with_hud": 0, "outcome": "ok", "error": null}
```

### `runs/state.csv` — key `(video_id, extraction_key)`

`video_id,extraction_key,state,attempts,last_error,updated_at` (state per data-model §3.1).

### `catalog/video_links.csv` — key `video_id`

`video_id,series_id,status,link_confidence,role,pov_player_id,pov_team_id,confirmed,note`

### `catalog/map_spans.csv` — key `(video_id, ts_start)`

`video_id,map_id,ts_start,ts_end,status`

### `reconciled/field_sources.csv` — key `(map_id, table, field, subject)`

`map_id,table,field,subject,value,value_source,provisional,raw_ref` where `raw_ref` points to the
reading (`obs:<video>/<key>#<type>:<slot>@<ts>`) or reference record
(`ref:<source>/<snapshot>#<locator>`). This is the table `audit` checks (SC-004) and the
provenance export uses (SC-003).

### `verify/comparisons.csv` — key `(map_id, field, subject)`

`map_id,series_id,field,subject,video,liquipedia,spreadsheet,owtv,outcome,tolerance,note`

### `verify/discrepancies.csv` — key `discrepancy_id`

`discrepancy_id,map_id,kind,field,subject,values_json,provisional_value,provisional_source,ts_video_from,ts_video_to,video_id,status,decision_id`

### `raw/decisions/decisions.csv` — append order

`decision_id,discrepancy_id,field,seen_values_json,action,value,reason,decided_by,decided_at`

### `raw/gold/<map_id>/labels.csv`

`map_id,field,subject,value,ts_video,labeled_by,labeled_at`
