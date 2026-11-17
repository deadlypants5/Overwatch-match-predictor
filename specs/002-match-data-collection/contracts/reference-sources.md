# Contract: reference source adapters

## In short

| Source | What we take from it | How it's read |
|---|---|---|
| OWCS Hero Bans & Metas spreadsheet | Bans, map list and names, map scores, team abbreviations | From the fixed `.xlsx` file |
| Liquipedia | Dates and time zones, teams, lineups, map winners, VOD links | Its official API, at most 1 request every 2 s |
| OWTV | Scoreboard per player per map, hero playtime, bans, team fights, and the map event log (allowed as a main source) | Its official API with a key, under 60 requests a minute; the probe (T065) checks coverage |
| YouTube (ObsSojourn channel) | The list of POV videos: IDs, titles, lengths | Video list only, no download |

Each download is saved as a dated snapshot with values exactly as the source gives them.
Names are matched to stable IDs later, in `catalog build`.

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

**Permission (2026-11-16):** Liquipedia allows us to use its data as long as we credit it.
Every export, chart or write-up that uses Liquipedia data must say so and link to
liquipedia.net.
**API key:** requested from Liquipedia on 2026-11-16 (with our contact); waiting for an answer.
New Liquipedia downloads (task T028) wait until the key arrives. It goes in `local.yaml` as
`liquipedia_api_key`, never in git. Record the date and any extra terms here when they reply.

## OWTV fantasy results (**to be fixed by the R10 probe**)

Planned record: `map_player_stats`: series key text, map_number (or empty if per series),
player text, team text, deaths, eliminations, final_blows (where given). Locator: URL + section.
The probe writes the real field list, granularity and access method here before the adapter is
built. If the data is only per series, comparisons run at series level (spec assumption).
≤1 request per 5 s, only if the site's terms allow it.

### What OWTV's terms allow (checked 2026-11-16, terms dated 2026-11-11)

In short: **no scripts on the website; use their official API, which needs a key and their approval.**

- **The website can't be read by a program.** The terms forbid bots, scripts, scrapers and
  "data mining" tools, and forbid systematically pulling data into a database without written
  permission. So the probe must not fetch OWTV's web pages.
- **There is an official API.** Documentation is at `owtv.gg/api-docs`. Keys go only to
  approved supporters and contributors, one key per person or per named project.
- **Research use is allowed with a key.** Rules that apply to us:
  - at most 60 requests per minute (our limit of 1 per 5 s is well inside this); stop when told to slow down
  - cache answers and don't re-ask for unchanged data
  - credit OWTV.gg, with a link, wherever their data is shown publicly
  - no publishing bulk exports or dumps of their data, and no building a competing database
  - no making money from it without written approval
  - keep the key secret: it goes in `local.yaml` only, never in git
- **Questions and approval:** the contact email is on the terms page.
- There is no `robots.txt`.

**Permission (2026-11-17):** granted for the current scope. The OWTV owner knows the project's
scope and allows its data to be used **as a main source**, not only as a cross-check, as long as
we stay **under 60 requests a minute**. (An earlier permission, Oct 2026, covered an older scope.)
We've asked them for the layout of the map event log (`eventLog`), which their docs don't
describe yet. The other terms above (credit with a link, no bulk dumps, key kept secret) still apply.

### What the API offers (from `owtv.gg/api-docs`, read 2026-11-17)

- **Access:** `GET https://owtv.gg/api/<collection>` (a list) or `/<collection>/<id>` (one item).
  The key goes in the `X-API-Key` header. Read-only. Lists take `limit` (100 at most), `page`,
  `sort`, `depth` (0 = IDs only, 1–2 = related items included) and `where[...]` filters.
  Going over the limit returns 429. The API is in early access, so its layout may change: we keep
  every answer exactly as received.
- **Permissions (scopes) the key needs:** `read:matches`, `read:teams`, `read:tournaments`.
- **Useful collections:**
  - `match`: date, teams, score, best-of, winner, bracket side, links to its maps
  - `match-map`: map, map order, winner, bans (`team1Ban`, `team2Ban`, `firstBan`), who picked the
    map, replay code, `replayParsed`, **`eventLog`** (raw event log, layout not documented yet),
    and links to player stats
  - `map-fight`: each team fight, with start time (seconds from map start), length, kills,
    deaths, ultimates used, and its own event log
  - `player-map-stats`: one player on one map: eliminations, assists, deaths, damage, healing,
    mitigation (**no final blows**)
  - `player-map-stats-hero`: one player on one hero on one map: playtime, totals, ultimates,
    perks
  - `person`, `team`, `team-membership` (with join and leave dates), each with a Liquipedia link
  - `game-hero`, `game-map`, `hero-perk`, `tournament`, `tournament-phase`, `region`
- **Not in the API:** no VOD or video links; no in-game round data outside the event log.

## YouTube channel list

Video ID, title, duration, approximate upload date, from `yt-dlp --flat-playlist` (no video
download). Listing is a snapshot like any other source.

**Permission:** request sent to the ObsSojourn channel owner on 2026-11-16; waiting for an answer.
Until they agree (and the platform terms are confirmed, task T039), `platform_terms_acknowledged`
stays `false` and no videos are downloaded.
