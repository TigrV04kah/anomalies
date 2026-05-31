# Line Monitor System Overview

Last updated: 2026-05-28

This document describes the current state of the Line Monitor project: what runs locally, what is deployed to Vercel, how data moves through the system, and what anomaly rules are active.

## Goal

The system monitors the current betting line, detects configured anomalies, stores the results in Supabase, and exposes them in a web UI for human review.

Reviewers can mark each anomaly as:

- `defect`
- `normal`

They can also add a comment and reviewer name. Existing reviews stay attached to the same anomaly if it disappears and later appears again.

## High-Level Architecture

There are two separate parts:

1. Local monitor pipeline on the workstation.
2. Web UI deployed to Vercel.

The local pipeline is responsible for all Mongo access and all anomaly detection. Vercel does not access Mongo and does not run Python checks.

Data flow:

```text
Mongo Line.LineGame
  -> run_line_monitor.py
  -> snapshots/current_line_snapshot.zip
  -> analyze_line_rules.py
  -> reports/*.csv
  -> Supabase
  -> Vercel UI / local UI
```

## Local Pipeline

Main launcher:

```text
Start Line Monitor.cmd
```

It runs:

```text
start_line_monitor.ps1
```

Current behavior:

- starts local preview UI at `http://127.0.0.1:8766/`;
- immediately runs a full line monitor pass;
- repeats every 5 minutes;
- keeps running while the command window remains open;
- stop with `Ctrl+C`.

Important: the script opens the local UI once at startup. It does not reopen the browser after every run.

Main pipeline file:

```text
run_line_monitor.py
```

Current mode:

- default mode fetches the full current line from Mongo every run;
- incremental mode exists only for debugging via `--incremental`;
- full snapshots are stored in `snapshots/current_line_snapshot.zip`;
- state is stored in `linegame_state.json`.
- checks run in parallel against the already loaded snapshot dataframe.

The full-line approach is intentional: old events can change, so checking only new events is not reliable enough.

## Environment Variables

Required locally:

- `LINE_MONGO_URI`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Vercel needs only:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Secrets must stay in environment variables. Do not hardcode them in project files.

## Mongo Mapping

Mongo stores raw fields. The export layer normalizes them.

Important raw-to-normalized fields:

| Raw Mongo | Normalized |
|---|---|
| `I` | `GameId` |
| `MI` | `MainGameId` |
| `T` | `GameType` |
| `Pr` | `Period` |
| `S` | `SportName` |
| `C` | `Champ` |
| `H` | `Opp1` |
| `A` | `Opp2` |

Event fields:

| Raw Mongo event | Normalized |
|---|---|
| `T` | `EventId` / `EventType` |
| `P` | `Param` |
| `C` | `Coef` |
| `OC` | `CoefOrig` |
| `Cn` | `ContoraName` |

Current checks use `Coef`, not `CoefOrig`.

## Supabase Tables

Main tables:

| Table | Purpose |
|---|---|
| `monitor_runs` | One row per pipeline run. Stores run metadata and summary JSON. |
| `check_results` | All anomaly results. Stores payload, status, review fields, and history fields. |
| `run_statistics` | Dashboard-level statistics for each run. |
| `run_check_statistics` | Per-check statistics for each run. |

`check_results` fields that matter operationally:

| Field | Meaning |
|---|---|
| `result_key` | Stable anomaly identity. Primary key. |
| `check_name` | Internal check id. |
| `check_title` | Human-readable check name used by UI filters. |
| `status` | Usually `DIFF`. |
| `first_seen_at` | When this stable anomaly first appeared. |
| `last_seen_at` | Last time this stable anomaly appeared. |
| `last_run_id` | Latest run where this anomaly was present. |
| `occurrence_count` | Increments when the same anomaly appears again. |
| `payload_json` | Check-specific details for rendering. |
| `verdict` | Reviewer decision: `defect` or `normal`. |
| `review_comment` | Reviewer comment. |
| `reviewed_by` | Reviewer name. |
| `reviewed_at` | Review timestamp. |

History behavior:

- If an anomaly appears, it is stored in `check_results`.
- If it disappears on the next run, it is not deleted.
- The `current` UI scope shows only anomalies with `last_run_id` equal to the latest run.
- The `history` UI scope can show older anomalies.
- If the same anomaly appears later with the same `result_key`, the old row is updated and its existing review stays attached.

## Web UI

Vercel deploys only the web/UI side:

- `index.html`
- `app.js`
- `styles.css`
- `check_definitions.json`
- `api/*.js`

Local Python files, snapshots, reports, notebooks, CSV and ZIP files are excluded from Vercel by `.vercelignore`.

UI tabs:

- `Текущие`: anomalies from latest run only.
- `История`: older anomaly records can be viewed.
- `Dashboard`: run statistics and per-check counts.
- `Справка`: descriptions of checks from `check_definitions.json` / `app.js`.

API routes:

