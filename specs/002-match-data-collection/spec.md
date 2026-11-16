# Feature Specification: Match Data Collection & Verification

**Feature Branch**: `002-match-data-collection`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "lets start the data collection, ObsSojourn's youtube channel contains
replays of each match, these matches should be referenced against the excel sheet, owcs
liquipedia page to make sure the dates and rosters line up, as well as OWTV fantasy match
results to check the score board results. a few task that come to mind: 1st decide how the data
will be stored, and what data should be stored. i have ideas on what to store but i do not have
expertise in storing and using data so i will listen to your recommendations. 2nd decide how the
data will be collected, i want to use a virtual player that can watch these videos. 3rd how the
data will be verified against the sources i provided"

## Overview

This feature turns OWCS 2026 match replays into the map-level dataset that the strength metrics
feature (`specs/001-strength-metrics`) consumes. It has three parts, matching the three tasks in
the request:

1. **What is stored and how it is organized**: three layers, kept separate so mistakes can be
   traced and fixed without re-watching video:
   - **Raw observations**: everything the virtual viewer saw, exactly as it saw it, with the
     video and timestamp it came from. Never edited after it is written.
   - **Reference records**: what each outside source (the OWCS Hero Bans & Metas spreadsheet,
     Liquipedia, OWTV fantasy results) says about each series and map, saved as retrieved, with
     the retrieval date.
   - **Reconciled dataset**: one clean record per map, built from the two layers above, in the
     exact input format feature 001 expects, with a verification status and a log of every
     disagreement and how it was settled.
2. **How it is collected**: a "virtual viewer" processes each ObsSojourn replay and records
   what is on screen over time: which map (by its number in the series) and mode, the two teams and ten players, every hero
   swap, every kill, objective progress, the game clock, round/attack boundaries, bans and the
   final result.
3. **How it is verified**: every reconciled map is checked field by field against the outside
   sources. Agreement raises confidence; disagreement is logged with both values and sent for
   review instead of being silently overwritten (Constitution Principle IV).

## Clarifications

### Session 2026-11-16

- Q: Where does each map's name come from, given the ObsSojourn POV banner shows "MAP 1" and
  the event but not the map name? → A: From the reference sources: the spreadsheet first,
  cross-checked against Liquipedia (OWTV if its probe shows map names). The viewer reads the
  **map number** from the banner and the **mode** from the objective widget. Map spans are
  aligned to catalog maps by map number, with mode as a sanity check. The video is no longer a
  source for map names.

## User Scenarios & Testing *(mandatory)*

The primary user is the project researcher. They point the system at the replay channel and the
reference sources, and get back a verified map dataset plus a short list of problems that need a
human decision.

### User Story 0 - Footage inventory (Priority: P0, first task)

Before any viewer is built or any processing cost is chosen, the researcher gets an inventory of
how much footage is needed: every series and map played in 2026 (from Liquipedia and the
spreadsheet), every ObsSojourn video that covers it, and every series or map with no video. It
is produced twice: for the pilot (Korea Stage 1) and for the whole 2026 set.

