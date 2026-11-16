# Contract: input directory

An input directory contains UTF-8 CSV files with a header row. Empty cell = missing.
Entity semantics and validation rules: [data-model.md §1](../data-model.md).

```text
<input-dir>/
├── maps.csv
├── segments.csv
├── segment_heroes.csv
├── bans.csv
├── attacks.csv          # rows only for asymmetric-mode maps
└── entities/
    └── aliases.csv      # optional; identity mapping if absent
```

## maps.csv

```csv
map_id,series_id,map_number,date,series_start,patch_id,map_name,mode_id,team_a_id,team_b_id,winner,kills_a,kills_b,obj_a,obj_b,verification,source_ref
m0001,s001,1,2026-03-01,2026-03-01T18:00,p2026.1,Busan,control,T1,T2,a,30,20,1.0,0.62,verified,yt:abc123@00:12:40
m0002,s001,2,2026-03-01,2026-03-01T18:00,p2026.1,King's Row,hybrid,T1,T2,b,41,44,,,verified,yt:abc123@00:31:05
```

`obj_a`/`obj_b` are filled for symmetric modes and left empty for asymmetric (which use attacks.csv).

Map-level `kills_*`/`obj_*` may be left empty when segments carry them (they are then summed
from segments). If both are given they must agree.

## segments.csv

A new segment starts whenever any of the 10 players changes hero, and at every round or attack
boundary.

```csv
map_id,segment_no,start_s,end_s,attack_order,clock_elapsed_start_s,clock_elapsed_end_s,kills_a,kills_b,obj_a,obj_b
m0001,1,0,360,,,,18,11,0.55,0.30
m0001,2,360,600,,,,12,9,0.45,0.32
m0002,1,0,300,1,0,300,14,10,0.6,
m0002,2,300,505,1,300,505,7,9,0.4,
```

For asymmetric segments `obj_*` is the attacker's progress gained (the defender's cell is
empty), and defender points come from the clock columns.

## segment_heroes.csv

```csv
map_id,segment_no,team_id,player_id,hero_id
m0001,1,T1,P02,tracer
m0001,2,T1,P02,sombra
```

(10 rows per segment: 5 players × 2 teams.) Hero seconds per player are derived from segment
durations. Here P02 has tracer 360 s and sombra 240 s.

## bans.csv

```csv
map_id,banning_team_id,hero_id
m0001,T1,ana
m0001,T2,tracer
```

## attacks.csv

```csv
map_id,attack_order,attacking_team_id,obj_progress,attack_clock_s,time_remaining_s
m0002,1,T1,1.0,600,95
m0002,2,T2,1.0,600,140
```

## entities/aliases.csv

```csv
entity_type,alias,stable_id,valid_from,valid_to
team,Old Name Esports,T1,2024-01-01,2025-06-30
player,NewTag,P02,2026-01-01,
```

## Validation errors (all reported together, exit 1)

Unknown column / missing required column; duplicate `map_id` or `(series_id, map_number)`;
segment/ban/attack referencing an unknown `map_id`; segments with gaps, overlaps, or
`end_s ≤ start_s`; a segment crossing an attack boundary; clock positions outside the attack
clock; map totals disagreeing with summed segments; `time_remaining_s > attack_clock_s`;
progress outside [0,1]; asymmetric map without attacks for both teams; alias overlaps.
Non-fatal data problems (bad roster size, missing hero time, missing score, missing segment
score, Clash) are **not** errors. They become exclusion records.
