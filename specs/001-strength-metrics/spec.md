# Feature Specification: Strength Metrics

**Feature Branch**: `001-strength-metrics`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "Strength metrics" — measure team, player, and hero strength as
features for the Overwatch map predictor, following the plan in `Math_plan.pdf` (team Elo,
Elo-style player ratings, time-weighted team strength, player-on-hero strength, hero Elo,
composition strength, and ban impact). Glicko/Glicko-2 are out of scope for this feature.

## User Scenarios & Testing *(mandatory)*

The primary user is the project researcher, who feeds a chronological history of professional
Overwatch maps into the rating system and receives pre-map strength values for every team,
player, player-on-hero, and hero, ready to be used as model features and analyzed on their own.

### User Story 1 - Team Elo and pre-map win probability (Priority: P1)

The researcher processes a chronological list of maps and gets, for every map, each team's
rating *before* that map was played and the expected win probability that the ratings imply.
After each map, both teams' ratings are updated using `R_new = R_old + K(S − μ)`.

**Why this priority**: Team Elo is the baseline every other metric must beat (Constitution
Principle V). Without it nothing else can be evaluated.

**Independent Test**: Run on a small hand-built history (e.g., 5 maps, 3 teams) whose correct
ratings were calculated by hand, and compare the output to the hand calculation.

**Acceptance Scenarios**:

1. **Given** two new teams with equal starting ratings, **When** the first map between them is
   processed, **Then** the pre-map expected win probability is 50% for each, and after the map
   the winner's rating rises by exactly `K/2` and the loser's falls by `K/2`.
2. **Given** a history of maps, **When** ratings are produced, **Then** the rating attached to
   each map is the value from before that map's result was applied (no data from the same or
   later maps).
3. **Given** a map that ended in a draw, **When** it is processed, **Then** it counts as an
   outcome of 0.5 for both teams.

---

### User Story 2 - Player ratings and team strength built from players (Priority: P2)

The researcher gets an individual rating for every player, updated after each map they play
using `p̂ = p + K·f(S − μ)`, following Marveldoss (2018). In the score-differential variant,
`S` is the actual +/- (the normalized differential while the player was in play), and `μ` is
the expected +/- built from the player's, teammates', and opponents' ratings. `f` normalizes
the difference to (−0.5, 0.5). The K-factor is proportional to normalized time played, and the
updates conserve the total of all ratings. A team's strength for a map is then the
time-weighted average of its players' ratings, `m_j = Σ t·p / Σ t`, and this player-based
strength can be used in place of team Elo to get a win probability.

**Why this priority**: This is the first metric that goes beyond team Elo and lets roster
changes (substitutions, new signings) affect a team's predicted strength.

**Independent Test**: On a hand-built history that includes a substitution, check that the
player ratings and the time-weighted team strength match a hand calculation, and that the
substitute's rating changes only for maps they played.

**Acceptance Scenarios**:

1. **Given** a team that substitutes one player between maps of a series, **When** the next
   map's team strength is computed, **Then** it uses the ratings of the five players who
   actually played that map.
2. **Given** a player making their first recorded appearance, **When** the map is processed,
   **Then** the player starts from a documented default rating and the default is recorded.
3. **Given** any map, **When** player ratings are updated, **Then** two variants are produced
   side by side: one driven by map win/loss and one driven by the map score differential
   (FR-016), so the two can be compared.
4. **Given** a map where Team A got 30 kills to Team B's 20 and the objective points were
   equal, **When** the score differential is computed, **Then** it equals `a × 10` and is
   positive for Team A.

---

### User Story 2a - Map score differential (Priority: P2)

For every map, the researcher gets a single score differential that captures how decisively a
team won, not just whether it won. It combines kills and objective performance:

`D_AB = a·(Kills_A − Kills_B) + X_n·Obj_A − C_n·Obj_B`

where `a` is a constant weight on kills, and each game mode `n` has two constants: `X_n` weights
attacker (objective-progress) points and `C_n` weights defender (time-based) points. In this form
Team A is attacking and Team B is defending.