ObsSojourn uploads one **POV video per player per series** (titles like
`[ Player ] Nickname | Team A vs Team B | Event`). Up to 10 videos can cover the same series.
The inventory therefore reports footage hours three ways: all POV videos, one POV per series
(the minimum needed, because the HUD shows both teams), and one POV per team per series (the
minimum for cross-checking each team's view).

**Why this priority**: The processing budget (FR-015) can't be chosen until the amount of
footage is known, and the gaps show where data will only come from the reference sources.

**Independent Test**: Count the series and maps for Korea Stage 1 by hand from Liquipedia, and
confirm the inventory has the same counts, and that every listed video opens to the right
series.

**Acceptance Scenarios**:

1. **Given** Liquipedia and the spreadsheet, **When** the inventory is built, **Then** it lists
   every played series and map with its date, event, teams and score, and flags series that
   appear in only one source.
2. **Given** the channel's video list, **When** the inventory is built, **Then** every video is
   assigned to a series (or listed as unmatched / not OWCS 2026), with its player and length.
3. **Given** the inventory, **When** the summary is read, **Then** it shows, for the pilot and
   for the whole set: series, maps, series with and without a video, and footage hours under
   each of the three counting rules above.

---

### User Story 1 - Build the match catalog and link replays (Priority: P1)

The researcher builds a catalog of every OWCS 2026 series and map in scope, taken from the
reference sources (spreadsheet and Liquipedia: date, region, stage, teams, rosters, map order,
map winners, bans), and links each map to the ObsSojourn replay (and the position in the video)
that shows it.

**Why this priority**: Nothing can be watched or checked until we know which matches exist and
which video shows each one. The catalog alone also already gives map winners, which is enough
for team Elo (feature 001, User Story 1).

**Independent Test**: For one region-stage, compare the catalog against Liquipedia by hand:
every series is present, dates and teams match, and every replay link opens the right match.

**Acceptance Scenarios**:

1. **Given** the spreadsheet and Liquipedia both list a series, **When** the catalog is built,
   **Then** the series appears once, with its date, region, stage, teams, map list and result,
   and a note of which sources supplied each field.
2. **Given** an ObsSojourn video whose title names two teams and an event, **When** linking
   runs, **Then** it is matched to the series with those teams closest in date on or before the
   upload date, and the match is recorded with its confidence.
3. **Given** a video that covers several maps of a series, **When** linking runs, **Then** each
   map in the catalog points to the start and end time of that map in the video.
4. **Given** a series in the catalog with no matching video, **When** the catalog is reported,
   **Then** the series is listed as "no replay" and its maps are still kept with whatever the
   reference sources provide.
5. **Given** a video that cannot be matched to any series, **When** linking runs, **Then** it
   is listed as unmatched for review, not guessed.

---

### User Story 2 - Virtual viewer extracts map events from a replay (Priority: P2)

For each linked map, the virtual viewer watches the replay and records a timeline of
observations: hero shown for each of the ten players over time, each kill (who killed whom, on
which heroes, at what game time), objective progress readings, the game clock, round and attack
boundaries, the ban phase, and the final result. From that timeline it builds the segments,
kill totals, objective progress, and attack timings that feature 001 needs.

**Why this priority**: This is the only source of per-hero time played and per-segment kills
and objectives, which every metric beyond team Elo depends on.

**Independent Test**: For a small "gold set" of maps that the researcher has labeled by hand
while watching, compare the viewer's output to the hand labels field by field.

**Acceptance Scenarios**:

1. **Given** a player swaps from one hero to another mid-map, **When** the replay is processed,
   **Then** a new segment starts at the swap time, and both segments list the correct hero for
   that player.
2. **Given** a kill appears in the kill feed, **When** the replay is processed, **Then** a kill
   observation is recorded with game time, killer, victim, both heroes, and the video timestamp.
3. **Given** an Escort or Hybrid map, **When** the replay is processed, **Then** each attack is
   recorded with the attacking team, its progress, its attack clock and the time remaining when
   it ended (including banked time).
4. **Given** a stretch of video where the game is not visible (replay cut, caster desk, pause,
   technical stop), **When** it is processed, **Then** the gap is recorded as a gap and no
   events are invented for it.
5. **Given** any value the viewer is unsure of (e.g., an unreadable player name or hero
   portrait), **When** it is recorded, **Then** it carries a confidence value and low-confidence
   values are flagged instead of being treated as certain.
6. **Given** the same video and the same extraction settings, **When** it is processed twice,
   **Then** the observations are identical.

---

### User Story 3 - Verify against the reference sources (Priority: P3)

Every map built from a replay is compared field by field with the reference sources: dates and
rosters against Liquipedia and the spreadsheet; map names, order, winners and bans against all
three where available; and per-player and per-team scoreboard figures (kills, deaths) against
OWTV fantasy results. Each map gets a verification status, and every disagreement is logged.

**Why this priority**: Constitution Principle IV requires it, and errors in heroes or results
corrupt every downstream rating.

**Independent Test**: Plant known errors in a copy of a few reconciled maps (wrong winner, wrong
player, a missing kill) and confirm each one is caught and logged with both values.

**Acceptance Scenarios**:

1. **Given** the video, spreadsheet and Liquipedia all agree on a map's winner, teams, roster and
   bans, and the kill totals agree with OWTV fantasy within tolerance, **When** verification
   runs, **Then** the map is marked `verified`.
2. **Given** the video shows a player who is not on that team's Liquipedia roster for the
   series, **When** verification runs, **Then** a roster discrepancy is logged with both values,
   and the map is not marked `verified` until it is resolved.
3. **Given** the viewer's kill count for a player differs from OWTV fantasy by more than the
   tolerance, **When** verification runs, **Then** a scoreboard discrepancy is logged with both
   numbers and the video time range to re-check.
4. **Given** a discrepancy, **When** the researcher records a decision (accept source X, accept
   the video, or enter a corrected value), **Then** the decision, who made it, when, and why are
   saved, and the reconciled record is rebuilt using it, while the raw observation stays
   unchanged.
5. **Given** a field that only one source provides, **When** verification runs, **Then** the
   field is marked "single source" rather than verified.

---

### User Story 4 - Export the verified dataset (Priority: P4)

The researcher exports the reconciled dataset as input for feature 001, choosing whether
unverified maps are included, and gets a summary of coverage and quality.

**Why this priority**: This is the hand-off to the strength metrics; it only adds value once
Stories 1–3 work.

**Independent Test**: Export, then run feature 001's input validation on the result with no
errors.

**Acceptance Scenarios**:

1. **Given** a reconciled dataset, **When** it is exported, **Then** it passes feature 001's
   input validation with no errors.
2. **Given** the export, **When** the researcher reads the summary, **Then** it shows, per
   region and stage: maps in scope, maps with replays, maps processed, maps verified, open
   discrepancies by type, and maps excluded with reasons.
3. **Given** every exported map, **When** the researcher looks up its provenance, **Then** they
   can find the video, the timestamps, the extraction version, and which source confirmed each
   field.

### Edge Cases

- A team rebrands or a player changes their in-game name during the season: names are resolved
  to stable IDs through the alias table; a new name with no alias is flagged, not auto-created
  as a new player if it closely matches an existing one.
- Video title has a typo or uses a team abbreviation: matching uses the alias table and team
  abbreviations from the spreadsheet; ambiguous matches go to review.
- The same match is uploaded twice (re-upload, split parts): duplicates are detected and only
  one is used; the others are recorded as duplicates.
- A map was remade or restarted (technical pause, remake after a bug): only the completed game
  counts; the abandoned attempt is recorded and excluded.
- Spectator camera is on one player when a kill happens off-screen: kills are taken from the
  kill feed, not the camera view. If the kill feed is hidden or covered by a replay or overlay,
  the gap is recorded and the team kill total is checked against the scoreboard source.
- Scoreboard "eliminations" in Overwatch include assists, so they don't equal kills. Team kills
  are compared as the opposing team's total deaths, and per-player checks use deaths (and final
  blows where the source has them).
