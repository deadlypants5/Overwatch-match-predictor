# Contract: run configuration (YAML)

Default file: `configs/strength/default.yaml`. Unknown keys are an error. The fully resolved
config (defaults filled in) is written to every run directory as `config.resolved.yaml`.

```yaml
schema_version: 1

initial_rating: {team: 1500, player: 1500, player_hero: 1500, hero: 1500}
elo_scale: 400

k:
  team: 20                     # plain Elo K for team ratings (full map, t̂ = 1)
  gamma:                       # Marveldoss time-based K-factor: K = gamma * t̂, t̂ = time / map duration
    player:      {diff: 50, wl: 20}
    player_hero: {diff: 50, wl: 20}

marveldoss:                    # Marveldoss (2018) player update, see research R4/R17
  alpha: 100                   # rating units per (normalized differential per minute); expected +/- = t(p + 4m̂ − 5m_k)/alpha
  beta: 2.0                    # spread of F(x) = 1/(1+e^(−x/beta)) − 0.5
  conserve_points: true        # thesis eq. 2.27 offset correction

normalization:                 # per-mode differential scale, written by `fit-normalization` (training period only)
  min_maps_for_sigma: 30       # fewer training maps for a mode → pooled sigma, flagged
  sigma: {}                    # e.g. {control: 3.1, push: 2.4, ...}; empty → `run` refuses the diff variant

score:
  a: 0.02                      # kill weight
  s: 0.5                       # team-Elo only: logistic scale for normalized map D -> S (winner-clamped)
  def_curve: {kind: linear}    # or {kind: power, gamma: 1.5}

modes:                         # every mode in the input must appear (else exit 4)
  control:    {symmetric: true,  X: 1.0}
  push:       {symmetric: true,  X: 1.0}
  flashpoint: {symmetric: true,  X: 1.0}
  escort:     {symmetric: false, X: 1.0, C: 1.0}
  hybrid:     {symmetric: false, X: 1.0, C: 1.0}
excluded_modes: [clash]

include_unverified: false

splits:
  train_end: 2026-06-30        # inclusive
  validation_end: 2026-09-30   # inclusive; test = after this date


tune:                          # used only by `tune`; each list is a grid axis
  k.team: [5, 10, 20, 30, 50]                 # thesis Elo grid: 1–500 (Table 4.4)
  k.gamma.player.diff: [25, 50, 75, 100, 250]  # thesis grid 25–500 (Table 4.2)
  k.gamma.player_hero.diff: [25, 50, 75, 100, 250]
  marveldoss.alpha: [50, 100, 250, 500]
  marveldoss.beta: [0.5, 1.0, 2.0, 4.0]
  score.a: [0.0, 0.01, 0.02, 0.05]
  score.s: [0.25, 0.5, 1.0]
  modes.escort.C: [0.5, 1.0, 1.5]
  modes.hybrid.C: [0.5, 1.0, 1.5]
```

The thesis's hyperparameter values (e.g., its best pair, 100 and 2500) are on NBA point and
1000-baseline scales and do not transfer. Only the shape of its grid search is reused.
Numeric values above are placeholders; the shipped default is whatever `tune` selects on the
validation period, committed with its `grid_results.csv` (FR-017). For symmetric modes `C` must
be absent (it is fixed to `X`).
