# Footage inventory (2026-11-15)

Exploratory output for spec 002, User Story 0 / FR-007a. It answers: how many 2026 OWCS series and
maps were played, which ones have an ObsSojourn POV video, and how many hours of footage that is.

## Sources (snapshots in `data/raw/reference/`)

| Source | File | Retrieved |
|---|---|---|
| OWCS 2026 Hero Bans & Metas spreadsheet | `spreadsheet/sheet_series.csv`, `sheet_maps.csv` | parsed 2026-11-15 |
| Liquipedia page sources (all 2026 OWCS events, excluding open qualifiers and relegation) | `liquipedia/batch*_2026-11-15.json` → `lp_series.csv`, `lp_maps.csv` | 2026-11-15 |
| ObsSojourn channel video list (titles, IDs, lengths, approximate upload month) | `youtube/obssojourn_videos_dated_2026-11-15.json` | 2026-11-15 |

## Files

- `inventory_summary.csv`: per event, plus the pilot and the whole set: series, maps, series with/without video, footage hours (all POVs / one POV per series / one POV per team).
- `series_inventory.csv`: one row per played 2026 series, with matched POV count and hours.
- `series_missing_video.csv`: series with no ObsSojourn video.
- `pilot_korea_stage1_series.csv`: the pilot's 51 series.
- `gap_coverage.csv`: of the series with no ObsSojourn video, how many have an official broadcast VOD linked on Liquipedia.
- `sheet_vs_liquipedia.csv`: series and map counts per event, spreadsheet vs. Liquipedia.
- `video_matches.csv`: every channel video, its parsed teams, the series it was assigned to, and a status.

## Regenerate

```text
python -I scripts/inventory/parse_sheet.py "OWCS 2026 Hero Bans _ Metas(1).xlsx" data/raw/reference/spreadsheet
python -I scripts/inventory/parse_lp.py data/raw/reference/liquipedia data/raw/reference/liquipedia/batch1_2026-11-15.json data/raw/reference/liquipedia/batch2_2026-11-15.json
python -I scripts/inventory/inventory.py data/raw/reference/youtube/obssojourn_videos_dated_2026-11-15.json data/raw/reference/liquipedia/lp_series.csv data/raw/reference/liquipedia/lp_maps.csv data/raw/reference/spreadsheet/sheet_series.csv data/interim/inventory
```

## Known limits

- Upload dates are approximate (to the month); they only separate 2025 from 2026 uploads.
- 517 videos matched a team pair that met more than once in the same window (e.g., regular
  season and playoffs). They were assigned by phase words in the title and upload date, so a few
  may sit on the wrong one of the two series. Total hours are unaffected.
- "One POV per team" hours are estimated as 2 × the median POV length, since a video's team is
  not yet resolved from the player name.
- "No official VOD" means Liquipedia has no link, not that no broadcast exists.
- About 80 channel videos were left unmatched (unknown team names such as SV Crush and RTplz, or
  showmatches/qualifiers). See `video_matches.csv`, status `unknown_team` / `no_2026_series`.