- Hero swaps in spawn that last only seconds: every swap visible on screen starts a segment;
  very short segments are kept and flagged so the strength feature can decide how to treat them.
- Sources disagree on the match date (time zones, broadcast delay vs. live date): dates are
  compared in a single time zone and a one-day difference caused by time zone is noted, not
  treated as a conflict.
- OWTV fantasy has no result for a match, or Liquipedia is incomplete: the affected fields are
  marked "single source"; the map can still be used but is not `verified` for those fields.
- A Clash map (mode no longer in scope): it is recorded in the catalog and excluded from the
  export with reason, matching feature 001.
- A forfeit or walkover: kept in the catalog with no video data and excluded from the export.
- Broadcast footage (if used) shows an instant replay of a fight: replays look like live play,
  so observations are accepted only while the game clock moves forward from the last accepted
  reading. Footage where the clock rewinds or repeats is a replay and is discarded. A kill-feed
  entry matching an earlier one (same killer, victim and heroes) is flagged as a possible
  replay.
- Broadcast footage shows downtime (caster desk, breaks, ads, map transitions): footage with no
  game HUD is skipped, not read frame by frame, and does not count toward gameplay time. On the
  pilot, broadcast slots run about 2.6× as long as the POV video of the same series.
- A source page changes after retrieval (e.g., Liquipedia corrected later): each retrieval is
  saved with its date; re-retrieving creates a new snapshot and any newly appearing differences
  are reported.