- **Symmetric modes**: `C_n = X_n`, so the formula reduces to
  `D_AB = a·(Kills_A − Kills_B) + X_n·(Obj_A − Obj_B)`.
- **Asymmetric modes where both teams attack** (e.g., Escort, Hybrid): the formula is applied to
  each attack, and the results are added. Equivalently, each team's objective total is
  `X_n·(its attacker points) + C_n·(its defender points)`, and the differential is
  `a·(Kills_A − Kills_B) + (A's objective total − B's objective total)`.

Objective points are earned as follows:

- **Symmetric modes** (both teams play for the same objective at once, e.g., Control, Push,
  Flashpoint): each team's objective points come directly from its objective progress.
- **Asymmetric modes, attacking side** (e.g., Escort, Hybrid): objective points come directly
  from objective progress.
- **Asymmetric modes, defending side**: defenders can't make objective progress, so they earn
  objective points from the attackers' time remaining. The less time attackers have left when
  their attack ends, the more points defenders earn; the more time left, the fewer.

**Why this priority**: Win/loss alone gives every player on a team the same update (players
stay in for the whole map). A margin-based signal is what makes the +/- approach in
`Math_plan.pdf` meaningful in Overwatch.

**Independent Test**: For a small set of hand-scored maps covering every game mode (including
both attack/defense halves of an asymmetric map), compare the system's differential to the hand
calculation.

**Acceptance Scenarios**:

1. **Given** a Control map, **When** the differential is computed, **Then** both teams' objective
   points come from their objective progress, scaled by the Control constant `X_control`, and
   `C_control = X_control`.
2. **Given** an Escort map where Team A attacks first and Team B attacks second, **When** the
   differential is computed, **Then** each team gets attacker points for its own attack
   (weighted by `X_escort`) and defender points based on the time the other team had left at the
   end of its attack (weighted by `C_escort`).
3. **Given** Team A attacks while Team B defends, **When** that attack is scored, **Then** its
   contribution is `X_n·Obj_A − C_n·Obj_B`, so raising `C_n` increases how much a strong defense
   counts relative to attacking progress.
4. **Given** attackers finish the map with a lot of time remaining, **When** defender points are
   computed, **Then** defenders earn fewer points than they would if the attackers had finished
   with little time remaining.
5. **Given** two maps with the same kill and objective differences but different game modes,
   **When** differentials are computed, **Then** they differ only by the mode constants `X_n`
   and `C_n`.
6. **Given** the differential, **When** it is used as the outcome `S` in a **team Elo** update,
   **Then** it is converted to a value between 0 and 1 (0.5 = even) by a documented mapping,
   and the winner of the map never gets `S` below 0.5. (Player and player-on-hero updates use
   the normalized differential directly as the actual +/-, per Marveldoss.)
7. **Given** maps from different game modes, **When** differentials are used in any update,
   **Then** each is first divided by that mode's normalization constant, fitted on the
   training period only, so that one unit of normalized differential per minute means the
   same thing in every mode.

---

### User Story 3 - Player-on-hero strength (Priority: P3)

The researcher gets a separate rating for each player on each hero they play (`h_jik`), so the
same player on two different heroes counts as two different "people". The player's overall
strength on a map is then the time-weighted average across the heroes they played on it,
`p_ji = Σ_k t_jik·h_jik / Σ_k t_jik`.

**Why this priority**: This distinguishes teammates who always play together (e.g., two
players who have played every map together for five years and so share identical outcome
histories), which plain player ratings cannot do.

**Independent Test**: On a hand-built history where a player switches heroes partway through a
map, check that each hero rating is updated in proportion to time played on that hero and that
the player's combined strength matches a hand calculation.

**Acceptance Scenarios**:

1. **Given** a player who plays hero A for 6 minutes and hero B for 4 minutes on a map,
   **When** that map is processed, **Then** the player's combined strength for the map weights
   hero A at 60% and hero B at 40%.
