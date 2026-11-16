# Contract: export to feature 001 (plus analysis tables)

## In short

What an export contains:

- **`input/`**: exactly the files feature 001 reads.
- **`tables/`**: extra analysis tables (every kill; time, kills and deaths per player per hero).
  These are descriptive only and must not be used as pre-map features.
- **`summary/`**: coverage, quality, and every map that wasn't exported, with the reason.
- **`provenance/`**: for each map, which video, timestamps and sources it came from.

```text
data/processed/collection/<export_id>/          # export_id = <YYYYMMDD>-<short hash of inputs>
├── input/                                      # exactly feature 001's input directory
│   ├── maps.csv  segments.csv  segment_heroes.csv  bans.csv  attacks.csv
│   └── entities/aliases.csv
├── tables/                                     # extra analysis tables (FR-024a); outside input/ so 001's validator ignores them
│   ├── kill_events.csv                         # one row per kill
│   ├── player_hero_map.csv                     # one row per map × player × hero
│   └── player_hero_summary.csv                 # one row per player × hero × mode (+ mode "all"), over the exported maps
├── summary/
│   ├── coverage.csv                            # per region-stage (US4 scenario 2)
│   ├── excluded_maps.csv                       # every non-exported catalog map + reason (FR-025)
│   └── quality.csv                             # open discrepancies by kind, gold accuracy, link checks
├── provenance/
│   ├── map_provenance.csv                      # per map: video(s), spans, extraction_key, status
│   └── field_sources.csv                       # copy of reconciled/field_sources.csv for exported maps
└── manifest.json                               # inputs hashed (snapshots, readings keys, decisions, configs), tool version, include setting
```

## Field mapping (001 `input-schema.md`)

| 001 field | Filled from |
|---|---|
| `map_id`, `series_id`, `map_number` | Catalog (`<series_id>-m<n>`). |
| `date`, `series_start` | Liquipedia: event-local date; UTC start time (research R11). |
| `patch_id` | `patches.yaml` by series start. |
| `map_name`, `mode_id` | Catalog map entity. Clash maps aren't exported (reason `clash`). |
| `team_a_id`, `team_b_id` | Catalog (Liquipedia order). |
| `winner` | Reconciled map winner. |
| `kills_a`, `kills_b` | Sum of segment kills (deaths of the opposing team, including environmental). Left empty if `kills_incomplete` and not resolved. |
| `obj_a`, `obj_b` | Symmetric modes only, data-model §2.3. |
| `verification` | `verified` if status `verified`, otherwise `unverified`. |
| `source_ref` | `yt:<primary video>@<map span start>`. |
| segments / segment_heroes | Interpreted segments; player IDs via aliases. |
| bans | Reconciled bans (spreadsheet priority). |
| attacks | Interpreted AttackRecords (Escort/Hybrid). |
| `entities/aliases.csv` | Hand-curated aliases (team, player, hero types only). |

`map_provenance.csv`:
`map_id,verification_status,primary_video_id,cross_check_video_id,ts_start,ts_end,extraction_key,confirming_sources,open_discrepancies`.

`excluded_maps.csv`: `map_id,series_id,region_stage,reason` with reason in
`no_replay | forfeit | clash | remake_only | open_conflict | unverified_excluded | not_processed`.

## Analysis tables (`tables/`, FR-024a)

These cover the same maps as `input/` (same `--include` setting) and use the same stable IDs.
They're **descriptive**: `player_hero_summary.csv` uses every exported map, including later
ones, so it must not be joined onto a map as a prediction feature (Constitution II). Pre-map
values come from feature 001.

### `kill_events.csv` — key `(map_id, kill_no)`

```csv
map_id,kill_no,game_s,segment_no,attack_order,killer_team_id,killer_player_id,killer_hero_id,victim_team_id,victim_player_id,victim_hero_id,env_or_self,video_id,ts_video,conf,flags,verification
m0001,1,42.50,1,,T1,P02,tracer,T2,P17,zenyatta,false,abc123,812.50,0.941,,verified
m0001,2,61.00,1,,,,,T1,P04,lucio,true,abc123,831.00,0.902,,verified
```

- `kill_no`: 1, 2, … in game-time order (ties broken by video time, then victim slot).
- `segment_no` / `attack_order`: the segment (and attack, for Escort/Hybrid) the kill falls in,
  so it joins to `input/segments.csv`.
