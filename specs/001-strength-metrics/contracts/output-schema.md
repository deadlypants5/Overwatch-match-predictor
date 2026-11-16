# Contract: run directory

## In short

What a run writes. The file that matters most is **`map_features.csv`**: one row of pre-map
features per map, ready for the model. `feature_timing.csv` says when each column becomes known.
Only `pre_map` and `map_start` columns may be used to predict a map. The rest are rating
histories, scores, ban impact and a list of what was left out and why.

Written by `owstudy-strength run`. Byte-for-byte reproducible (research R10): fixed column order,
rows sorted, floats `%.10f`, LF line endings, no timestamps or absolute paths.

```text
<run-dir>/
├── manifest.json               # package version, input + config SHA-256, row counts
├── config.resolved.yaml
├── map_features.csv            # main deliverable, one row per map × variant
├── segment_features.csv        # one row per map × segment × variant (hero-swap level)
├── feature_timing.csv          # column -> pre_map | map_start | segment | post_map | label
├── map_scores.csv
├── segment_scores.csv
├── snapshots_team.csv
├── snapshots_player.csv
├── snapshots_player_hero.csv
├── snapshots_hero.csv
├── ban_impact.csv
├── exclusions.csv
└── report/                     # written by `report`
```

## map_features.csv (columns in this order)

```text
# keys
map_seq, map_id, date, patch_id, mode_id, split, variant, team_a_id, team_b_id,
# pre_map
team_elo_a, team_elo_b, p_team_elo_a,
m_a, m_b, p_player_a,
ts_player_hero_career_a, ts_player_hero_career_b, p_ts_player_hero_career_a,
n_default_players_a, n_default_players_b,
# map_start
comp_start_a, comp_start_b, p_comp_start_a,
ban_loss_a, ban_loss_b, ban_undefined_a, ban_undefined_b,
n_no_history_heroes_a, n_no_history_heroes_b,
# post_map (weighted by this map's hero times; measurement only, not pre-map features)
ts_hero_a, ts_hero_b, p_ts_hero_a,
ts_player_hero_a, ts_player_hero_b, p_ts_player_hero_a,
n_segments,
# status + labels
player_metrics_ok_a, player_metrics_ok_b,
label_outcome_a, label_S_a, label_D_ab
```

- `feature_timing.csv` gives every column's class. Pre-map prediction may only use `pre_map`
  and `map_start` columns. `label_` columns are the map's own result and never features.
- `variant ∈ {wl, diff}`. `p_*_a` = expected probability that team A wins.
- Columns for a metric that was skipped (exclusion) are empty and `player_metrics_ok_* = false`.

## segment_features.csv

```text
map_seq, map_id, segment_no, start_s, end_s, duration_s, variant,
heroes_a, heroes_b,                 # sorted hero IDs joined with '|'
comp_a, comp_b, p_comp_a,           # Σ H_k of heroes in play, no time weighting (segment timing)
hbar_a, hbar_b, mu_g_a,             # mean pre-map h in play; expected +/- for team A (Marveldoss)
label_D_g, label_D_norm_g, label_S_g_a
```

## segment_scores.csv

`map_seq, map_id, segment_no, duration_s, kills_a, kills_b, t_hat_g, points_a, points_b, D_g, D_norm_g, S_g_wl_a, score_status`

## map_scores.csv

`map_seq, map_id, mode_id, duration_s, kills_a, kills_b, points_a, points_b, D_ab, sigma_mode, D_norm_ab, S_wl_a, S_diff_a, clamped, score_status`

`S_diff_a` is team Elo's 0–1 mapping. Player-level `diff` updates use `D_norm_ab` directly.

## snapshots_*.csv

- team: `map_seq, map_id, patch_id, variant, team_id, rating_pre, rating_post, is_default`
- player: `map_seq, map_id, patch_id, variant, team_id, player_id, rating_pre, rating_post, is_default`
- player_hero: `map_seq, map_id, patch_id, variant, player_id, hero_id, seconds, n_segments, rating_pre, delta, rating_post, career_seconds_pre, is_default` (`delta` = sum of that hero's per-segment updates)
- hero: `map_seq, map_id, patch_id, variant, hero_id, H_pre, W_pre, no_history` (one row per hero appearing or banned on that map)

`rating_post` is for auditing hand calculations only.

## ban_impact.csv / exclusions.csv

As in [data-model.md §5](../data-model.md).