## Requirements *(mandatory)*

### Functional Requirements

**Storage and what is stored**

- **FR-001**: System MUST keep three separate layers: raw observations (from video), reference
  records (from each outside source), and the reconciled dataset. Raw observations and
  reference records MUST NOT be edited once written; corrections MUST live only in the
  reconciled layer, as logged decisions.
- **FR-002**: Every raw observation MUST record: video ID, video timestamp, game clock reading
  (when visible), observation type, value, confidence, extraction method and version, and
  extraction date.
- **FR-003**: The virtual viewer MUST record at least these observation types: map number
  (from the banner) and mode (from the objective widget); team names and side; the ten player names; each player's hero over time; kill feed
  entries (killer, victim, their heroes, and whether it was a self-inflicted/environmental
  death); objective progress readings; game clock and attack clock; round and attack
  boundaries; the ban phase result; the final map result; and gaps where gameplay is not
  visible.
- **FR-004**: Every reference record MUST record: source (spreadsheet, Liquipedia, OWTV
  fantasy), the page or sheet and row it came from, retrieval date, and the values as given.
- **FR-005**: The reconciled dataset MUST include, per map, everything in feature 001's input
  contract (maps, segments, segment heroes, bans, attacks, aliases), plus a verification status
  and links back to the raw observations and reference records it was built from.
- **FR-006**: System MUST keep stable IDs for teams, players, heroes, maps, modes, series and
  patches, with an alias table mapping every observed spelling to its stable ID
  (Constitution: Canonical entities).
- **FR-007**: System MUST store only derived data (observations, records, the dataset), never
  copies of the videos, in the project repository (Constitution Principle IV).

**Collection**

- **FR-007a**: Before any extraction, the system MUST produce a footage inventory (User
  Story 0) for the pilot and for the whole 2026 set. It reports series, maps, matched videos,
  series and maps with no video, and footage hours counted three ways: all POV videos, one POV
  per series, and one POV per team per series.
- **FR-007b**: Video source policy for the pilot: ObsSojourn POV videos are the only source
  for extracted data. Official broadcast VODs are tested separately on 2–3 series that also have
  an ObsSojourn POV, using the POV result as the answer key. Broadcasts may be used to fill
  gaps only if that test shows that replays are rejected and downtime is skipped, and the
  researcher approves.
- **FR-007c**: Videos MUST be deleted after their extraction run succeeds; only derived data is
  kept. Re-processing a video after a change to the viewer means downloading it again.
- **FR-008**: System MUST build a catalog of all series and maps in scope from the reference
  sources, and link each map to a replay video and the time range inside it.
- **FR-009**: The virtual viewer MUST process a replay without a human watching it, and produce
  the observation timeline described in FR-003.
- **FR-010**: System MUST derive segments (a new one at every hero swap and every round or
  attack boundary), segment kills, segment objective progress, and attack timings from the
  observations, in the format of feature 001's input contract.
- **FR-011**: Every extracted value MUST carry a confidence; values below a configurable
  threshold MUST be flagged for review and not counted as verified.
- **FR-012**: Processing MUST be resumable: if it stops partway, already-processed maps are not
  reprocessed unless the extraction version changes or the researcher asks.
- **FR-013**: Given the same video and extraction settings, the viewer MUST produce identical
  observations.
- **FR-014**: Retrieval from YouTube, Liquipedia and OWTV MUST respect each platform's terms of
  use and rate limits.