- Environmental or self deaths: `env_or_self = true`, killer columns empty. They still count
  toward the killing side's team total (`kills_a`/`kills_b`) because the scoreboard counts them
  as deaths.
- `flags`: `;`-separated from `low_conf`, `possible_replay`, `name_unresolved`.
- `verification`: the map's export value (`verified` / `unverified`).
- Kills inside a gap don't exist here. Those segments are flagged in `player_hero_map.csv`.

### `player_hero_map.csv` — key `(map_id, player_id, hero_id)`

One row for every hero a player was on during a map. All values come from the segments where
that player was on that hero.

| Column | Meaning |
|---|---|
| `map_id`, `series_id`, `date`, `patch_id`, `map_name`, `mode_id` | From `maps.csv`. |
| `team_id`, `opponent_id`, `player_id`, `hero_id` | |
| `won_map` | 1 if the player's team won the map, 0 if it lost, empty for a draw. |
| `segments` | Number of segments on this hero. |
| `time_s` | Seconds on this hero (sum of segment lengths). |
| `time_share` | `time_s` ÷ map length. |
| `team_kills` | The team's kills in those segments (opponent deaths, environmental included). |
| `team_deaths` | The team's deaths in those segments (the opponent's kills). |
| `own_kills` | Kill-feed final blows by this player on this hero. |
| `own_deaths` | This player's deaths on this hero. |
| `obj_for` | Objective progress the team gained in those segments. Normalized per mode (data-model §2.3). For Escort/Hybrid, this counts only segments where the team attacked. |
| `obj_against` | Progress the opponent gained in those segments (for Escort/Hybrid, only segments where the team defended). |
| `attack_time_s`, `defense_time_s` | Escort/Hybrid only: time on this hero while attacking and while defending. |
| `defense_clock_used` | Escort/Hybrid only: the share of the opponent's attack clock that ran down during this hero's defending segments (0–1, the defender points used in 001 research R8). |
| `incomplete_s` | Seconds of those segments marked `kills_incomplete` (a gap). Kill counts are lower bounds when this is > 0. |
| `low_conf_segments` | Segments where this player's hero reading was low confidence. |
| `verification` | The map's export value. |

### `player_hero_summary.csv` — key `(player_id, hero_id, mode_id)`

Totals of `player_hero_map.csv` over all exported maps. There is one row per mode and one
`mode_id = all` row. On the `all` row the objective columns are empty, because progress isn't
comparable across modes.

| Column | Meaning |
|---|---|
| `player_id`, `hero_id`, `mode_id` | |
| `team_ids` | `;`-separated teams the player was on while playing this hero (rosters change). |
| `first_date`, `last_date` | Date range covered. |
| `maps`, `maps_won` | Maps with any time on this hero, and how many the team won. Not a hero win rate: a player can swap off a hero mid-map. |
| `time_s` | Total seconds. |
| `team_kills`, `team_deaths`, `own_kills`, `own_deaths` | Totals. |
| `team_kills_per10`, `team_deaths_per10`, `own_kills_per10`, `own_deaths_per10` | Per 10 minutes on the hero. |
| `team_kill_diff_per10` | `team_kills_per10 − team_deaths_per10`. |
| `obj_for`, `obj_against`, `obj_for_per10`, `obj_against_per10` | Per mode only. |
| `defense_clock_used_mean` | Escort/Hybrid only: time-weighted mean over defending segments. |
| `incomplete_s` | Total incomplete seconds. |
| `verified_maps` | Number of the maps that are `verified`. |

Rates are empty when `time_s < 60`, so a few seconds on a hero can't produce extreme rates.
The 60 s cut-off is set by `export.summary_min_time_s` in the config.

### Consistency checks (run by `export`; exit 1 on failure)

- Per map, for each team: `kill_events` rows with the opponent as victim = `maps.csv` kills for
  that team.
- Per map and player: `Σ time_s` over that player's heroes = map length.
- Per map, team and hero row: `team_kills` = kills in `kill_events` whose `segment_no` is one of
  that player's segments on that hero.
- Per map and team: `Σ own_kills` over the team's players + the opponent's `env_or_self` deaths
  = the team's kills.
- `player_hero_summary` totals = sums of `player_hero_map`.

Acceptance: `owstudy-strength validate data/processed/collection/<id>/input` exits 0 (SC-007).
Rebuilding the export from the same raw layer, configs and decisions gives byte-identical files
except `manifest.json`'s `created_at` (SC-008).
