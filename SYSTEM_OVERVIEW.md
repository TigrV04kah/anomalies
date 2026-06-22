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

Soft near-threshold cases:

- `AustralianFootball / Main / IndTotal_*`: `SOFT` when `abs(delta) <= critical_delta + 1.0`;
- `Football / Corners / IndTotal_*` and `Football / ShotsOnTarget / IndTotal_*`: `SOFT` when `abs(delta) <= critical_delta + 0.25`;
- `Football / ShotByGates / Total_B|Total_M`: `SOFT` when `abs(delta) <= critical_delta + 0.5`.

### Total = Ind total 1 + Ind Total 2 (average)

Internal name:

```text
total_deviations_average
```

Production status:

```text
legacy / inactive
```

This rule is kept in the codebase and UI descriptions for historical anomalies and possible rollback, but it is not included in the active production `CHECKS` set. `Poisson Total Consistency` is the active replacement.

Purpose:

Checks that a total is consistent with individual team totals:

```text
Total ~= IndTotal1 + IndTotal2
```

Line selection:

- for each `MainGameId`, `GameType`, `Period`, and side, choose the line closest to coefficient `1.95`;
- if any of the three selected lines has coefficient below `1.5` or above `2.6`, skip this group because there is no reliable central line;
- exception for `Tennis / Ace`: if the selected general `Total_B` has coefficient `2.4-2.7`, subtract `1.0` from the total before comparison; if the selected general `Total_M` has coefficient `2.4-2.7`, add `1.0` before comparison;
- if the chosen individual-total coefficient is between `1.5` and `1.65`, adjust that individual total `Param` toward the center: add `0.5` for `IndTotal_B`, subtract `0.5` for `IndTotal_M`;
- if the chosen individual-total coefficient is between `2.3` and `2.6`, use the inverse adjustment: subtract `0.5` for `IndTotal_B`, add `0.5` for `IndTotal_M`;
- `Volleyball` period `0` is excluded because full-match volleyball totals do not use the same additive logic;
- anomaly if the absolute delta `abs(Total - (IndTotal1 + IndTotal2))` is greater than the dynamic threshold based on `Total`: `<=5: 1.0`, `<=10: 1.5`, `<=20: 2.0`, `<=35: 2.0`, `<=60: 3.0`, `<=80: 4.0`, `<=120: 6.0`, `>120: 8.0`;
- for this rule, the critical threshold is increased by `0.5`;
- for `Rugby`, the critical threshold is increased by another `1.0`.

### Poisson Total Consistency

Internal name:

```text
poisson_total_consistency
```

Purpose:

Checks whether the total is consistent with individual totals after converting normalized over probabilities into Poisson lambda values:

```text
lambda_total ~= lambda_ind_total_1 + lambda_ind_total_2
```

Scope:

- enabled only for `Football`, `Basketball`, `Hockey`, `Handball`, `WaterPolo`, and `FootHall`;
- every available `Period` is checked separately when the full market set exists;
- only half-point parameters (`.5`), because integer and quarter Asian totals need separate push/half-push handling;
- all compared lines must come from the same source/bookmaker.

Line selection:

- build same-parameter pairs for `Total_B / Total_M`, `IndTotal_1_B / IndTotal_1_M`, and `IndTotal_2_B / IndTotal_2_M` inside each `MainGameId + GameType + Period + source` group;
- normalize over probability for each pair:

```text
p_over = (1 / coef_B) / ((1 / coef_B) + (1 / coef_M))
```

- keep only central pairs where normalized `p_over` is between `0.35` and `0.65`;
- solve for `lambda` so that:

```text
P(Poisson(lambda) > Param) = p_over
```

- if multiple same-source pairs exist, use the pair whose normalized `p_over` is closest to `0.5`.

Anomaly:

- `abs(lambda_total - (lambda_ind_total_1 + lambda_ind_total_2)) > 1.0`;
- rows up to `1.1` are stored as `SOFT`;
- rows above `1.1` stay hard `DIFF`.

Excluded for now:

- `Tennis`, `TableTennis`, `Volleyball`, `Rugby`, and other sports. Tests showed that their scoring structure does not fit this simple Poisson total model reliably.