| Route | Purpose |
|---|---|
| `/api/anomalies` | Reads anomaly rows from Supabase. |
| `/api/review` | Saves reviewer verdict/comment. |
| `/api/dashboard` | Reads run statistics. |

Important UI maintenance detail: check filters in `index.html`, active titles in `api/anomalies.js`, titles in `check_metadata.py`, and descriptions in `check_definitions.json` should be updated together when adding a new check.

## Active Checks

All checks are implemented in:

```text
analyze_line_rules.py
```

### Main = Period (average)

Internal name:

```text
period_deviations_average
```

Purpose:

Checks whether the period-0 total equals the sum of full-period totals.

Supported full groups:

| Sport | Required periods |
|---|---|
| `Football`, `FootHall`, `Handball`, `Rugby` | `1 + 2` |
| `Hockey`, `Floorball` | `1 + 2 + 3` |
| `Basketball`, `AustralianFootball`, `WaterPolo` | `1 + 2 + 3 + 4` |

Separate half logic:

- if periods `11` and `12` both exist, compare period `0` to `11 + 12`;
- do not mix halves with normal periods.

Central line selection:

- uses total and individual total markets with coefficients in the configured acceptable range;
- aggregates `Param` by `MainGameId`, `GameType`, `Period`, and `EventType`.

Critical delta by main total:

| Main total | Critical delta |
|---:|---:|
| `<= 5` | `1.0` |
| `<= 10` | `1.5` |
| `<= 20` | `2.0` |
| `<= 35` | `2.0` |
| `<= 60` | `3.0` |
| `<= 80` | `4.0` |
| `<= 120` | `6.0` |
| `> 120` | `8.0` |

### Total = Ind total 1 + Ind Total 2 (average)

Internal name:

```text
total_deviations_average
```

Purpose:

Checks that a total is consistent with individual team totals:

```text
Total ~= IndTotal1 + IndTotal2
```

Line selection:

- for each `MainGameId`, `GameType`, `Period`, and side, choose the line closest to coefficient `1.95`;
- anomaly if the delta is greater than `1.5`.

### Stat Conflicts

Internal name:

```text
stat_conflicts
```

Purpose:

Checks whether a match favorite has contradictory direction in football statistical markets.

Match favorite:

- based on `GameType = Main`, `Period = 0`, events `p1` and `p2`;
- favorite exists only if its coefficient is below `1.8` and lower than the opponent coefficient.

Stat rule:

- if match favorite is `p1`, then the stat coefficient for `p1` should not be higher than `p2`;
- if match favorite is `p2`, then the stat coefficient for `p2` should not be higher than `p1`;
- if the favorite side has the higher stat coefficient, this is `DIFF`.
- for inverted markets `Save` and `GoalFromGates`, the logic is reversed: the match favorite should be the outsider by this statistic, so its statistic coefficient should be higher than the opponent coefficient.

Checked football stat types:

- `Corners`
- `Tackles`
- `ShotsOnTarget`
- `ShotByGates`
- `Save`
- `GoalFromGates`
- `PossessionPercentage`

Special case:

- `Tackles` is checked only if the match favorite coefficient is `<= 1.4`.

Current excluded case:

- `Yellow` is not checked in `Stat Conflicts`.

### Football Stat Relations

Internal name:

```text
football_stat_relations
```

Purpose:

Checks consistency between shot-related football statistics.

Part 1: central totals.

- `ShotsOnTarget` = shots on target.
- `ShotByGates` = shots by/on goal.
- Central line is the `Total_B` or `Total_M` line closest to 50% implied probability.
- `ShotsOnTarget` central total must not be greater than `ShotByGates` central total.

Part 2: relation to goal kicks.

- `GoalFromGates` = goal kicks.
- If a team is favorite below `1.8` on `ShotsOnTarget` or `ShotByGates`, it should be the outsider on `GoalFromGates`.
- This direction is intentionally inverted: the team that attacks/shoots more usually should have fewer goal kicks.
- Anomaly appears when the shot-stat favorite is not the outsider on `GoalFromGates`.

### Basketball Players

Internal name:

```text
basketball_players
```

Purpose:

Checks player statistics in basketball markets.

Scope:

- only `SportName = Basketball`;
- only `GameType = GoalPlayers`;
- only players that have a points total market;
- central line is the line closest to 50% implied probability.

Period checks:

- points in quarters `1`, `2`, `3`, `4` are compared with full-game points divided by `4`;
- points in halves `11`, `12` are compared with full-game points divided by `2`;
- anomaly appears when the absolute delta is greater than the threshold below.

| Full-game points parameter | Allowed delta |
|---:|---:|
| `< 5` | `0.5` |
| `< 10` | `1.0` |
| `< 15` | `1.5` |
| `< 20` | `2.0` |
| `< 25` | `2.5` |
| `< 30` | `3.0` |
| `>= 30` | `3.5` |

Monotonicity checks:

