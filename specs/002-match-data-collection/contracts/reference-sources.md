# Contract: reference source adapters

Each adapter turns one retrieval into a snapshot folder (storage-layout.md) of **values as given**,
with a `locator` per record. Adapters never resolve names. That happens in `catalog build`.

## Spreadsheet (`OWCS 2026 Hero Bans _ Metas(1).xlsx`, fixed snapshot)

| Record | Fields | Locator |
|---|---|---|
| series | sheet, phase, label, team1/2 text, abbr1/2, score1/2, n_maps | `sheet!row` |
| map | series locator, map_number, map_name, score1/2 | `sheet!row:col` |
| ban | series locator, map_number, team text, hero text | `sheet!cell` |

Spreadsheet has no dates or rosters. It supplies bans (priority), map list and scores, and team
abbreviations (seed aliases).

## Liquipedia (MediaWiki API, wikitext parsed locally)

| Record | Fields |
|---|---|
| series | match key, event, part, date + tz, team1/2, bestof, maps_played, vod, page revision |
| map | map_number, map_name, mode, score1/2, winner, ban1/2, map_vod |
| lineup | team, player page names / display names for the series (or the team's event roster when the match has none) |

Terms: descriptive User-Agent with contact from `local.yaml`, gzip, ≤1 request per 2 s, cache by
revision ID. Locator: `page@revid#match<n>`.

## OWTV fantasy results (**to be fixed by the R10 probe**)

Planned record: `map_player_stats`: series key text, map_number (or empty if per series),
player text, team text, deaths, eliminations, final_blows (where given). Locator: URL + section.
The probe writes the real field list, granularity and access method here before the adapter is
built. If the data is only per series, comparisons run at series level (spec assumption).
≤1 request per 5 s, only if the site's terms allow it.

## YouTube channel list

Video ID, title, duration, approximate upload date, from `yt-dlp --flat-playlist` (no video
download). Listing is a snapshot like any other source.
