# Contract: configuration files

## In short

Every setting the tool reads, with its default. There are four files:

- **`default.yaml`**: thresholds, tolerances, scope, download limits. Shared and committed.
- **`local.yaml`**: your machine's settings (cache folder, contact for the User-Agent, terms
  acknowledgement). Not committed.
- **`patches.yaml`**: 2026 patch go-live times, filled in by you (task T030).
- **`hud/*.yaml`**: where each HUD element sits on screen, one file per HUD layout.

All under `configs/collect/`, version-controlled (Constitution VI). Unknown keys are an error
(exit 2). Local secrets and machine-specific values (User-Agent contact, cache path, terms
acknowledgement) go in `configs/collect/local.yaml`, which is gitignored and merged on top.

## `default.yaml`

```yaml
scope:
  pilot: "Asia/Stage 1/Korea"
  approved: ["Asia/Stage 1/Korea"]      # FR-023: expansions added here one at a time

video:
  source_kinds: [pov]                   # add "broadcast" only after FR-007b test + approval
  povs_per_series: 1                    # 2 = also a cross-check POV from the other team
  format: "bv*[vcodec^=avc1][height<=1080]/bv*[height<=1080]"
  cache_max_videos: 2
  sleep_between_downloads_s: [5, 15]
  rate_limit: "8M"
  delete_after_extract: true            # FR-007c

sampling:
  fps: 2
  hud_anchor_min_score: 0.80

recognition:
  ocr_threads: 2
  low_conf_threshold: 0.80              # FR-011
  icon_min_margin: 0.08

interpret:
  swap_min_frames: 2
  short_segment_s: 10
  replay_repeat_window_s: 15
  clock_must_advance: true

retrieval:
  liquipedia_min_interval_s: 2.0
  owtv_min_interval_s: 5.0

verify:                                 # FR-017 tolerances
  team_kills_abs: 1
  player_deaths_abs: 0
  player_final_blows_abs: 0
  date_tz_one_day_note: true
  roster_match: exact
  source_priority:                      # FR-021
    date: liquipedia
    teams: liquipedia
    roster: liquipedia
    series_result: liquipedia
    map_winner: liquipedia
    bans: spreadsheet
    scoreboard: owtv
    heroes: video
    segments: video
    objective: video

export:
  include: verified                     # verified | partial | all
  source_ref_format: "yt:{video_id}@{hh}:{mm}:{ss}"
  analysis_tables: true                 # FR-024a: kill_events, player_hero_map, player_hero_summary
  summary_min_time_s: 60                # rates left empty below this time on a hero
```

## `local.yaml` (not committed)

```yaml
platform_terms_acknowledged: false      # must be true before any download (FR-014)
video_cache_dir: "C:/Users/<you>/AppData/Local/owstudy/videos"
user_agent_contact: "<contact for Liquipedia API User-Agent>"
reviewer: "<name or initials recorded in decisions>"
owtv_api_key: ""                         # personal OWTV API key; keep secret, never commit
```

## `patches.yaml`

```yaml
- {patch_id: "p2026.01", live_from_utc: "2026-02-10T18:00:00Z", note: "Season 21"}
```

## `hud/<layout_id>.yaml`

```yaml
layout_id: owcs2026_pov_v1
applies_to: [pov]
resolution_ref: [1920, 1080]            # regions are normalized 0–1; this is for documentation
anchors:                                # used to detect the layout and HUD presence
  - {name: clock_box, box: [0.468, 0.012, 0.064, 0.030], template: anchors/clock_box.png}
regions:
  hero_portrait:   {L1: [x, y, w, h], …, R5: [x, y, w, h]}
  player_name:     {L1: [...], …}
  game_clock:      [x, y, w, h]
  attack_clock:    [x, y, w, h]
  team_name:       {left: [...], right: [...]}
  map_banner:      [x, y, w, h]        # reads the map number ("MAP n"); map names come from references
  ban_display:     {left: [...], right: [...]}
  kill_feed:       {box: [x, y, w, h], row_height: 0.028, max_rows: 6}
  objective:
    control:    {left_pct: [...], right_pct: [...]}
    push:       {bar: [...]}
    escort:     {bar: [...], checkpoints: [...]}
    hybrid:     {bar: [...], checkpoints: [...]}
    flashpoint: {points: [...]}
team_colors:                            # kill-feed side detection
  left:  {hsv_low: [..], hsv_high: [..]}
  right: {hsv_low: [..], hsv_high: [..]}
```

The `extraction_key` includes this file's hash, so editing a layout means re-extracting the
affected videos (research R13).