- for `Total_B` style player markets, coefficient should increase as `Param` increases;
- for `Total_M` style player markets, coefficient should decrease as `Param` increases;
- close parameter steps are ignored if implied probability differs by no more than `3%`.

Allowed close-step exceptions:

| Minimum parameter | Max parameter diff |
|---:|---:|
| `< 10` | `1.0` |
| `< 20` | `1.5` |
| `< 30` | `2.0` |
| `> 30` | `2.5` |

Combination checks:

- `points_rebounds` should be close to `points + rebounds`;
- `points_assists` should be close to `points + assists`;
- `rebounds_assists` should be close to `rebounds + assists`;
- `points_rebounds_assists` should be close to `points + rebounds + assists`;
- current combination delta threshold is `1.5`.

### Basketball Q4 Handicap Shift

Internal name:

```text
basketball_q4_handicap_shift
```

Purpose:

Checks whether basketball 4th-quarter handicap markets are shifted too far from the 1st-quarter handicap markets.

Scope:

- only `SportName = Basketball`;
- only `GameType = Main`;
- only periods `1` and `4`;
- only `EventType = Fora_1` and `Fora_2`.

Line selection:

- in the 1st quarter, choose the central handicap line by coefficient closest to `1.95`;
- do the same for the 4th quarter;
- compare each side independently: `Fora_1` with `Fora_1`, `Fora_2` with `Fora_2`.

Anomaly scenarios:

- if the same 1st-quarter parameter exists in the 4th quarter, compare implied probabilities `1 / Coef`; absolute probability delta above `25` percentage points is `DIFF`;
- if the same parameter does not exist in the 4th quarter, compare central parameters; absolute parameter delta above `4.5` points is `DIFF`.

### Period Conflicts

Internal name:

```text
period_conflicts
```

Purpose:

Checks whether the favorite in full match remains the favorite by periods.

Classification:

| Coefficient | Zone |
|---:|---|
| `< 1.8` | `favorite` |
| `1.8 <= coef < 2.3` | `equal` |
| `>= 2.3` | `outsider` |

Anomaly:

- match favorite exists in period `0`;
- period favorite exists in another period;
- favorites are different.

Esports exception:

- applies to `SubSport` `Valorant`, `CoD`, `Dota2`, `CS2`;
- if the match-side implied probability delta `abs(1 / p1 - 1 / p2)` is below `0.14`;
- and the period-side implied probability delta is below `0.15`;
- then the favorite flip is treated as a soft conflict and is not reported.

### Tennis Special. What Earlear

Internal name:

```text
tennis_special_what_earlear
```

Purpose:

Checks tennis special market "what earlier" against `Ace` and `Breaks` totals.

If totals point to one expected scenario but the "what earlier" odds point the opposite way, the row is `DIFF`.

## Global Exclusions

Before checks run, rows are excluded if they match known noisy patterns.

Opponent text exclusions:

- `команды`
- `класк`
- `Yellow`
- `Хозяева`
- `Гости`

Championship exclusions:

- `FIFA`
- `Belarus Sky League`
- `IPBL`
- `Short Football`
- `Regional League`
- `Альтернативные`

Contora exclusions:

- `XBetLineRegions`
- `XbetLineConstructor`

## Running Manually

Run the normal continuous monitor:

```powershell
& "C:\Users\Bogomolov.v\Documents\Электронный Агент-Букмекер\Start Line Monitor.cmd"
```

Run one full monitor pass from the project folder:

```powershell
& "C:\Users\Bogomolov.v\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run_line_monitor.py
```

Run a forced full pass:

```powershell
& "C:\Users\Bogomolov.v\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run_line_monitor.py --force-full
```

The normal run writes to Supabase.

## Outputs

Local outputs:

| Path | Meaning |
|---|---|
| `snapshots/current_line_snapshot.zip` | Latest full line snapshot. |
| `reports/*.csv` | Latest CSV output for every check. |
| `linegame_state.json` | Last run state. |

Supabase outputs:

| Table | Meaning |
|---|---|
| `monitor_runs` | Run metadata. |
| `check_results` | Anomaly rows and reviewer decisions. |
| `run_statistics` | Dashboard summary. |
| `run_check_statistics` | Dashboard per-check rows. |

## Deployment

The repository is pushed to:

```text
https://github.com/TigrV04kah/anomalies
```

Vercel deploys the web UI from GitHub.

Local scripts still run only on the workstation. Pushing to GitHub does not move the Mongo/Supabase pipeline to Vercel.

## Current Known Maintenance Notes

- When adding a new check, update all of these:
  - `analyze_line_rules.py`
  - `check_metadata.py`
  - `check_definitions.json`
  - `app.js` if custom UI rendering is needed
  - `index.html` check filter
  - `api/anomalies.js` active check title whitelist
- Old anomalies are intentionally retained in Supabase history.
- Existing `defect/normal` review data remains attached to a stable anomaly if it reappears.
- The monitor interval is currently 5 minutes.
- Full runs currently take roughly around 2 minutes, depending on Mongo and Supabase response time.