1a. **Given** a player who plays hero A for the first 5 minutes of a map and then swaps,
   **When** the hero A rating is updated, **Then** the update uses only those 5 minutes: the
   opponents' heroes during those minutes (for the expected outcome), the score differential
   earned during those minutes (differential variant), and a weight equal to those 5 minutes'
   share of the map. Nothing that happened after the swap affects the hero A rating.
2. **Given** two players who have played every map together, **When** they play different
   heroes, **Then** their player-on-hero ratings can differ.
3. **Given** a finished run, **When** the researcher compares each player-on-hero rating to that
   player's raw win rate on that hero, **Then** a comparison report is produced.

---

### User Story 4 - Hero strength and composition strength (Priority: P4)

The researcher gets a "hero Elo" for every hero, `H_k`: the time-weighted average of every
player-on-hero rating for that hero across all teams. Two team-level metrics are built from it:

- **Composition strength**: the heroes *currently in play* for a team, `comp = Σ_players H_k`
  over each player's current hero. It is a snapshot with no time weighting. It changes whenever
  a player swaps, so a map has one composition strength per segment.
- **Hero-weighted team strength**: a team strength metric that accounts for hero swaps,
  `Σ_i Σ_k (t_jik / T_ji)·H_k`, i.e., each player's heroes weighted by the share of the map
  played on them.

Both can be compared to raw hero win rates.

**Why this priority**: Hero and composition strength are new features in their own right and
let the project describe the meta independently of who is playing.

**Independent Test**: On a hand-built history, check hero strengths and composition strength
against hand calculations, and confirm a report compares hero Elo to hero win rate.

**Acceptance Scenarios**:

1. **Given** a hero played by several players for different lengths of time, **When** its hero
   strength is computed, **Then** each player's contribution is weighted by time played on that
   hero.
2. **Given** a hero with no recorded play before a map, **When** composition strength is
   computed for that map, **Then** the hero uses the documented default and is flagged as
   having no history.
2a. **Given** a team that starts with heroes {A, B, C, D, E} and one player swaps E → F after
   4 minutes, **When** composition strength is computed, **Then** the first segment's value is
   `H_A + H_B + H_C + H_D + H_E`, the second's is `H_A + H_B + H_C + H_D + H_F`, and neither value
   depends on how long the segment lasted.
2b. **Given** the same map, **When** hero-weighted team strength is computed, **Then** E and F
   are each weighted by their share of that player's time on the map.
3. **Given** every map is tagged with a patch, **When** hero strengths are reported, **Then**
   they can be viewed per patch.

---

### User Story 5 - Ban impact (Priority: P5)

For each map, the researcher gets a measure of how much each team's ban weakens the opponent:
each affected player's strength is recalculated without the banned hero (sum over `k ≠ x`) and
compared to their strength with it.

**Why this priority**: It's a distinctive analysis that depends on Stories 3 and 4 being
finished first.

**Independent Test**: On a hand-built history where one player mostly plays the banned hero,
check that the drop in that player's and team's strength matches a hand calculation.

**Acceptance Scenarios**:

1. **Given** a ban on a hero a player has never played, **When** ban impact is computed,
   **Then** that player's strength loss is zero.
2. **Given** a ban on the only hero a player has ever played, **When** ban impact is computed,
   **Then** the result is flagged as undefined for that player instead of dividing by zero.
3. **Given** ban impact for many maps, **When** it is reported alongside outcomes, **Then** the
   researcher can see whether larger strength losses go with losing the map.

### Edge Cases

- A team rebrands or a player changes their in-game name: ratings follow the stable ID, not the
  display name.
- A player appears for a new team: the player's rating carries over; team Elo stays with the
  team.
- Map data is missing hero time-played: player-on-hero and hero metrics skip that map for the
  affected player and flag it; team Elo still updates.
