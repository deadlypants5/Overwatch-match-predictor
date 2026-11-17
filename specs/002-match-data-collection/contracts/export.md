# Contract: export to feature 001 (plus analysis tables)

## In short

What an export contains:

- **`input/`**: exactly the files feature 001 reads.
- **`tables/`**: three analysis tables (one row per map, one per player hero interval, one per
  event) plus name lookups. These are descriptive only and must not be used as pre-map features.
- **`summary/`**: coverage, quality, and every map that wasn't exported, with the reason.
- **`provenance/`**: for each map, which video, timestamps and sources it came from.

```text
data/processed/collection/<export_id>/          # export_id = <YYYYMMDD>-<short hash of inputs>
├── input/                                      # exactly feature 001's input directory
│   ├── maps.csv  segments.csv  segment_heroes.csv  bans.csv  attacks.csv
│   └── entities/aliases.csv
├── tables/                                     # extra analysis tables (FR-024a); outside input/ so 001's validator ignores them
│   ├── maps.csv                                # one row per map: teams, players, bans, winner, kills, objective
│   ├── hero_intervals.csv                      # one row per player stint on a hero
│   ├── events.csv                              # one row per event (kills, swaps, objective, rounds, gaps)
│   └── players.csv  teams.csv  heroes.csv      # ID → display name
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

Three main tables plus name lookups. Each fact is stored once: kills live only in `events.csv`,
and every per-player total can be added up from `hero_intervals.csv`. All tables cover the same
maps as `input/` (same `--include` setting), use stable IDs rather than names, and hold every
map in one file (filter by `map_id`). They're descriptive data, not pre-map features
(Constitution II); pre-map values come from feature 001.

### `maps.csv` — key `map_id`

One row per map: the overall result.

| Column | Meaning |
|---|---|
| `map_id`, `series_id`, `region_stage`, `date`, `patch_id`, `map_number`, `map_name`, `mode_id` | From the catalog. |
| `team_a_id`, `team_b_id` | Liquipedia order. |
| `winner` | `a`, `b` or `draw`. |
| `bans_a`, `bans_b` | Hero IDs each team banned on this map, `;`-separated. |
| `players_a`, `players_b` | Player IDs who played any time on this map for each team, `;`-separated, sorted. |
| `kills_a`, `kills_b` | Team kills (opponent deaths, environmental and self deaths included). Empty if the map has an unresolved gap. |
| `obj_a`, `obj_b` | Total objective progress per team, normalized per mode (data-model §2.3). Escort/Hybrid: the sum of the team's attack progress (fraction of the route, checkpoints included). |
| `map_length_s` | Game seconds from map start to map end. |
| `kills_incomplete` | `true` if a gap hid part of the kill feed (kill counts are then lower bounds). |
| `verification` | `verified` / `unverified`. |

### `hero_intervals.csv` — key `(map_id, player_id, interval_no)`

One row per stint of one player on one hero. A new interval starts when the player swaps
hero, when a round starts, and (Escort/Hybrid) when the team switches between attacking and
defending. So on Escort/Hybrid each interval is entirely attack or entirely defense. Dying
doesn't end an interval. Each player's intervals tile the map with no gaps or overlaps.

**Short swaps are "transitioning".** A stint on a hero lasting less than
`export.min_interval_s` (default 20 s) isn't counted as playing that hero. A stint is measured
from when it starts (a swap onto the hero, or a round or attack starting) to when it ends (a
swap off, or the round, attack or map ending), so a swap made just before a round ends or the
teams switch sides counts as a transition too. It becomes a **transition** interval:
`interval_type = transition`, `hero_id` empty, and the heroes passed through listed in
`transition_heroes`. Several short stints in a row are lumped into one transition interval.
Its time, kills, deaths and objective are counted on the transition row, not on any hero.
Round starts and attack/defense switches still split intervals as usual, transitions included.
`events.csv` still records every swap with the hero actually played, and feature 001's
`segment_heroes` keeps the hero actually on screen.

Example: Lúcio 0–95 s, Mercy 95–107 s, Brigitte 107–115 s, Lúcio 115–300 s gives three
intervals: Lúcio 0–95, transition 95–115 (`transition_heroes = mercy;brigitte`), Lúcio 115–300.

| Column | Meaning |
|---|---|
| `map_id`, `team_id`, `opponent_id`, `player_id` | |
| `interval_type` | `hero` or `transition` (see above). |
| `hero_id` | The hero played; empty on transition intervals. |
| `interval_no` | 1, 2, … per player in time order. |
| `round_no` | Round (Control), attack (Escort/Hybrid) or point (Flashpoint) number; empty for Push. |
| `side` | `attack` / `defend` on Escort/Hybrid; empty on other modes. |
| `start_s`, `end_s`, `time_s` | Game seconds; `time_s = end_s − start_s`. |
| `team_kills`, `team_deaths` | Kills by and deaths of the player's team during `[start_s, end_s)`. |
| `own_kills`, `own_deaths` | This player's final blows and deaths during the interval. |
| `obj_for`, `obj_against` | Objective progress gained by the team and by the opponent during the interval (same units as `obj_a`/`obj_b`). On Escort/Hybrid, attack intervals only have `obj_for` and defense intervals only `obj_against`; the other is 0. |
| `incomplete_s` | Seconds of the interval hidden by a gap. Kill counts are lower bounds when > 0. |
| `transition_heroes` | Transition intervals only: the heroes passed through, `;`-separated in time order. |
| `low_conf` | `true` if the hero reading for this interval was low confidence. |
| `verification` | The map's export value. |

Team kills and objective progress are credited in full to every player on the team during the
interval (shared credit, like 001's time weighting).

### `events.csv` — key `(map_id, event_no)`

Everything that happened on a map, in time order. The `actor_*` columns say who did it; the
`target_*` columns say who it happened to.

| Column | Meaning |
|---|---|
| `map_id`, `event_no` | `event_no` 1, 2, … in game-time order (ties: video time, then the order of event types below, then slot). |
| `game_s`, `ts_video` | Game seconds, and the timestamp in the primary video (`provenance/map_provenance.csv` names the video). |
| `event_type` | `map_start`, `round_start`, `hero_swap`, `kill`, `objective`, `attack_start`, `attack_end`, `gap_start`, `gap_end`, `round_end`, `map_end`. |
| `actor_team_id`, `actor_player_id`, `actor_hero_id` | Killer (`kill`); the player and their new hero (`hero_swap`); the team that made progress (`objective`) or is attacking (`attack_*`). |
| `target_team_id`, `target_player_id`, `target_hero_id` | Victim (`kill`). |
| `value` | `objective`: the team's progress so far (same units as `obj_a`); `hero_swap`: the previous hero ID; `round_*`/`attack_*`: the round or attack number; `gap_*`: the gap kind (`no_hud`, `replay`, `pause`). |
| `env_or_self` | `kill` only: `true` for environmental or self deaths (killer columns empty). These still count toward the other team's kills, because the scoreboard counts them as deaths. |
| `conf`, `flags` | Reading confidence; `flags` `;`-separated from `low_conf`, `possible_replay`, `name_unresolved`. |

`objective` events are written each time a team's progress rises by at least
`export.objective_event_step` (default 0.01) and at every capture or checkpoint, so progress over
time can be plotted without storing every frame. Kills inside a gap aren't known and don't appear.

### `players.csv`, `teams.csv`, `heroes.csv` — key `*_id`

Turn IDs back into names: `player_id,display_name,liquipedia_page`; `team_id,display_name`;
`hero_id,display_name,role`.

### Consistency checks (run by `export`; exit 1 on failure)

- Per map and team: `kill` events with the opponent as target = that team's `kills_*` in `maps.csv`.
- Per map and player: intervals tile `[0, map_length_s)`, so `Σ time_s` = `map_length_s`.
- Per interval: `team_kills`, `team_deaths`, `own_kills` and `own_deaths` equal the `kill`
  events in `[start_s, end_s)`.
- Every `hero` interval comes from a hero stint of at least `min_interval_s`; every
  `transition` interval is made only of shorter stints, and no two transition intervals are
  next to each other within a round.
- Per map and player: `Σ obj_for` over the player's intervals = the team's `obj_*` in `maps.csv`.
- Per map and team: `Σ own_kills` over the team's players + the opponent's `env_or_self` deaths
  = the team's kills.
- Every `players_*` ID has at least one interval on that map, and every interval's player is
  listed in `players_*`.

Acceptance: `owstudy-strength validate data/processed/collection/<id>/input` exits 0 (SC-007).
Rebuilding the export from the same raw layer, configs and decisions gives byte-identical files
except `manifest.json`'s `created_at` (SC-008).
