# Fake reference data for the catalog tests

These files are a tiny, made-up league. They exist only so the catalog tests (`tests/collect/integration/test_catalog.py`) can check every rule on a few rows instead of the real data. None of the teams or players are real.

`inventory_summary_2026-11-15.csv` is different: it's a copy of the real inventory numbers, used by the inventory test.

## What's in the league

The data is laid out like the real `data/raw/reference/` folder, with one dated snapshot per source:

| Folder | What it holds |
|---|---|
| `liquipedia/2026-11-20/responses/batch1.json` | Four Liquipedia pages, saved the way the API returns them |
| `spreadsheet/2026-11-20/` | The matching rows of the Hero Bans & Metas spreadsheet |
| `youtube/2026-11-20/` | A short list of channel videos |

The Liquipedia pages hold these series:

| Series | Date (local) | Teams | Why it's there |
|---|---|---|---|
| Korea regular season, match 1 | Apr 14, 19:00 KST | Team Alpha vs Bravo Esports | Played on a patch day in Korea, so it gets the previous patch. Map 2 is a Clash map. |
| Korea regular season, match 2 | Apr 15 | Charlie vs Delta Gaming | A forfeit, with one forfeited map |
| Korea regular season, match 3 | Apr 16, 08:00 KST | Charlie vs Team Alpha | Early morning, so in UTC it falls on the day before |
| Korea regular season, match 4 | Dec 1 | Bravo vs Delta | Not played yet, so it's left out |
| Korea playoffs, match 1 | Apr 25 | Bravo Esports vs Team Alpha | The same two teams meet again, so a video has to be told apart by its title |
| NA regular season, match 1 | Apr 14, 15:00 CDT | Echo vs Foxtrot | Same patch day, but outside Korea, so it gets the new patch |
| Preseason Bootcamp | Mar 5 | Team Alpha vs Charlie | Out of scope everywhere (FR-023a) |

The Korea overview page also lists each team's roster, with one coach per team. The coaches must be left out of the lineups.

The spreadsheet has the four played Korea series. It also has one series Liquipedia doesn't list (Delta Gaming vs Team Alpha, row 85), which must be flagged as coming from only one source.

The video list has:

- one video per played series
- a second POV of match 1, from the other team
- a re-upload of a video (must be marked as a duplicate)
- a title with unknown teams, and a title whose teams never played each other (both must stay unmatched, not guessed)
- a FaceIt video, a Bootcamp video and a 2025 video (all out of scope)

## Changing it

The Liquipedia file was generated once by a short script and is easiest to edit by hand. The match text sits in each page's `"*"` field. Keep the four test files in step with each other: if you add a series, also add it to the spreadsheet rows (unless it's meant to be Liquipedia-only), and check the counts in `test_catalog.py`.
