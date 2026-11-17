# Quickstart: validating Match Data Collection

**Feature**: `002-match-data-collection` | **Plan**: [plan.md](./plan.md)

How to check that each part works, in the order it will be built. Every command is listed in
[contracts/cli.md](./contracts/cli.md), and every file in
[contracts/storage-layout.md](./contracts/storage-layout.md).

## In short

| Step | What it checks | Hand check by you? |
|---|---|---|
| 1. Offline tests | All the logic, on small fake data | – |
| 2. Inventory and catalog | Every pilot series and map is listed and linked to a video | Open 30 random links |
| 3. Probes | The POV HUD shows what the viewer needs; what OWTV provides | Answer the HUD checklist |
| 4. Viewer on one video | One video turns into readings and events, the same way twice | Name the hero icons |
| 5. Gold set | The viewer is accurate enough | Label 6 maps while watching |
| 6. Pilot run and review | The whole pilot is processed, checked and reviewed | Settle each disagreement |
| 7. Broadcast test | Broadcasts can fill the coverage gap (or not) | Decide whether to use them |
| 8. Export | Feature 001 accepts the data, and the export is repeatable | Spot-check one player |
| Expansion gate | The pilot is good enough to add the next region | Approve |

## 0. Prerequisites

- Python 3.11+, `uv`. From the repo root: `uv sync --extra collect --extra dev`.
- `configs/collect/local.yaml` created from the example in
  [config-schema.md](./contracts/config-schema.md). Set `platform_terms_acknowledged: true` only
  after the researcher has confirmed the platforms allow it (FR-014).
- ~20 GB free disk for the video cache (2 videos at a time). No GPU needed.

## 1. Offline tests (no network, no video)

```text
uv run pytest tests/collect -q
```

**You should see:** unit tests (run-length encoding round-trip, interpretation rules, segment tiling,
objective normalization per mode, comparison outcomes and tolerances, discrepancy ID stability,
stale decisions, status rules) and fixture tests on a small synthetic set of readings and
references all pass. This includes the planted-error test: every planted error in
`tests/collect/fixtures/planted/` is caught (SC-006).

## 2. Inventory and catalog (US0, US1)

```text
uv run owstudy-collect inventory --scope pilot
uv run owstudy-collect catalog build --scope pilot
uv run owstudy-collect status --scope pilot
```

**You should see:** inventory matches the current `data/interim/inventory/` counts (51 series, 186 maps,
25 series with a POV). In `catalog/video_links.csv` every pilot video is `linked`, `unmatched`
or `duplicate`, and `low` links are listed for review. **Manual check**: 30 random links
opened in the browser, each showing the right series (SC-001 link check). Series with no video
show `no_replay` and still have their reference maps.

## 3. Probes (run once, before any bulk processing)

```text
uv run owstudy-collect refs probe-owtv <3 pilot series>
uv run owstudy-collect hud probe <3 pilot video ids, one Control, one Escort/Hybrid, one Push/Flashpoint>
```

Run the OWTV probe first: its result decides how much the video viewer still has to do.

**You should see:** the OWTV probe fills in the OWTV section of
[reference-sources.md](./contracts/reference-sources.md), including how many pilot maps OWTV
covers. `data/interim/probes/hud/checklist.md` answers each R5 item. Any "no" answer
follows the fallback in research R5/R10 before continuing.

## 4. Viewer on one video (US2)

```text
uv run owstudy-collect icons harvest <2-3 video ids>   # then: icons label
uv run owstudy-collect extract --videos <id> --keep-video --check-determinism
uv run owstudy-collect build --scope pilot
```

**You should see:** `data/raw/observations/<id>/<key>/` holds `run.json` (outcome `ok`), readings, kills
and the manifest. The determinism check reports identical readings for both passes (FR-013).
`interim/events/` has hero intervals, kills and attacks for each map span. Gaps appear where
the video shows no HUD.

## 5. Gold set accuracy (FR-022, SC-002)

```text
uv run owstudy-collect gold init <6 map ids covering every mode>
# researcher fills data/raw/gold/<map_id>/labels.csv while watching
uv run owstudy-collect gold score
```

**You should see:** `interim/reports/gold_accuracy.csv` shows 100% winners, map numbers,
modes and bans; ≥98% heroes per segment; ≥95% swaps within 3 s; ≥95% maps with team kills within ±1.

## 6. Pilot run, verification and review (US2, US3)

```text
uv run owstudy-collect refs fetch liquipedia --scope pilot
uv run owstudy-collect extract --scope pilot          # resumable; Ctrl-C and rerun skips finished videos
uv run owstudy-collect build --scope pilot
uv run owstudy-collect review --scope pilot
uv run owstudy-collect audit && uv run owstudy-collect validate
```

**You should see:** interrupting `extract` and rerunning it doesn't redo `extracted` videos (FR-012).
Videos are gone from the cache after success (FR-007c). `verify/discrepancies.csv` lists each
disagreement with both values and a time range. `review` resolves one in under 2 minutes on
average (SC-009). After a decision, `build` again gives a resolved discrepancy, and the raw
reading is unchanged. `audit` exits 0 (SC-004). `status` shows ≥85% of processed maps
`verified` without a decision (SC-005).

## 7. Broadcast test (FR-007b)

```text
uv run owstudy-collect broadcast-test <3 pilot series with both a POV and a broadcast VOD>
```

**You should see:** `interim/reports/broadcast_test.md` shows 0 replayed kills accepted, downtime
skipped, and per-field agreement with the POV. The researcher then decides whether to add
`broadcast` to `video.source_kinds` (needed for SC-001 on the pilot, research R17).

## 8. Export (US4)

```text
uv run owstudy-collect export --scope pilot --include verified
uv run owstudy-strength validate data/processed/collection/<export_id>/input
uv run owstudy-collect export --scope pilot --include verified   # again, then diff
```

**You should see:** 001 validation exits 0 (SC-007). `tables/` has `maps.csv`,
`hero_intervals.csv`, `events.csv` and the name lookups, and the export's consistency checks pass:
kill events add up to the map kill totals and to each interval's kills, and each player's
intervals add up to the map length and the team's objective total. **Manual check**: on one gold
map, pick a player who swapped heroes and compare their `hero_intervals` rows with the hand labels. The
two exports are byte-identical apart from `manifest.json` timestamps (SC-008). `summary/excluded_maps.csv` lists every non-exported pilot
map with a reason (FR-025). Each exported map's provenance row gives video, span, extraction
key and confirming sources (SC-003).

## Expansion gate (FR-023)

Add the next region-stage to `scope.approved` only when steps 2 (SC-001), 5 (SC-002) and 8
(SC-007) pass for the pilot and the researcher approves.