- Map has hero-swap timing but no per-segment kills/objective: the differential variant of the
  player-on-hero update skips that map (flagged `no_segment_score`) rather than falling back to
  the whole-map differential; the win/loss variant still updates per segment.
- Two maps share the same date: they are ordered by series and map number; if that's still
  unclear, the run stops and reports the conflict rather than guessing an order.
- A map with fewer or more than five players recorded for a team: flagged as a data error;
  team Elo still updates, player-based metrics skip the map for that team.
- A map marked as unverified (see Constitution Principle IV): it can be included or excluded by
  a setting, and both runs are supported.
- Kill counts or objective progress are missing for a map: the score-differential variant skips
  that map (flagged); the win/loss variant still updates.
- A team loses the map on objectives but wins the kill count by a wide margin: the
  differential may favor the loser. The mapping to `S` caps the loser at below 0.5 (see User Story
  2a, scenario 5) and these maps are counted in the report.
- Asymmetric map that goes past regulation (extra rounds/time banks): each attack's time
  remaining is measured from that team's own attack clock, including banked time.
- A game mode added to the game that has no `X_n` (or, if asymmetric, no `C_n`) yet: the run stops and reports the
  missing constant rather than using a default.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST take as input a chronological list of maps, each with: series ID, map
  number, date, patch, map name, game mode, the two teams, each team's players, each player's
  time played per hero, each team's ban, the outcome (win/loss/draw), each team's kill total,
  each team's objective progress, and for asymmetric modes which team attacked when and the
  attackers' time remaining at the end of each attack. Each map MUST also be divided into
  **segments**, time intervals in which no player changes hero, each with its duration, every
  player's hero, and each team's kills and objective progress during that segment.
- **FR-002**: System MUST process maps strictly in chronological order and attach to each map
  the ratings from *before* that map's result is applied.
- **FR-003**: System MUST compute team Elo and the expected win probability for each map using
  the standard logistic Elo expectation.
- **FR-004**: System MUST compute player ratings, updated after each map the player plays.
- **FR-005**: System MUST compute time-weighted team strength from player ratings and a win
  probability derived from it.
- **FR-006**: System MUST compute player-on-hero ratings, updated per segment: each segment's
  update uses only that segment (its expected outcome from the heroes in play during it, its own
  score differential in the differential variant, and a weight equal to its share of the map).
  Combined player strength is the time-weighted average across heroes played.
- **FR-007**: System MUST compute hero strength as the time-weighted average of all
  player-on-hero ratings for that hero; **composition strength** per team per segment as the sum
  of `H_k` over the heroes currently in play (no time weighting); and **hero-weighted team
  strength** per team per map as the time-weighted sum `Σ_i Σ_k (t_jik/T_ji)·H_k`.