- **FR-015**: The virtual viewer and every other step MUST run entirely on the researcher's own
  computer, with no paid or cloud processing services. Processing the pilot (~18 h of POV
  footage plus the broadcast test) MUST finish within a few days on that computer, and the whole
  set (~200 h) within a few weeks, running unattended.

**Verification**

- **FR-016**: System MUST compare these fields across sources whenever more than one provides
  them: series date; teams; each team's roster per map; map names and order; map winner and
  series score; bans; game mode; per-player deaths and team kill totals; and, where the source
  has them, per-player final blows.
- **FR-017**: Each comparison MUST produce one of: `agree`, `agree_within_tolerance`,
  `disagree`, or `single_source`. Default tolerances: exact for names, dates (after time-zone
  normalization), winners, bans and rosters; ±1 for a team's kill total per map; exact for
  per-player deaths. Tolerances MUST be configurable.
- **FR-018**: Every `disagree` MUST be logged with: map, field, each source's value, the video
  time range to re-check, and status (open / resolved). No value may be overwritten without a
  logged resolution.
- **FR-019**: Each map MUST get a verification status: `verified` (every compared field
  agrees, no open discrepancies, no low-confidence values in required fields), `partial` (some
  fields single-source but nothing in conflict), `conflict` (at least one open discrepancy), or
  `unverified` (no second source available).
- **FR-020**: The researcher MUST be able to resolve a discrepancy by choosing a source's value
  or entering a corrected one, with a reason; the decision is saved and re-applied on every
  rebuild. Every discrepancy MUST be reviewed by the researcher; no discrepancy is closed
  automatically, and a map cannot be `verified` while any of its discrepancies is open.
- **FR-021**: Until the researcher decides, a default source priority MUST supply a provisional
  value (shown as provisional, and the discrepancy stays open): Liquipedia for dates, teams, rosters and series results; the
  spreadsheet for bans and map names (Liquipedia as the cross-check; the video does not read
  map names); OWTV fantasy for scoreboard figures; the video for hero swaps, segment
  timing and objective progress (the only source that has them).
- **FR-022**: System MUST measure the virtual viewer's accuracy against a hand-labeled gold set
  of maps (at least one map per game mode) and report it per field.

**Scope and export**

- **FR-023**: The collection MUST start with a pilot on **OWCS 2026 Korea Stage 1**. Expanding
  to other regions, stages and LAN events happens only after the pilot meets SC-001, SC-002 and
  SC-007, and the researcher approves. Each expansion adds one region-stage (or event) at a
  time, and is tracked in the coverage summary.
- **FR-024**: System MUST export the reconciled dataset in feature 001's input format, with an
  option to include or exclude non-`verified` maps, and a coverage and quality summary per
  region and stage.
- **FR-024a**: Alongside the feature 001 input, the export MUST include (a) a kill events
  table, one row per kill with game time, segment, killer and victim (team, player, hero) and
  whether it was an environmental or self death; (b) a per-map table with one row per player ×
  hero, giving time on the hero, team kills and deaths, the player's own kills and deaths, and
  objective progress for and against during that time; and (c) a summary over all exported
  maps per player × hero × mode, with totals and per-10-minute rates. The summary is
  descriptive and MUST NOT be used as a pre-map feature (Constitution II).
- **FR-025**: Every map in the catalog that is not exported MUST appear in the summary with its
  reason (no replay, forfeit, Clash, open conflict, unverified and excluded by setting).

### Key Entities

- **Source Video**: One ObsSojourn upload: video ID, title, upload date, length, whose POV it
  is (player and team), the series it is linked to, and link confidence. Several videos (one per
  player) can cover the same series.
- **Video Map Span**: The start and end time of one map inside a video.
- **Observation**: One thing the viewer saw at one moment (FR-002/FR-003). Immutable.
- **Extraction Run**: One processing pass: extraction version, settings, date, which videos,
  and per-video outcome.
- **Reference Record**: What one source says about one series or map, as retrieved, with
  retrieval date. Immutable.