### Bounded Score Total Consistency

Internal name:

```text
bounded_score_total_consistency
```

Purpose:

Checks total consistency for volleyball periods where the score has a fixed period structure and simple Poisson by points is too rough:

```text
market P(Total_B) ~= model P(total score > Total_B Param)
```

Scope:

- enabled only for `Volleyball`;
- `Volleyball`: periods `1`, `2`, `3`, `4`, `5`;
- `Volleyball` period `0` is intentionally excluded;
- `Tennis` is disabled for this rule. The current bounded-score model is not reliable enough for tennis sets and needs separate research;
- only half-point parameters (`.5`);
- all compared lines must come from the same source/bookmaker;
- only `Total_B` creates a signal; `Total_M` is used only to normalize the B/M probability pair.

Model:

- build same-parameter B/M pairs for `Total`, `IndTotal1`, and `IndTotal2`;
- normalize over probability:

```text
p_over = (1 / coef_B) / ((1 / coef_B) + (1 / coef_M))
```

- build a bounded score grid:
  - volleyball regular set scores to `25` with two-point advantage;
  - volleyball fifth-set scores to `15` with two-point advantage;
- fit the score-grid distribution to available individual totals;
- compare model `P(score1 + score2 > TotalParam)` with market normalized `P(Total_B)`.

Anomaly:

- `Volleyball`: absolute probability delta greater than `18.5 p.p.`;

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

### Individual Total Favorite Consistency

Internal name:

```text
individual_total_favorite_consistency
```

Purpose:

Checks whether the favorite side by match outcome is also stronger in individual total markets.

Logic:

- for each `GameID`, read match outcomes `p1` and `p2`;
- match favorite exists only if its coefficient is below `1.8`;
- compare `IndTotal_1_B` and `IndTotal_2_B`;
- if both sides have the same `Param`, the favorite side should have a lower coefficient than the outsider side;
- if the same `Param` is absent, compare the central individual total lines closest to 50% implied probability;
- small probability deltas and very low coefficients are stored as `SOFT`.
- strong match favorites are not softened: if the implied probability delta between the match favorite and outsider is at least `15 p.p.`, same-param and central-param individual-total violations stay hard `DIFF` even when the individual-total delta would otherwise be soft.

Rows where both compared individual-total sources are `XMathRobotLine` are intentionally excluded from this general check and emitted by the dedicated MathRobot check below.

### MathRobot Individual Total Favorite Consistency

Internal name:

```text
mathrobot_individual_total_favorite_consistency
```

Purpose:

Separates the same individual-total favorite consistency pattern when both compared individual-total lines are from `XMathRobotLine`.

Reason:

The June 6-8 history showed this as a clean recurring pattern: most `Individual Total Favorite Consistency` signals came from `XMathRobotLine`, almost all on `Basketball/Main`, with the same parameter but a worse coefficient for the match favorite.

This check uses the same payload shape and UI rendering as `Individual Total Favorite Consistency`; only the source filter differs.

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

Soft near-threshold cases:

- period-point and combination delta checks are stored as `SOFT` when the absolute delta is above the normal limit but not above `limit + 0.125`.

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

### Tenis. Special

Internal name:

```text
tenis_special
```

Purpose:

Checks tennis-specific special markets.

First implemented rule: first-serve percentage vs first-serve percentage handicap.

Market ids:

| GroupId | Meaning |
|---:|---|
| `1119` | Player 1 first-serve percentage |
| `1121` | Player 2 first-serve percentage |
| `2257` | Player 1 first-serve percentage handicap |
| `2258` | Player 2 first-serve percentage handicap |

Line selection:

- only `SportName = Tennis`;
- rows are grouped by `MainGameId`, `Period`, and source;
- for each market side, the central line is selected by coefficient closest to 50% implied probability;
- comparison uses `Param`, not coefficient.

Anomaly:

- if player 1 has a higher central first-serve percentage parameter, player 1 handicap must be lower than player 2 handicap;
- if player 2 has a higher central first-serve percentage parameter, player 2 handicap must be lower than player 1 handicap;
- equal handicap parameters are a conflict when first-serve percentage parameters differ;
- handicap signs are read directly from stored `Param`.

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