- **FR-019**: Every output feature MUST be labeled with when it becomes known: `pre_map`
  (before the map starts), `map_start` (once bans and starting heroes are known), `segment`
  (at the start of that segment), or `post_map` (only after the map ends, e.g., anything weighted
  by this map's hero times). Only `pre_map` and `map_start` features may be used for pre-map
  prediction (Constitution Principle II).
- **FR-008**: System MUST compute ban impact for each player and team on each map, as the
  difference between strength with and without the banned hero.
- **FR-009**: Player, player-on-hero, and hero ratings MUST be computed in two variants side by
  side: one using map win/loss as the outcome `S`, and one using the normalized score
  differential (FR-016, FR-020) as the actual +/- score in the Marveldoss update. Team Elo MAY
  also be computed in both variants, in which case the differential is mapped to 0–1.
- **FR-010**: Every tunable parameter MUST come from a configuration that is saved alongside
  each run's output: K-factor scales `γ` per entity type, starting rating, the rating scale `α`,
  the spread `β` of `f`, the kill weight `a`, each mode's attacker constant `X_n` and defender
  constant `C_n`, the defender time-to-points function, the per-mode normalization constants
  `σ_n`, and the team-Elo differential-to-`S` mapping.
- **FR-020**: The player and player-on-hero updates MUST follow Marveldoss (2018):
  expected +/- `μ = t·(p_i + 4·m̂_−i − 5·m_opp)/α`; `b = f(S − μ)` with `f` bounded to
  (−0.5, 0.5); K-factor `K = γ·t̂`, with `t̂` the time in play divided by the map's duration;
  and a point-conservation correction so the ratings of all entities in a map (or segment)
  sum to the same total before and after the update. Score differentials MUST be normalized
  per game mode by constants fitted on the training period only.
- **FR-011**: System MUST keep each map's patch with its ratings so every metric can be
  reported per patch. The Elo update rule MUST be kept separate from the metric calculations so
  a different rating system could be added later without changing the input or output format
  (Constitution Principle III).
- **FR-012**: System MUST produce comparison reports: each metric against its naive
  counterpart (hero Elo vs. hero win rate; player-on-hero rating vs. player win rate on that
  hero), and each strength-based win probability against team Elo, using log loss, Brier score,
  and accuracy on a chronological hold-out period.
- **FR-013**: System MUST flag, not silently drop, maps or players excluded from any metric, and
  report how many were excluded and why.
- **FR-014**: Given the same input and configuration, the system MUST produce identical output.
- **FR-015**: System MUST include a set of hand-calculated reference examples for every metric,
  and the output MUST match them.
- **FR-016**: System MUST compute a map score differential
  `D_AB = a·(Kills_A − Kills_B) + X_n·Obj_A − C_n·Obj_B` (Team A attacking, Team B defending),
  with a separate attacker constant `X_n` and defender constant `C_n` for each game mode. In
  symmetric modes `C_n = X_n`, so `D_AB = a·(Kills_A − Kills_B) + X_n·(Obj_A − Obj_B)`. In
  asymmetric modes where both teams attack, the formula MUST be applied to each attack and the
  results added. The same formula MUST also be computed per segment from that segment's kills
  and objective points, and segment differentials MUST sum to the map differential. Objective
  points MUST come from objective progress in symmetric modes and on
  attack. On defense in asymmetric modes, they MUST come from the attackers' time remaining, so
  that less time remaining gives defenders more points. `D_AB = −D_BA` MUST always hold.
- **FR-017**: The constants `a`, `X_n`, and `C_n` (asymmetric modes only; symmetric modes have
  `C_n` fixed to `X_n`) MUST be tuned on the validation period only
  (Constitution Principle II), and the chosen values MUST be reported along with how sensitive
  the results are to them.
- **FR-018**: The report MUST compare the win/loss variant and the score-differential variant of
  each metric on the same hold-out period.

### Key Entities

- **Map Record**: One played map: series, map number, date, patch, map name, mode, two teams,
  per-player hero time, bans, outcome, team kills, objective progress, attack/defense timing,
  verification status.
- **Game Mode**: Stable ID, whether it's symmetric or asymmetric, its attacker constant `X_n`,
  and its defender constant `C_n` (equal to `X_n` for symmetric modes).
- **Map Score**: Per map: each team's kills, objective points (by attack and defense for
  asymmetric modes), the differential `D_AB`, and the derived outcome `S`.
- **Segment**: A time interval of a map in which no player changes hero: start/end time, each
  player's hero, each team's kills and objective points during it, its differential, its
  composition strength per team.
- **Team**: Stable ID, display-name history, and a team Elo history.
- **Player**: Stable ID, alias history, team history, player rating history.
- **Hero**: Stable ID, role, hero strength history per patch.
- **Player-on-Hero Rating**: Rating for one player on one hero, with time played and number of
  maps.
- **Rating Snapshot**: The pre-map value of any rating attached to a specific map. This is what downstream models consume.
- **Ban Impact Record**: Per map, per team: banned hero, each opposing player's strength with
  and without it, and the team-level change.
- **Run Configuration**: All rating parameters for one run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of hand-calculated reference examples match the system's output (to 4
  decimal places).
- **SC-002**: An automated check confirms that 0 maps have a rating snapshot that uses
  information from that map or later.