- **Catalog Series / Catalog Map**: The list of series and maps in scope, from the reference
  sources, with region, stage, date, teams, map order.
- **Reconciled Map**: The clean map record exported to feature 001, with verification status
  and links to its observations and reference records.
- **Comparison**: One field of one map compared across sources, with outcome (FR-017).
- **Discrepancy**: A `disagree` comparison, with both values, time range to re-check, and
  status.
- **Review Decision**: A researcher's resolution of a discrepancy: chosen value, reason, date.
- **Alias**: A spelling of a team, player, hero or map name mapped to a stable ID, with the
  dates it was in use.
- **Gold Label**: A hand-labeled value for a gold-set map, used to measure viewer accuracy.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of maps in scope are linked to a replay, and 100% of linked maps were
  confirmed against the catalog (no map linked to the wrong series in a hand check of 30 random
  links).
- **SC-002**: On the gold set, the viewer gets 100% of map winners, map numbers, modes and bans right;
  at least 98% of players' heroes right per segment; hero swap times within 3 seconds for at
  least 95% of swaps; and team kill totals within ±1 for at least 95% of maps.
- **SC-003**: 100% of exported maps can be traced to their video, timestamps, extraction
  version and confirming sources.
- **SC-004**: 0 values in the reconciled dataset differ from their raw observation or reference
  record without a logged decision (checked automatically).
- **SC-005**: At least 85% of processed maps reach `verified` without a manual decision.
- **SC-006**: All planted errors in the verification test (wrong winner, wrong player, missing
  kill, wrong ban, wrong date) are caught.
- **SC-007**: The exported dataset passes feature 001's input validation with 0 errors.
- **SC-008**: Re-running extraction on the same videos with the same settings produces
  identical observations; rebuilding the reconciled dataset from stored layers and decisions
  produces an identical export.
- **SC-009**: The researcher can review and resolve an open discrepancy in under 2 minutes on
  average, using the logged values and the video time range to jump to.

## Assumptions

- **Storage recommendation** (the researcher asked for one): the three-layer design in the
  Overview. Raw and reference layers are append-only so any later fix to the viewer or a source
  can be re-applied without re-watching video. The reconciled layer is always rebuildable from
  them plus the review decisions. This maps directly onto the constitution's `data/raw/`,
  `data/interim/` and `data/processed/` folders. The exact file format is decided in the plan.
- **Store more than feature 001 needs right now**: individual kill events (killer, victim,
  heroes, time) are stored, not just totals, because they are cheap to keep during viewing and
  expensive to re-collect later (e.g., for future first-pick or duel features). The researcher's
  own ideas for extra fields can be added to FR-003 at clarification.
- ObsSojourn replays use the standard OWCS observer layout, which shows all ten players' heroes,
  the kill feed, the objective status and the game clock. Views that hide parts of this
  (replays, caster cams) are recorded as gaps.
- The video upload date is not the match date; the match date comes from the reference sources.
- Player names are read from the in-game HUD; their mapping to Liquipedia player pages goes
  through the alias table, seeded from Liquipedia rosters.
- The OWCS 2026 Hero Bans & Metas spreadsheet (`OWCS 2026 Hero Bans _ Metas(1).xlsx`) is a
  fixed snapshot provided by the researcher. It covers per-series map lists, map scores, bans and
  team indexes for each region and stage.
- OWTV fantasy results provide per-player scoreboard statistics per map (at least deaths, and
  eliminations). If they turn out to be per series only, scoreboard checks run at series level.
- Patch IDs come from the official patch release dates (each map gets the patch live on its
  date).
- A small gold set (about 5–10 maps covering every mode) is labeled by hand by the researcher
  once, to measure viewer accuracy.
- Downloading or reading replays is done in a way the platforms permit; the researcher confirms
  this is allowed for personal research before large-scale processing.
- Training the prediction model and tuning the scoring constants (`a`, `X_n`, `C_n`) are out of
  scope; they belong to features 001 and 003 once this data exists.