- **SC-003**: On the chronological hold-out period, team-Elo win probabilities do better than a
  coin flip on log loss (below 0.693).
- **SC-004**: Every strength metric (player-based, player-on-hero, hero/composition, ban impact)
  has a recorded comparison against team Elo and against its naive counterpart, whether the
  result is positive or negative.
- **SC-005**: Re-running the full history with the same input and configuration produces
  output that is identical byte for byte.
- **SC-006**: The researcher can process a full season of professional maps (about 1,000+ maps)
  and get all metrics in under 5 minutes on a personal computer.
- **SC-007**: For every game mode, hand-scored reference maps (including both halves of an
  asymmetric map) match the system's score differential exactly.
- **SC-008**: The report states, for each metric, whether the score-differential variant or
  the win/loss variant has lower hold-out log loss.

## Assumptions

- Map data comes from the separate data collection feature. Until that exists, this feature is
  built and tested on hand-built and sample histories in the agreed input format.
- Players play the whole map for their team (as stated in `Math_plan.pdf`); only heroes change
  mid-map, so time played is tracked per hero.
- Default starting rating is 1500 for teams, players, player-on-hero, and heroes. The thesis
  uses 1000, but the starting level cancels in the expected +/-. `γ`, `α`, and `β` are tuned on
  the validation period only (Constitution Principle II), as the thesis tuned its parameters on
  a cross-validation set.
- The player update follows Marveldoss, *An Elo-Based Approach to Model Team Players and
  Predict the Outcome of Games* (Texas A&M, 2018). The thesis's time normalization divides
  minutes by 48, a full NBA game. Here, time is divided by the map's own duration, because map
  length varies by mode. Home-court advantage (thesis §1.4) is not modeled.
- Because every player plays the full map, the player-level expected +/- is the same for all
  five teammates, so player-level updates are identical within a team on any single map (the
  issue `Math_plan.pdf` raises). Player-on-hero segments are the part of the model that
  separates teammates.
- Hero strength is computed by the time-weighted aggregation formula `H_k` in `Math_plan.pdf`.
  Treating each hero as a "team" that receives its own direct Elo updates is a possible later
  experiment, not part of this feature.
- Composition strength is the sum of the strengths of the heroes currently in play, as written
  in `Math_plan.pdf`, with no time weighting. The time-weighted version is a separate team
  strength metric (hero-weighted team strength), not a composition variant.
- Ratings carry over across seasons and patches with no reset. Patches are recorded so their
  effects can be analyzed, but ratings don't adjust automatically when a patch lands.
- Glicko and Glicko-2 (rating uncertainty, faster movement after patches) are out of scope for
  this feature and may be specified separately later.
- Each team bans one hero per map.
- Game modes in scope: Control, Push, Flashpoint (symmetric) and Escort, Hybrid (asymmetric).
  Clash is no longer played and is out of scope; Clash maps in the input are excluded and
  flagged (FR-013).
- Team Elo and (hero-agnostic) player ratings use the whole-map outcome, because teams and
  players are in for the whole map. Player-on-hero ratings use per-segment data, so the data
  collection feature MUST provide time-stamped hero swaps, kills, and objective progress.
  In the win/loss variant a segment has no result of its own, so it uses the map result, but
  its expected outcome and weight still come from the segment.
- Default defender time-to-points function is linear: defender points scale with the
  fraction of the attack clock the attackers used. Other shapes can be compared during tuning.
- Default differential-to-`S` mapping is a logistic curve centered at 0, constrained so the map
  winner's `S` is at least 0.5 and the loser's is at most 0.5.
- Objective progress is measured in each mode's natural unit (capture percentage, payload
  distance/checkpoints, push distance, points captured) and scaled to a common 0–1 range per
  mode before applying `X_n`. Defender points are also scaled to 0–1 before applying `C_n`.
- Series-level prediction and training the final prediction model are out of scope here (that's
  the later modeling feature).
