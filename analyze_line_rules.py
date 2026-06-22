import csv
import json
import math
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


FOOTBALL_STAT_TYPES = [
    "Corners",
    "Tackles",
    "ShotsOnTarget",
    "ShotByGates",
    "Save",
    "GoalFromGates",
    "PossessionPercentage",
]
FOOTBALL_INVERTED = {"Save", "GoalFromGates"}
SHOT_RELATION_TYPES = {"ShotsOnTarget", "ShotByGates", "GoalFromGates"}
TOTAL_CENTER_EVENTS = {"Total_B", "Total_M"}
BASKETBALL_PLAYER_EVENT_TYPES = {
    "points": {"total_player_B", "total_player_M"},
    "rebounds": {"Player_podbor_total_B", "Player_podbor_total_M"},
    "assists": {"Player_peredacha_total_B", "Player_peredacha_total_M"},
    "points_rebounds": {"player_points_rebounds_tb", "player_points_rebounds_tm"},
    "points_assists": {"player_points_assists_tb", "player_points_assists_tm"},
    "rebounds_assists": {"plaeyr_rebounds_assists_tb", "plaeyr_rebounds_assists_tm"},
    "points_rebounds_assists": {
        "player_points_rebounds_assists_tb",
        "player_points_rebounds_assists_tm",
        "player_points_rebounds_transfer_tb",
        "player_points_rebounds_transfer_tm",
        "player_points_rebounds_pass_tb",
        "player_points_rebounds_pass_tm",
    },
}
BASKETBALL_EVENT_STAT = {
    event_type: stat
    for stat, event_types in BASKETBALL_PLAYER_EVENT_TYPES.items()
    for event_type in event_types
}
BASKETBALL_PLAYER_POINT_EVENTS = BASKETBALL_PLAYER_EVENT_TYPES["points"]
BASKETBALL_PERIOD_EXPECTATIONS = {1: 4, 2: 4, 3: 4, 4: 4, 11: 2, 12: 2}
BASKETBALL_HANDICAP_EVENTS = {"Fora_1", "Fora_2"}
BASKETBALL_Q4_HANDICAP_PROBABILITY_DELTA_THRESHOLD = 0.25
BASKETBALL_Q4_HANDICAP_PARAM_DELTA_THRESHOLD = 4.5
BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN = 0.125
TOTAL_DEVIATION_EXTRA_THRESHOLD = 0.5
POISSON_TOTAL_SPORTS = {"Basketball", "Football", "FootHall", "Handball", "Hockey", "WaterPolo"}
POISSON_TOTAL_LAMBDA_DELTA_THRESHOLD = 1.0
POISSON_TOTAL_LAMBDA_SOFT_THRESHOLD = 1.1
POISSON_TOTAL_CENTER_PROBABILITY_MIN = 0.35
POISSON_TOTAL_CENTER_PROBABILITY_MAX = 0.65
POISSON_TOTAL_MARKETS = {
    "Total_B": ("Total", "B"),
    "Total_M": ("Total", "M"),
    "IndTotal_1_B": ("IndTotal1", "B"),
    "IndTotal_1_M": ("IndTotal1", "M"),
    "IndTotal_2_B": ("IndTotal2", "B"),
    "IndTotal_2_M": ("IndTotal2", "M"),
}
BOUNDED_SCORE_SPORT_PERIODS = {
    "Volleyball": {1, 2, 3, 4, 5},
}
BOUNDED_SCORE_PROBABILITY_THRESHOLDS = {
    "Volleyball": 0.185,
}
BOUNDED_SCORE_TOTAL_MARKETS = POISSON_TOTAL_MARKETS
BOUNDED_SCORE_MAX_CONSTRAINTS_PER_SIDE = 12
TENNIS_FIRST_SERVE_PERCENT_GROUPS = {1119: "p1", 1121: "p2"}
TENNIS_FIRST_SERVE_HANDICAP_GROUPS = {2257: "p1", 2258: "p2"}
PERIOD_CONFLICT_ESPORTS_SUBSPORTS = {"Valorant", "CoD", "Dota2", "CS2"}
PERIOD_CONFLICT_ESPORTS_MATCH_PROBABILITY_DELTA = 0.14
PERIOD_CONFLICT_ESPORTS_PERIOD_PROBABILITY_DELTA = 0.15
PERIOD_DEVIATION_SPORT_PERIODS = {
    "AustralianFootball": (1, 2, 3, 4),
    "Basketball": (1, 2, 3, 4),
    "Floorball": (1, 2, 3),
    "FootHall": (1, 2),
    "Football": (1, 2),
    "Handball": (1, 2),
    "Hockey": (1, 2, 3),
    "Rugby": (1, 2),
    "WaterPolo": (1, 2, 3, 4),
}
PERIOD_DEVIATION_HALF_PERIODS = (11, 12)
EXCLUDE_TEXT_CONDITIONS = {
    "Opp1": [
        "команды",
        "класк",
        "Yellow",
        "Хозяева",
        "Гости",
    ],
    "Champ": [
        "FIFA",
        "Belarus Sky League",
        "IPBL",
        "Short Football",
        "Regional League",
        "Альтернативные",
    ],
}
EXCLUDE_CONTORAS = {"XBetLineRegions", "XbetLineConstructor"}


def load_games(snapshot_zip):
    with zipfile.ZipFile(snapshot_zip) as archive:
        json_name = next((name for name in archive.namelist() if name.lower().endswith(".json")), None)
        if json_name is None:
            raise RuntimeError(f"Snapshot ZIP has no .json file: {snapshot_zip}")
        with archive.open(json_name) as f:
            return json.load(f)


def games_to_events(games):
    rows = []
    for game in games:
        base = {
            "GameId": game.get("GameId"),
            "MainGameId": game.get("MainGameId"),
            "GameType": game.get("GameType"),
            "GameVid": game.get("GameVid"),
            "SubSport": game.get("SubSport"),
            "Period": game.get("Period"),
            "SportName": game.get("SportName"),
            "Champ": game.get("Champ"),
            "Opp1": game.get("Opp1"),
            "Opp2": game.get("Opp2"),
            "Start": game.get("Start"),
        }
        for event in game.get("Events") or []:
            row = dict(base)
            row.update(event)
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for column in ("Coef", "CoefOrig", "Param"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def apply_exclusions(df):
    if df.empty:
        return df

    excluded = pd.Series(False, index=df.index)
    for column, patterns in EXCLUDE_TEXT_CONDITIONS.items():
        if column not in df.columns:
            continue
        text = df[column].fillna("").astype(str)
        for pattern in patterns:
            excluded |= text.str.contains(pattern, na=False)

    if "ContoraName" in df.columns:
        excluded |= df["ContoraName"].isin(EXCLUDE_CONTORAS)

    return df.loc[~excluded].copy()


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def status_counts(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[row.get("Status", "")] += 1
    return dict(sorted(counts.items()))


def summary(rows, output):
    return {
        "rows": len(rows),
        "status_counts": status_counts(rows),
        "output": str(Path(output).resolve()),
    }


def game_info_map(df):
    if df.empty:
        return {}
    cols = [
        column for column in ["MainGameId", "SportName", "SubSport", "GameVid", "Champ", "Opp1", "Opp2", "Start"]
        if column in df.columns
    ]
    return df.drop_duplicates("MainGameId")[cols].set_index("MainGameId").to_dict("index")


def period_deviation_threshold(main_param):
    if pd.isna(main_param):
        return None
    if main_param <= 5:
        return 1.0
    if main_param <= 10:
        return 1.5
    if main_param <= 20:
        return 2.0
    if main_param <= 35:
        return 2.0
    if main_param <= 60:
        return 3.0
    if main_param <= 80:
        return 4.0
    if main_param <= 120:
        return 6.0
    return 8.0


def period_deviation_soft_margin(sport, game_type, event_type):
    if (
        sport == "AustralianFootball" and
        game_type == "Main" and
        str(event_type or "").startswith("IndTotal_")
    ):
        return 1.0
    if sport == "Football" and game_type in {"Corners", "ShotsOnTarget"}:
        if str(event_type or "").startswith("IndTotal_"):
            return 0.25
    if sport == "Football" and game_type == "ShotByGates":
        if event_type in {"Total_B", "Total_M"}:
            return 0.5
    return 0.0


def near_delta_status(abs_delta, threshold, soft_margin):
    if soft_margin and abs_delta <= threshold + soft_margin:
        return "SOFT"
    return "DIFF"


def probability(coef):
    if pd.isna(coef) or coef <= 0:
        return None
    return 1 / coef


def rounded_probability(coef):
    value = probability(coef)
    return round(value, 6) if value is not None else None


def rounded_number(value, digits=4):
    if pd.isna(value):
        return None
    return round(value, digits)


def rounded_abs_diff(left, right, digits=4):
    if pd.isna(left) or pd.isna(right):
        return None
    return round(abs(right - left), digits)


def source_label(row):
    name = row.get("ContoraName")
    contora = row.get("Contora")
    if pd.notna(name) and name not in (None, ""):
        if pd.notna(contora) and contora not in (None, ""):
            return f"{name} ({contora})"
        return str(name)
    if pd.notna(contora) and contora not in (None, ""):
        return str(contora)
    return None


def first_source_row(group, event_type):
    rows = group[group["EventType"] == event_type].copy()
    if rows.empty:
        return None
    return rows.sort_values(
        ["Coef", "GameId", "ContoraName", "Contora"],
        na_position="last",
        kind="mergesort",
    ).iloc[0]


def joined_sources(values):
    sources = sorted({str(value) for value in values if pd.notna(value) and str(value).strip()})
    return "; ".join(sources)


def analyze_period_deviations_average(df):
    if df.empty:
        return []
    filtered = df[
        (df["SportName"].isin(PERIOD_DEVIATION_SPORT_PERIODS)) &
        (df["Coef"].between(1.65, 2.3)) &
        (df["EventType"].isin([
            "Total_B", "Total_M",
            "IndTotal_1_B", "IndTotal_1_M",
            "IndTotal_2_B", "IndTotal_2_M",
        ]))
    ].copy()
    if filtered.empty:
        return []
    filtered["SourceLabel"] = filtered.apply(source_label, axis=1)

    mean_param = filtered.groupby(
        ["GameId", "MainGameId", "GameType", "Period", "EventType"], dropna=False
    ).agg(
        Param=("Param", "mean"),
        Coef=("Coef", "mean"),
        Sources=("SourceLabel", joined_sources),
    ).reset_index()

    param_pivot = mean_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="Param",
        aggfunc="mean",
    )
    param_pivot.columns = [f"{event}_{period}_param" for event, period in param_pivot.columns]
    param_pivot = param_pivot.reset_index()

    gameid_pivot = mean_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="GameId",
        aggfunc="first",
    )
    gameid_pivot.columns = [f"{event}_{period}_GameId" for event, period in gameid_pivot.columns]
    gameid_pivot = gameid_pivot.reset_index()
    pivot = param_pivot.merge(gameid_pivot, on=["MainGameId", "GameType"], how="left")
    coef_pivot = mean_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="Coef",
        aggfunc="mean",
    )
    coef_pivot.columns = [f"{event}_{period}_Coef" for event, period in coef_pivot.columns]
    coef_pivot = coef_pivot.reset_index()
    source_pivot = mean_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="Sources",
        aggfunc="first",
    )
    source_pivot.columns = [f"{event}_{period}_Sources" for event, period in source_pivot.columns]
    source_pivot = source_pivot.reset_index()
    pivot = pivot.merge(coef_pivot, on=["MainGameId", "GameType"], how="left")
    pivot = pivot.merge(source_pivot, on=["MainGameId", "GameType"], how="left")
    info = game_info_map(df)

    rows = []
    for event_type in ["Total_B", "Total_M", "IndTotal_1_B", "IndTotal_1_M", "IndTotal_2_B", "IndTotal_2_M"]:
        p0_col = f"{event_type}_0_param"
        p0_gid = f"{event_type}_0_GameId"
        if p0_col not in pivot.columns or p0_gid not in pivot.columns:
            continue
        for _, item in pivot.iterrows():
            gi = info.get(item["MainGameId"], {})
            sport = gi.get("SportName")
            required_periods = PERIOD_DEVIATION_SPORT_PERIODS.get(sport)
            period_groups = []
            if required_periods:
                period_groups.append(("periods", required_periods))

            half_cols = [f"{event_type}_{period}_param" for period in PERIOD_DEVIATION_HALF_PERIODS]
            half_gids = [f"{event_type}_{period}_GameId" for period in PERIOD_DEVIATION_HALF_PERIODS]
            if all(column in pivot.columns for column in half_cols + half_gids):
                half_values = [item[column] for column in half_cols]
                if all(pd.notna(value) for value in half_values):
                    period_groups.append(("halves", PERIOD_DEVIATION_HALF_PERIODS))

            for comparison_type, periods in period_groups:
                period_cols = [f"{event_type}_{period}_param" for period in periods]
                period_gids = [f"{event_type}_{period}_GameId" for period in periods]
                if not all(column in pivot.columns for column in period_cols + period_gids):
                    continue
                values = [item[p0_col], *[item[column] for column in period_cols]]
                if any(pd.isna(value) for value in values):
                    continue
                delta = item[p0_col] - sum(item[column] for column in period_cols)
                threshold = period_deviation_threshold(item[p0_col])
                abs_delta = abs(delta)
                if threshold is None or abs_delta <= threshold:
                    continue
                soft_margin = period_deviation_soft_margin(sport, item["GameType"], event_type)
                row = {
                    "Status": near_delta_status(abs_delta, threshold, soft_margin),
                    "MainGameId": item["MainGameId"],
                    "GameType": item["GameType"],
                    "Sport": gi.get("SportName"),
                    "Champ": gi.get("Champ"),
                    "Opp1": gi.get("Opp1"),
                    "Opp2": gi.get("Opp2"),
                    "Start": gi.get("Start"),
                    "EventType": event_type,
                    "ComparisonType": comparison_type,
                    "Periods": "+".join(str(period) for period in periods),
                    "P0": round(item[p0_col], 4),
                    "P0Coef": rounded_number(item.get(f"{event_type}_0_Coef")),
                    "P0Probability": rounded_probability(item.get(f"{event_type}_0_Coef")),
                    "P0Sources": item.get(f"{event_type}_0_Sources"),
                    "Delta": round(delta, 4),
                    "CriticalDelta": threshold,
                    "SoftDeltaMargin": soft_margin,
                    "GID0": item[p0_gid],
                }
                if row["Status"] == "SOFT":
                    row["SoftReason"] = f"abs(delta) <= critical delta + {soft_margin}"
                for period, col, gid_col in zip(periods, period_cols, period_gids):
                    row[f"P{period}"] = round(item[col], 4)
                    row[f"P{period}Coef"] = rounded_number(item.get(f"{event_type}_{period}_Coef"))
                    row[f"P{period}Probability"] = rounded_probability(item.get(f"{event_type}_{period}_Coef"))
                    row[f"P{period}Sources"] = item.get(f"{event_type}_{period}_Sources")
                    row[f"GID{period}"] = item[gid_col]
                rows.append(row)
    return sorted(rows, key=lambda row: abs(float(row["Delta"])), reverse=True)


def analyze_total_deviations_average(df):
    if df.empty:
        return []
    center_coef = 1.95
    center_coef_min = 1.5
    low_adjust_max = 1.65
    high_adjust_min = 2.3
    center_coef_max = 2.6
    tennis_ace_total_adjust_min = 2.4
    tennis_ace_total_adjust_max = 2.7
    event_types = [
        "Total_B", "Total_M",
        "IndTotal_1_B", "IndTotal_1_M",
        "IndTotal_2_B", "IndTotal_2_M",
    ]
    individual_event_types = {
        "IndTotal_1_B", "IndTotal_1_M",
        "IndTotal_2_B", "IndTotal_2_M",
    }
    total_event_types = {"Total_B", "Total_M"}
    filtered = df[
        ~((df["SportName"] == "Volleyball") & (df["Period"] == 0)) &
        (df["EventType"].isin(event_types)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if filtered.empty:
        return []
    filtered["CoefDistance"] = (filtered["Coef"] - center_coef).abs()
    closest_param = filtered.sort_values(
        ["MainGameId", "GameType", "Period", "EventType", "CoefDistance", "Coef"]
    ).drop_duplicates(
        ["MainGameId", "GameType", "Period", "EventType"],
        keep="first",
    )
    tennis_ace_total_adjustment_mask = (
        (closest_param["SportName"] == "Tennis") &
        (closest_param["GameType"] == "Ace") &
        (closest_param["EventType"].isin(total_event_types)) &
        (closest_param["Coef"].between(tennis_ace_total_adjust_min, tennis_ace_total_adjust_max))
    )
    closest_param = closest_param[
        closest_param["Coef"].between(center_coef_min, center_coef_max) |
        tennis_ace_total_adjustment_mask
    ].copy()
    if closest_param.empty:
        return []
    closest_param["ParamAdjustment"] = 0.0
    individual_mask = (
        closest_param["EventType"].isin(individual_event_types) &
        (closest_param["Coef"].notna())
    )
    low_adjustment_mask = (
        individual_mask &
        (closest_param["Coef"] < low_adjust_max)
    )
    high_adjustment_mask = (
        individual_mask &
        (closest_param["Coef"] > high_adjust_min)
    )
    closest_param.loc[
        low_adjustment_mask & closest_param["EventType"].str.endswith("_B"),
        "ParamAdjustment",
    ] = 0.5
    closest_param.loc[
        low_adjustment_mask & closest_param["EventType"].str.endswith("_M"),
        "ParamAdjustment",
    ] = -0.5
    closest_param.loc[
        high_adjustment_mask & closest_param["EventType"].str.endswith("_B"),
        "ParamAdjustment",
    ] = -0.5
    closest_param.loc[
        high_adjustment_mask & closest_param["EventType"].str.endswith("_M"),
        "ParamAdjustment",
    ] = 0.5
    tennis_ace_total_adjustment_mask = (
        (closest_param["SportName"] == "Tennis") &
        (closest_param["GameType"] == "Ace") &
        (closest_param["EventType"].isin(total_event_types)) &
        (closest_param["Coef"].between(tennis_ace_total_adjust_min, tennis_ace_total_adjust_max))
    )
    closest_param.loc[
        tennis_ace_total_adjustment_mask & (closest_param["EventType"] == "Total_B"),
        "ParamAdjustment",
    ] = -1.0
    closest_param.loc[
        tennis_ace_total_adjustment_mask & (closest_param["EventType"] == "Total_M"),
        "ParamAdjustment",
    ] = 1.0
    closest_param["AdjustedParam"] = closest_param["Param"] + closest_param["ParamAdjustment"]
    pivot = closest_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="AdjustedParam",
        aggfunc="first",
    )
    pivot.columns = [f"{event}_{period}_param" for event, period in pivot.columns]
    pivot = pivot.reset_index()
    detail_by_key = {
        (row["MainGameId"], row["GameType"], row["Period"], row["EventType"]): row
        for _, row in closest_param.iterrows()
    }
    info = game_info_map(df)
    rows = []
    for side in ("B", "M"):
        for period in (0, 1, 2):
            total_col = f"Total_{side}_{period}_param"
            ind1_col = f"IndTotal_1_{side}_{period}_param"
            ind2_col = f"IndTotal_2_{side}_{period}_param"
            if not all(column in pivot.columns for column in (total_col, ind1_col, ind2_col)):
                continue
            valid = pivot[[total_col, ind1_col, ind2_col]].notna().all(axis=1)
            for _, item in pivot.loc[valid].iterrows():
                expected = item[ind1_col] + item[ind2_col]
                delta = item[total_col] - expected
                abs_delta = abs(delta)
                gi = info.get(item["MainGameId"], {})
                threshold = period_deviation_threshold(item[total_col])
                if threshold is not None:
                    threshold += TOTAL_DEVIATION_EXTRA_THRESHOLD
                if threshold is not None and gi.get("SportName") == "Rugby":
                    threshold += 1.0
                if threshold is None or abs_delta <= threshold:
                    continue
                total_line = detail_by_key.get((item["MainGameId"], item["GameType"], period, f"Total_{side}"))
                ind1_line = detail_by_key.get((item["MainGameId"], item["GameType"], period, f"IndTotal_1_{side}"))
                ind2_line = detail_by_key.get((item["MainGameId"], item["GameType"], period, f"IndTotal_2_{side}"))
                rows.append({
                    "Status": "DIFF",
                    "MainGameId": item["MainGameId"],
                    "GameType": item["GameType"],
                    "Sport": gi.get("SportName"),
                    "Champ": gi.get("Champ"),
                    "Opp1": gi.get("Opp1"),
                    "Opp2": gi.get("Opp2"),
                    "Start": gi.get("Start"),
                    "Period": period,
                    "Type": side,
                    "EventType": f"Total_{side}",
                    "EventTypes": f"Total_{side} / IndTotal_1_{side} / IndTotal_2_{side}",
                    "GameId": total_line.get("GameId") if total_line is not None else None,
                    "TotalGameId": total_line.get("GameId") if total_line is not None else None,
                    "Total": rounded_number(total_line.get("Param") if total_line is not None else None),
                    "TotalAdjusted": round(item[total_col], 4),
                    "TotalOriginal": rounded_number(total_line.get("Param") if total_line is not None else None),
                    "TotalAdjustment": rounded_number(total_line.get("ParamAdjustment") if total_line is not None else None),
                    "TotalCoef": rounded_number(total_line.get("Coef") if total_line is not None else None),
                    "TotalProbability": rounded_probability(total_line.get("Coef") if total_line is not None else None),
                    "TotalSource": source_label(total_line) if total_line is not None else None,
                    "IndTotal1": rounded_number(ind1_line.get("Param") if ind1_line is not None else None),
                    "IndTotal1Adjusted": round(item[ind1_col], 4),
                    "IndTotal1GameId": ind1_line.get("GameId") if ind1_line is not None else None,
                    "IndTotal1Coef": rounded_number(ind1_line.get("Coef") if ind1_line is not None else None),
                    "IndTotal1Probability": rounded_probability(ind1_line.get("Coef") if ind1_line is not None else None),
                    "IndTotal1Source": source_label(ind1_line) if ind1_line is not None else None,
                    "IndTotal1Original": rounded_number(ind1_line.get("Param") if ind1_line is not None else None),
                    "IndTotal1Adjustment": rounded_number(ind1_line.get("ParamAdjustment") if ind1_line is not None else None),
                    "IndTotal2": rounded_number(ind2_line.get("Param") if ind2_line is not None else None),
                    "IndTotal2Adjusted": round(item[ind2_col], 4),
                    "IndTotal2GameId": ind2_line.get("GameId") if ind2_line is not None else None,
                    "IndTotal2Coef": rounded_number(ind2_line.get("Coef") if ind2_line is not None else None),
                    "IndTotal2Probability": rounded_probability(ind2_line.get("Coef") if ind2_line is not None else None),
                    "IndTotal2Source": source_label(ind2_line) if ind2_line is not None else None,
                    "IndTotal2Original": rounded_number(ind2_line.get("Param") if ind2_line is not None else None),
                    "IndTotal2Adjustment": rounded_number(ind2_line.get("ParamAdjustment") if ind2_line is not None else None),
                    "Expected": round(expected, 4),
                    "Delta": round(delta, 4),
                    "AbsDelta": round(abs_delta, 4),
                    "CriticalDelta": threshold,
                })
    return sorted(rows, key=lambda row: abs(float(row["Delta"])), reverse=True)


def is_half_point_param(value):
    if pd.isna(value):
        return False
    doubled = round(float(value) * 2)
    return abs(float(value) * 2 - doubled) < 1e-9 and doubled % 2 == 1


def poisson_cdf(k, lam):
    if lam < 0:
        return None
    if k < 0:
        return 0.0
    term = math.exp(-lam)
    total = term
    for i in range(1, int(k) + 1):
        term *= lam / i
        total += term
    return min(max(total, 0.0), 1.0)


def poisson_over_probability(param, lam):
    cdf = poisson_cdf(math.floor(float(param)), lam)
    if cdf is None:
        return None
    return min(max(1.0 - cdf, 0.0), 1.0)


def lambda_from_over_probability(param, probability):
    if not (0 < probability < 1):
        return None
    low = 0.0
    high = max(1.0, float(param) + 10.0)
    while poisson_over_probability(param, high) < probability:
        high *= 2.0
        if high > 10000:
            return None
    for _ in range(70):
        mid = (low + high) / 2.0
        if poisson_over_probability(param, mid) < probability:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def normalized_over_probability(over_coef, under_coef):
    if pd.isna(over_coef) or pd.isna(under_coef) or over_coef <= 1 or under_coef <= 1:
        return None
    over_raw = 1.0 / float(over_coef)
    under_raw = 1.0 / float(under_coef)
    total = over_raw + under_raw
    if total <= 0:
        return None
    return over_raw / total


def analyze_poisson_total_consistency(df):
    if df.empty:
        return []
    required = {"MainGameId", "GameId", "GameType", "Period", "SportName", "EventType", "Param", "Coef"}
    if not required.issubset(df.columns):
        return []

    filtered = df[
        (df["SportName"].isin(POISSON_TOTAL_SPORTS)) &
        (df["EventType"].isin(POISSON_TOTAL_MARKETS)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if filtered.empty:
        return []

    filtered = filtered[filtered["Param"].apply(is_half_point_param)].copy()
    if filtered.empty:
        return []
    filtered["BaseMarket"] = filtered["EventType"].map(lambda event_type: POISSON_TOTAL_MARKETS[event_type][0])
    filtered["Side"] = filtered["EventType"].map(lambda event_type: POISSON_TOTAL_MARKETS[event_type][1])
    if "Contora" in filtered.columns:
        filtered["SourceKey"] = filtered["Contora"]
    else:
        filtered["SourceKey"] = None
    if "ContoraName" in filtered.columns:
        filtered["SourceKey"] = filtered["SourceKey"].where(filtered["SourceKey"].notna(), filtered["ContoraName"])
    filtered = filtered[filtered["SourceKey"].notna()].copy()
    if filtered.empty:
        return []

    pair_rows = []
    group_columns = ["MainGameId", "GameType", "Period", "SourceKey", "BaseMarket", "Param"]
    for _, group in filtered.groupby(group_columns, dropna=False):
        over_rows = group[group["Side"] == "B"].sort_values(["Coef", "GameId"], kind="mergesort")
        under_rows = group[group["Side"] == "M"].sort_values(["Coef", "GameId"], kind="mergesort")
        if over_rows.empty or under_rows.empty:
            continue
        over = over_rows.iloc[0]
        under = under_rows.iloc[0]
        probability = normalized_over_probability(over.get("Coef"), under.get("Coef"))
        if probability is None:
            continue
        if not (
            POISSON_TOTAL_CENTER_PROBABILITY_MIN <= probability <= POISSON_TOTAL_CENTER_PROBABILITY_MAX
        ):
            continue
        lam = lambda_from_over_probability(over.get("Param"), probability)
        if lam is None:
            continue
        pair_rows.append({
            "MainGameId": over.get("MainGameId"),
            "GameType": over.get("GameType"),
            "Period": over.get("Period"),
            "SourceKey": over.get("SourceKey"),
            "BaseMarket": over.get("BaseMarket"),
            "Sport": over.get("SportName"),
            "Champ": over.get("Champ"),
            "Opp1": over.get("Opp1"),
            "Opp2": over.get("Opp2"),
            "Start": over.get("Start"),
            "Param": float(over.get("Param")),
            "CoefB": float(over.get("Coef")),
            "CoefM": float(under.get("Coef")),
            "ProbabilityOver": probability,
            "ProbabilityUnder": 1.0 - probability,
            "Lambda": lam,
            "Source": source_label(over),
            "GameIdB": over.get("GameId"),
            "GameIdM": under.get("GameId"),
        })

    if not pair_rows:
        return []

    pairs = pd.DataFrame(pair_rows)
    pairs["CenterDistance"] = (pairs["ProbabilityOver"] - 0.5).abs()
    centers = pairs.sort_values(
        ["MainGameId", "GameType", "Period", "SourceKey", "BaseMarket", "CenterDistance", "CoefB", "Param"],
        kind="mergesort",
    ).drop_duplicates(
        ["MainGameId", "GameType", "Period", "SourceKey", "BaseMarket"],
        keep="first",
    )
    pivot = centers.pivot_table(
        index=["MainGameId", "GameType", "Period", "SourceKey"],
        columns="BaseMarket",
        values=["Param", "CoefB", "CoefM", "ProbabilityOver", "ProbabilityUnder", "Lambda", "GameIdB", "GameIdM"],
        aggfunc="first",
    )
    pivot.columns = [f"{market}_{field}" for field, market in pivot.columns]
    pivot = pivot.reset_index()
    required_columns = ["Total_Lambda", "IndTotal1_Lambda", "IndTotal2_Lambda"]
    pivot = pivot.dropna(subset=required_columns).copy()
    if pivot.empty:
        return []

    info = centers.drop_duplicates(["MainGameId", "GameType", "Period", "SourceKey"])[[
        "MainGameId", "GameType", "Period", "SourceKey", "Sport", "Champ", "Opp1", "Opp2", "Start", "Source",
    ]]
    pivot = pivot.merge(info, on=["MainGameId", "GameType", "Period", "SourceKey"], how="left")
    rows = []
    for _, item in pivot.iterrows():
        expected_lambda = item["IndTotal1_Lambda"] + item["IndTotal2_Lambda"]
        delta = item["Total_Lambda"] - expected_lambda
        abs_delta = abs(delta)
        if abs_delta <= POISSON_TOTAL_LAMBDA_DELTA_THRESHOLD:
            continue
        status = "SOFT" if abs_delta <= POISSON_TOTAL_LAMBDA_SOFT_THRESHOLD else "DIFF"
        rows.append({
            "Status": status,
            "MainGameId": item["MainGameId"],
            "GameId": item.get("Total_GameIdB"),
            "GameType": item["GameType"],
            "Sport": item.get("Sport"),
            "Champ": item.get("Champ"),
            "Opp1": item.get("Opp1"),
            "Opp2": item.get("Opp2"),
            "Start": item.get("Start"),
            "Period": item["Period"],
            "Type": "B",
            "EventType": "Total_B",
            "EventTypes": "Total_B / Total_M / IndTotal_1_B / IndTotal_1_M / IndTotal_2_B / IndTotal_2_M",
            "SourceKey": item.get("SourceKey"),
            "Source": item.get("Source"),
            "TotalGameId": item.get("Total_GameIdB"),
            "TotalUnderGameId": item.get("Total_GameIdM"),
            "TotalParam": rounded_number(item.get("Total_Param")),
            "TotalCoefB": rounded_number(item.get("Total_CoefB")),
            "TotalCoefM": rounded_number(item.get("Total_CoefM")),
            "TotalProbabilityOver": rounded_number(item.get("Total_ProbabilityOver"), 6),
            "TotalProbabilityUnder": rounded_number(item.get("Total_ProbabilityUnder"), 6),
            "TotalLambda": rounded_number(item.get("Total_Lambda"), 4),
            "IndTotal1GameId": item.get("IndTotal1_GameIdB"),
            "IndTotal1UnderGameId": item.get("IndTotal1_GameIdM"),
            "IndTotal1Param": rounded_number(item.get("IndTotal1_Param")),
            "IndTotal1CoefB": rounded_number(item.get("IndTotal1_CoefB")),
            "IndTotal1CoefM": rounded_number(item.get("IndTotal1_CoefM")),
            "IndTotal1ProbabilityOver": rounded_number(item.get("IndTotal1_ProbabilityOver"), 6),
            "IndTotal1ProbabilityUnder": rounded_number(item.get("IndTotal1_ProbabilityUnder"), 6),
            "IndTotal1Lambda": rounded_number(item.get("IndTotal1_Lambda"), 4),
            "IndTotal2GameId": item.get("IndTotal2_GameIdB"),
            "IndTotal2UnderGameId": item.get("IndTotal2_GameIdM"),
            "IndTotal2Param": rounded_number(item.get("IndTotal2_Param")),
            "IndTotal2CoefB": rounded_number(item.get("IndTotal2_CoefB")),
            "IndTotal2CoefM": rounded_number(item.get("IndTotal2_CoefM")),
            "IndTotal2ProbabilityOver": rounded_number(item.get("IndTotal2_ProbabilityOver"), 6),
            "IndTotal2ProbabilityUnder": rounded_number(item.get("IndTotal2_ProbabilityUnder"), 6),
            "IndTotal2Lambda": rounded_number(item.get("IndTotal2_Lambda"), 4),
            "ExpectedLambda": round(expected_lambda, 4),
            "LambdaDelta": round(delta, 4),
            "AbsLambdaDelta": round(abs_delta, 4),
            "CriticalLambdaDelta": POISSON_TOTAL_LAMBDA_DELTA_THRESHOLD,
            "SoftLambdaDeltaThreshold": POISSON_TOTAL_LAMBDA_SOFT_THRESHOLD,
            "SoftReason": (
                f"abs(lambda delta) <= {POISSON_TOTAL_LAMBDA_SOFT_THRESHOLD}"
                if status == "SOFT" else None
            ),
            "ParamDelta": rounded_number(item.get("Total_Param") - item.get("IndTotal1_Param") - item.get("IndTotal2_Param"), 4),
        })
    return sorted(rows, key=lambda row: float(row["AbsLambdaDelta"]), reverse=True)


def bounded_score_grid(sport, period):
    period = int(period)
    if sport == "Volleyball":
        target = 15 if period == 5 else 25
        cap = 35 if period == 5 else 50
        scores = []
        for loser in range(0, target - 1):
            scores.append((target, loser))
            scores.append((loser, target))
        for winner in range(target + 1, cap + 1):
            scores.append((winner, winner - 2))
            scores.append((winner - 2, winner))
        return np.array(scores, dtype=float)

    return np.empty((0, 2), dtype=float)


def bounded_score_prior(sport, period, scores):
    totals = scores.sum(axis=1)
    if sport == "Volleyball" and int(period) == 5:
        center = 27.0
        sigma = 5.0
    else:
        center = 45.0
        sigma = 6.0
    prior = np.exp(-0.5 * ((totals - center) / sigma) ** 2)
    prior = np.maximum(prior, 1e-12)
    return prior / prior.sum()


def bounded_score_fit(scores, constraints, prior, iterations=350, l2=0.002):
    if len(constraints) < 2:
        return None
    features = []
    targets = []
    sides = set()
    for side, param, target_probability in constraints:
        if side not in {"IndTotal1", "IndTotal2"}:
            continue
        if target_probability is None or pd.isna(target_probability):
            continue
        target_probability = float(target_probability)
        if not (0.0 < target_probability < 1.0):
            continue
        values = scores[:, 0] if side == "IndTotal1" else scores[:, 1]
        features.append((values > float(param)).astype(float))
        targets.append(min(max(target_probability, 0.001), 0.999))
        sides.add(side)

    if len(features) < 2 or sides != {"IndTotal1", "IndTotal2"}:
        return None

    a = np.vstack(features)
    y = np.array(targets, dtype=float)
    prior_log = np.log(np.maximum(prior, 1e-300))
    theta = np.zeros(len(y), dtype=float)
    first_moment = np.zeros_like(theta)
    second_moment = np.zeros_like(theta)
    best = None
    best_loss = float("inf")

    for step in range(1, iterations + 1):
        logits = prior_log + theta @ a
        logits -= logits.max()
        weights = np.exp(logits)
        probabilities = weights / weights.sum()
        predicted = a @ probabilities
        diff = predicted - y
        loss = float(np.mean(diff ** 2) + l2 * float(theta @ theta))
        if loss < best_loss:
            best_loss = loss
            best = (probabilities.copy(), predicted.copy(), loss)
        if loss < 1e-7:
            break

        covariance = (a * probabilities) @ a.T - np.outer(predicted, predicted)
        gradient = (2.0 / len(y)) * (covariance @ diff) + 2.0 * l2 * theta
        first_moment = 0.9 * first_moment + 0.1 * gradient
        second_moment = 0.999 * second_moment + 0.001 * (gradient ** 2)
        step_size = 0.08 * (math.sqrt(1.0 - 0.999 ** step) / (1.0 - 0.9 ** step))
        theta -= step_size * first_moment / (np.sqrt(second_moment) + 1e-8)

    if best is None:
        return None

    probabilities, predicted, loss = best
    return {
        "probabilities": probabilities,
        "predicted": predicted,
        "targets": y,
        "loss": loss,
        "mae": float(np.mean(np.abs(predicted - y))),
    }


def bounded_select_constraints(ind_lines):
    selected = []
    for side in ("IndTotal1", "IndTotal2"):
        side_lines = ind_lines[ind_lines["BaseMarket"] == side].copy()
        if side_lines.empty:
            continue
        side_lines["CenterDistance"] = (side_lines["ProbabilityOver"] - 0.5).abs()
        side_lines = side_lines.sort_values(
            ["CenterDistance", "Param", "CoefB"],
            kind="mergesort",
        ).head(BOUNDED_SCORE_MAX_CONSTRAINTS_PER_SIDE)
        selected.extend(
            (row["BaseMarket"], row["Param"], row["ProbabilityOver"])
            for _, row in side_lines.iterrows()
        )
    return selected


def analyze_bounded_score_total_consistency(df):
    if df.empty:
        return []
    required = {"MainGameId", "GameId", "GameType", "Period", "SportName", "EventType", "Param", "Coef"}
    if not required.issubset(df.columns):
        return []

    filtered = df[
        (df["SportName"].isin(BOUNDED_SCORE_SPORT_PERIODS)) &
        (df["EventType"].isin(BOUNDED_SCORE_TOTAL_MARKETS)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if filtered.empty:
        return []

    filtered = filtered[filtered["Param"].apply(is_half_point_param)].copy()
    if filtered.empty:
        return []
    filtered["PeriodInt"] = pd.to_numeric(filtered["Period"], errors="coerce")
    filtered = filtered[
        filtered.apply(
            lambda row: row["PeriodInt"] in BOUNDED_SCORE_SPORT_PERIODS.get(row["SportName"], set()),
            axis=1,
        )
    ].copy()
    if filtered.empty:
        return []

    filtered["BaseMarket"] = filtered["EventType"].map(lambda event_type: BOUNDED_SCORE_TOTAL_MARKETS[event_type][0])
    filtered["Side"] = filtered["EventType"].map(lambda event_type: BOUNDED_SCORE_TOTAL_MARKETS[event_type][1])
    if "Contora" in filtered.columns:
        filtered["SourceKey"] = filtered["Contora"]
    else:
        filtered["SourceKey"] = None
    if "ContoraName" in filtered.columns:
        filtered["SourceKey"] = filtered["SourceKey"].where(filtered["SourceKey"].notna(), filtered["ContoraName"])
    filtered = filtered[filtered["SourceKey"].notna()].copy()
    if filtered.empty:
        return []

    pair_rows = []
    group_columns = ["MainGameId", "GameType", "Period", "SourceKey", "BaseMarket", "Param"]
    for _, group in filtered.groupby(group_columns, dropna=False):
        over_rows = group[group["Side"] == "B"].sort_values(["Coef", "GameId"], kind="mergesort")
        under_rows = group[group["Side"] == "M"].sort_values(["Coef", "GameId"], kind="mergesort")
        if over_rows.empty or under_rows.empty:
            continue
        over = over_rows.iloc[0]
        under = under_rows.iloc[0]
        adjusted_param = float(over.get("Param"))
        adjusted_coef_b = float(over.get("Coef"))
        param_adjustment = 0.0
        coef_b_adjustment = 0.0
        adjustment_reason = None

        probability = normalized_over_probability(adjusted_coef_b, under.get("Coef"))
        if probability is None:
            continue
        pair_rows.append({
            "MainGameId": over.get("MainGameId"),
            "GameType": over.get("GameType"),
            "Period": over.get("Period"),
            "PeriodInt": int(over.get("Period")),
            "SourceKey": over.get("SourceKey"),
            "BaseMarket": over.get("BaseMarket"),
            "Sport": over.get("SportName"),
            "Champ": over.get("Champ"),
            "Opp1": over.get("Opp1"),
            "Opp2": over.get("Opp2"),
            "Start": over.get("Start"),
            "Param": adjusted_param,
            "OriginalParam": float(over.get("Param")),
            "ParamAdjustment": param_adjustment,
            "CoefB": adjusted_coef_b,
            "OriginalCoefB": float(over.get("Coef")),
            "CoefBAdjustment": coef_b_adjustment,
            "CoefM": float(under.get("Coef")),
            "AdjustmentReason": adjustment_reason,
            "ProbabilityOver": float(probability),
            "ProbabilityUnder": float(1.0 - probability),
            "Source": source_label(over),
            "GameIdB": over.get("GameId"),
            "GameIdM": under.get("GameId"),
        })

    if not pair_rows:
        return []

    pairs = pd.DataFrame(pair_rows)
    pairs["CenterDistance"] = (pairs["ProbabilityOver"] - 0.5).abs()
    rows = []
    for _, group in pairs.groupby(["MainGameId", "GameType", "Period", "SourceKey"], dropna=False):
        total_lines = group[group["BaseMarket"] == "Total"].copy()
        ind_lines = group[group["BaseMarket"].isin(["IndTotal1", "IndTotal2"])].copy()
        if total_lines.empty or ind_lines.empty:
            continue
        if {"IndTotal1", "IndTotal2"} - set(ind_lines["BaseMarket"].dropna()):
            continue

        total = total_lines.sort_values(
            ["CenterDistance", "CoefB", "Param"],
            kind="mergesort",
        ).iloc[0]
        sport = total.get("Sport")
        period = int(total.get("PeriodInt"))
        threshold = BOUNDED_SCORE_PROBABILITY_THRESHOLDS.get(sport)
        scores = bounded_score_grid(sport, period)
        if threshold is None or scores.size == 0:
            continue

        constraints = bounded_select_constraints(ind_lines)
        prior = bounded_score_prior(sport, period, scores)
        fit = bounded_score_fit(scores, constraints, prior)
        if fit is None:
            continue

        probabilities = fit["probabilities"]
        model_total_probability = float(probabilities[(scores[:, 0] + scores[:, 1]) > float(total["Param"])].sum())
        market_total_probability = float(total["ProbabilityOver"])
        delta = market_total_probability - model_total_probability
        abs_delta = abs(delta)
        if abs_delta <= threshold:
            continue

        ind1_center = ind_lines[ind_lines["BaseMarket"] == "IndTotal1"].sort_values(
            ["CenterDistance", "CoefB", "Param"],
            kind="mergesort",
        ).iloc[0]
        ind2_center = ind_lines[ind_lines["BaseMarket"] == "IndTotal2"].sort_values(
            ["CenterDistance", "CoefB", "Param"],
            kind="mergesort",
        ).iloc[0]

        rows.append({
            "Status": "DIFF",
            "MainGameId": total.get("MainGameId"),
            "GameId": total.get("GameIdB"),
            "GameType": total.get("GameType"),
            "Sport": sport,
            "Champ": total.get("Champ"),
            "Opp1": total.get("Opp1"),
            "Opp2": total.get("Opp2"),
            "Start": total.get("Start"),
            "Period": total.get("Period"),
            "Type": "B",
            "EventType": "Total_B",
            "EventTypes": "Total_B / Total_M / IndTotal_1_B / IndTotal_1_M / IndTotal_2_B / IndTotal_2_M",
            "SourceKey": total.get("SourceKey"),
            "Source": total.get("Source"),
            "TotalGameId": total.get("GameIdB"),
            "TotalUnderGameId": total.get("GameIdM"),
            "TotalParam": rounded_number(total.get("Param")),
            "TotalOriginalParam": rounded_number(total.get("OriginalParam")),
            "TotalParamAdjustment": rounded_number(total.get("ParamAdjustment")),
            "TotalCoefB": rounded_number(total.get("CoefB")),
            "TotalOriginalCoefB": rounded_number(total.get("OriginalCoefB")),
            "TotalCoefBAdjustment": rounded_number(total.get("CoefBAdjustment")),
            "TotalCoefM": rounded_number(total.get("CoefM")),
            "TotalAdjustmentReason": total.get("AdjustmentReason"),
            "TotalProbabilityOver": rounded_number(market_total_probability, 6),
            "TotalProbabilityUnder": rounded_number(total.get("ProbabilityUnder"), 6),
            "ModelTotalProbabilityOver": rounded_number(model_total_probability, 6),
            "ProbabilityDelta": round(delta, 6),
            "AbsProbabilityDelta": round(abs_delta, 6),
            "ProbabilityDeltaPp": round(delta * 100.0, 2),
            "AbsProbabilityDeltaPp": round(abs_delta * 100.0, 2),
            "CriticalProbabilityDelta": threshold,
            "CriticalProbabilityDeltaPp": round(threshold * 100.0, 2),
            "ExpectedScore1": round(float((scores[:, 0] * probabilities).sum()), 4),
            "ExpectedScore2": round(float((scores[:, 1] * probabilities).sum()), 4),
            "ExpectedTotal": round(float(((scores[:, 0] + scores[:, 1]) * probabilities).sum()), 4),
            "FitMAE": round(float(fit["mae"]), 6),
            "FitLoss": round(float(fit["loss"]), 8),
            "ConstraintCount": len(constraints),
            "IndTotal1LineCount": int((ind_lines["BaseMarket"] == "IndTotal1").sum()),
            "IndTotal2LineCount": int((ind_lines["BaseMarket"] == "IndTotal2").sum()),
            "IndTotal1GameId": ind1_center.get("GameIdB"),
            "IndTotal1UnderGameId": ind1_center.get("GameIdM"),
            "IndTotal1Param": rounded_number(ind1_center.get("Param")),
            "IndTotal1OriginalParam": rounded_number(ind1_center.get("OriginalParam")),
            "IndTotal1ParamAdjustment": rounded_number(ind1_center.get("ParamAdjustment")),
            "IndTotal1CoefB": rounded_number(ind1_center.get("CoefB")),
            "IndTotal1OriginalCoefB": rounded_number(ind1_center.get("OriginalCoefB")),
            "IndTotal1CoefBAdjustment": rounded_number(ind1_center.get("CoefBAdjustment")),
            "IndTotal1CoefM": rounded_number(ind1_center.get("CoefM")),
            "IndTotal1AdjustmentReason": ind1_center.get("AdjustmentReason"),
            "IndTotal1ProbabilityOver": rounded_number(ind1_center.get("ProbabilityOver"), 6),
            "IndTotal2GameId": ind2_center.get("GameIdB"),
            "IndTotal2UnderGameId": ind2_center.get("GameIdM"),
            "IndTotal2Param": rounded_number(ind2_center.get("Param")),
            "IndTotal2OriginalParam": rounded_number(ind2_center.get("OriginalParam")),
            "IndTotal2ParamAdjustment": rounded_number(ind2_center.get("ParamAdjustment")),
            "IndTotal2CoefB": rounded_number(ind2_center.get("CoefB")),
            "IndTotal2OriginalCoefB": rounded_number(ind2_center.get("OriginalCoefB")),
            "IndTotal2CoefBAdjustment": rounded_number(ind2_center.get("CoefBAdjustment")),
            "IndTotal2CoefM": rounded_number(ind2_center.get("CoefM")),
            "IndTotal2AdjustmentReason": ind2_center.get("AdjustmentReason"),
            "IndTotal2ProbabilityOver": rounded_number(ind2_center.get("ProbabilityOver"), 6),
        })

    return sorted(rows, key=lambda row: float(row["AbsProbabilityDelta"]), reverse=True)


def get_match_favorite(p1, p2, threshold=0.10, max_coef=2.2):
    if pd.notna(p1) and pd.notna(p2):
        prob_p1, prob_p2 = 1 / p1, 1 / p2
        if abs(prob_p1 - prob_p2) >= threshold:
            if prob_p1 > prob_p2 and p1 < max_coef:
                return "p1"
            if prob_p2 > prob_p1 and p2 < max_coef:
                return "p2"
    return "noone"


def get_stat_favorite(p1, p2, stat_type, threshold=0.07):
    if pd.isna(p1) or pd.isna(p2):
        return "noone"
    prob_p1, prob_p2 = 1 / p1, 1 / p2
    if abs(prob_p1 - prob_p2) < threshold:
        return "noone"
    if stat_type in FOOTBALL_INVERTED:
        return "p1" if prob_p1 < prob_p2 else "p2"
    return "p1" if prob_p1 > prob_p2 else "p2"


def get_match_favorite_by_coef_zone(p1, p2):
    if pd.isna(p1) or pd.isna(p2):
        return "noone"
    if p1 < 1.8 and p1 < p2:
        return "p1"
    if p2 < 1.8 and p2 < p1:
        return "p2"
    return "noone"


def stat_conflict_by_coef_direction(match_fav, stat_p1, stat_p2, stat_type):
    if match_fav not in {"p1", "p2"} or pd.isna(stat_p1) or pd.isna(stat_p2):
        return False
    favorite_stat_coef = stat_p1 if match_fav == "p1" else stat_p2
    opponent_stat_coef = stat_p2 if match_fav == "p1" else stat_p1
    if stat_type in FOOTBALL_INVERTED:
        return favorite_stat_coef < opponent_stat_coef
    return favorite_stat_coef > opponent_stat_coef


def add_game_info(row, info, main_game_id):
    gi = info.get(main_game_id, {})
    row.update({
        "Sport": gi.get("SportName"),
        "Champ": gi.get("Champ"),
        "Opp1": gi.get("Opp1"),
        "Opp2": gi.get("Opp2"),
        "Start": gi.get("Start"),
    })
    return row


def analyze_stat_conflicts(df):
    if df.empty:
        return []
    win_rows = df[
        (df["EventType"].isin(["p1", "p2"])) &
        (df["GameType"] == "Main") &
        (df["SportName"] == "Football") &
        (df["Period"] == 0)
    ].copy()
    wins = win_rows.pivot_table(index="MainGameId", columns="EventType", values="Coef", aggfunc="mean").reset_index()
    if wins.empty or "p1" not in wins.columns or "p2" not in wins.columns:
        return []
    win_source = {
        (row["MainGameId"], row["EventType"]): source_label(row)
        for _, row in win_rows.sort_values(["MainGameId", "EventType", "Coef"]).drop_duplicates(["MainGameId", "EventType"]).iterrows()
    }
    win_game_id = {
        row["MainGameId"]: row.get("GameId")
        for _, row in win_rows.sort_values(["MainGameId", "GameId"], na_position="last").drop_duplicates("MainGameId").iterrows()
    }

    stats = df[
        (df["EventType"].isin(["p1", "p2"])) &
        (df["GameType"].isin(FOOTBALL_STAT_TYPES)) &
        (df["SportName"] == "Football") &
        (df["Period"] == 0)
    ].copy()
    if stats.empty:
        return []
    stats = stats.merge(wins, how="left", on="MainGameId", suffixes=("", "_match"))
    rows = []
    for (game_id, stat_type), group in stats.groupby(["GameId", "GameType"], dropna=False):
        if group.empty:
            continue
        first = group.sort_values(
            ["MainGameId", "GameId", "GameType", "EventType", "Coef", "ContoraName", "Contora"],
            na_position="last",
            kind="mergesort",
        ).iloc[0]
        match_p1 = first.get("p1")
        match_p2 = first.get("p2")
        match_fav = get_match_favorite_by_coef_zone(match_p1, match_p2)
        stat_p1_values = group.loc[group["EventType"] == "p1", "Coef"]
        stat_p2_values = group.loc[group["EventType"] == "p2", "Coef"]
        stat_p1 = stat_p1_values.mean() if not stat_p1_values.empty else None
        stat_p2 = stat_p2_values.mean() if not stat_p2_values.empty else None
        stat_p1_source_row = first_source_row(group, "p1")
        stat_p2_source_row = first_source_row(group, "p2")
        stat_p1_source = source_label(stat_p1_source_row) if stat_p1_source_row is not None else None
        stat_p2_source = source_label(stat_p2_source_row) if stat_p2_source_row is not None else None
        if not stat_conflict_by_coef_direction(match_fav, stat_p1, stat_p2, stat_type):
            continue
        if stat_type == "Tackles":
            favorite_coef = match_p1 if match_fav == "p1" else match_p2
            if pd.isna(favorite_coef) or favorite_coef > 1.4:
                continue
        stat_fav = "p1" if pd.notna(stat_p1) and pd.notna(stat_p2) and stat_p1 < stat_p2 else "p2"
        rows.append({
            "Status": "DIFF",
            "GameId": game_id,
            "StatGameId": game_id,
            "MatchGameId": win_game_id.get(first.get("MainGameId")),
            "MainGameId": first.get("MainGameId"),
            "GameType": stat_type,
            "Sport": first.get("SportName"),
            "Champ": first.get("Champ"),
            "Opp1": first.get("Opp1"),
            "Opp2": first.get("Opp2"),
            "Start": first.get("Start"),
            "Period": 0,
            "StatType": stat_type,
            "MatchCoefP1": match_p1,
            "MatchProbabilityP1": rounded_probability(match_p1),
            "MatchSourceP1": win_source.get((first.get("MainGameId"), "p1")),
            "MatchCoefP2": match_p2,
            "MatchProbabilityP2": rounded_probability(match_p2),
            "MatchSourceP2": win_source.get((first.get("MainGameId"), "p2")),
            "StatCoefP1": stat_p1,
            "StatProbabilityP1": rounded_probability(stat_p1),
            "StatSourceP1": stat_p1_source,
            "StatCoefP2": stat_p2,
            "StatProbabilityP2": rounded_probability(stat_p2),
            "StatSourceP2": stat_p2_source,
            "MatchFavorite": match_fav,
            "StatFavorite": stat_fav,
            "ExpectedStatRole": "outsider" if stat_type in FOOTBALL_INVERTED else "favorite",
        })
    return rows


def ind_total_side_lines(df):
    required = {"GameId", "MainGameId", "GameType", "EventType", "Coef", "Param"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()
    rows = df[
        (df["EventType"].isin(["IndTotal_1_B", "IndTotal_2_B"])) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if rows.empty:
        return rows
    rows["Side"] = rows["EventType"].map({"IndTotal_1_B": "p1", "IndTotal_2_B": "p2"})
    rows["Probability"] = 1 / rows["Coef"]
    rows["ProbabilityDistance"] = (rows["Probability"] - 0.5).abs()
    rows["SourceLabel"] = rows.apply(source_label, axis=1)
    return rows


def best_param_line(rows):
    if rows.empty:
        return None
    return rows.sort_values(["ProbabilityDistance", "Coef", "Param", "GameId"], kind="mergesort").iloc[0]


IND_TOTAL_SOFT_PROBABILITY_DELTA_PP = 1.5
IND_TOTAL_SOFT_COEF_THRESHOLD = 1.1
IND_TOTAL_CENTER_SOFT_PARAM_DELTA = 0.5
IND_TOTAL_CENTER_SOFT_PROBABILITY_DELTA_PP = 20.0
IND_TOTAL_STRONG_MATCH_PROBABILITY_DELTA_PP = 15.0
MATHROBOT_SOURCE_MARKER = "XMathRobotLine"


def individual_total_soft_reasons(favorite_coef, outsider_coef):
    favorite_probability = probability(favorite_coef)
    outsider_probability = probability(outsider_coef)
    reasons = []
    probability_delta_pp = None
    if favorite_probability is not None and outsider_probability is not None:
        probability_delta_pp = round((outsider_probability - favorite_probability) * 100, 4)
        if probability_delta_pp <= IND_TOTAL_SOFT_PROBABILITY_DELTA_PP:
            reasons.append(f"individual total probability delta <= {IND_TOTAL_SOFT_PROBABILITY_DELTA_PP} pp")
    if (
        pd.notna(favorite_coef) and favorite_coef < IND_TOTAL_SOFT_COEF_THRESHOLD or
        pd.notna(outsider_coef) and outsider_coef < IND_TOTAL_SOFT_COEF_THRESHOLD
    ):
        reasons.append(f"individual total coefficient < {IND_TOTAL_SOFT_COEF_THRESHOLD}")
    return reasons, probability_delta_pp


def individual_total_center_soft_reasons(favorite_param, outsider_param, favorite_coef, outsider_coef):
    favorite_probability = probability(favorite_coef)
    outsider_probability = probability(outsider_coef)
    param_delta = None
    probability_delta_pp = None
    reasons = []
    if pd.notna(favorite_param) and pd.notna(outsider_param):
        param_delta = round(abs(favorite_param - outsider_param), 4)
    if favorite_probability is not None and outsider_probability is not None:
        probability_delta_pp = round(abs(favorite_probability - outsider_probability) * 100, 4)
    if (
        param_delta is not None and
        probability_delta_pp is not None and
        param_delta <= IND_TOTAL_CENTER_SOFT_PARAM_DELTA and
        probability_delta_pp <= IND_TOTAL_CENTER_SOFT_PROBABILITY_DELTA_PP
    ):
        reasons.append(
            f"central param delta <= {IND_TOTAL_CENTER_SOFT_PARAM_DELTA} "
            f"and probability delta <= {IND_TOTAL_CENTER_SOFT_PROBABILITY_DELTA_PP} pp"
        )
    return reasons, param_delta, probability_delta_pp


def match_favorite_probability_delta_pp(favorite, p1_coef, p2_coef):
    if favorite not in {"p1", "p2"}:
        return None
    favorite_coef = p1_coef if favorite == "p1" else p2_coef
    outsider_coef = p2_coef if favorite == "p1" else p1_coef
    favorite_probability = probability(favorite_coef)
    outsider_probability = probability(outsider_coef)
    if favorite_probability is None or outsider_probability is None:
        return None
    return round((favorite_probability - outsider_probability) * 100, 4)


def apply_strong_match_hardening(soft_reasons, match_probability_delta_pp):
    if (
        soft_reasons and
        match_probability_delta_pp is not None and
        match_probability_delta_pp >= IND_TOTAL_STRONG_MATCH_PROBABILITY_DELTA_PP
    ):
        return [], (
            f"match favorite probability delta >= "
            f"{IND_TOTAL_STRONG_MATCH_PROBABILITY_DELTA_PP} pp"
        )
    return soft_reasons, None


def is_mathrobot_individual_total_row(row):
    favorite_source = str(row.get("FavoriteSource") or "")
    outsider_source = str(row.get("OutsiderSource") or "")
    return (
        MATHROBOT_SOURCE_MARKER in favorite_source and
        MATHROBOT_SOURCE_MARKER in outsider_source
    )


def analyze_individual_total_favorite_consistency_rows(df):
    if df.empty:
        return []
    wins = df[
        (df["EventType"].isin(["p1", "p2"])) &
        (df["Coef"] > 1)
    ].copy()
    if wins.empty:
        return []
    win_pivot = wins.pivot_table(
        index=["GameId", "MainGameId", "GameType", "Period"],
        columns="EventType",
        values="Coef",
        aggfunc="mean",
    ).reset_index()
    if "p1" not in win_pivot.columns or "p2" not in win_pivot.columns:
        return []
    win_sources = {
        (row["GameId"], row["EventType"]): source_label(row)
        for _, row in wins.sort_values(["GameId", "EventType", "Coef"]).drop_duplicates(["GameId", "EventType"]).iterrows()
    }
    ind_totals = ind_total_side_lines(df)
    if ind_totals.empty:
        return []

    info = game_info_map(df)
    rows = []
    for _, win in win_pivot.iterrows():
        game_id = win.get("GameId")
        p1_coef = win.get("p1")
        p2_coef = win.get("p2")
        favorite = get_match_favorite_by_coef_zone(p1_coef, p2_coef)
        if favorite not in {"p1", "p2"}:
            continue
        outsider = "p2" if favorite == "p1" else "p1"
        match_probability_delta_pp = match_favorite_probability_delta_pp(favorite, p1_coef, p2_coef)
        game_totals = ind_totals[ind_totals["GameId"] == game_id]
        fav_event = "IndTotal_1_B" if favorite == "p1" else "IndTotal_2_B"
        out_event = "IndTotal_2_B" if favorite == "p1" else "IndTotal_1_B"
        fav_lines = game_totals[game_totals["EventType"] == fav_event]
        out_lines = game_totals[game_totals["EventType"] == out_event]
        if fav_lines.empty or out_lines.empty:
            continue

        common_params = sorted(set(fav_lines["Param"]).intersection(set(out_lines["Param"])))
        if common_params:
            for param in common_params:
                fav_line = best_param_line(fav_lines[fav_lines["Param"] == param])
                out_line = best_param_line(out_lines[out_lines["Param"] == param])
                if fav_line is None or out_line is None or fav_line["Coef"] < out_line["Coef"]:
                    continue
                soft_reasons, probability_delta_pp = individual_total_soft_reasons(
                    fav_line["Coef"],
                    out_line["Coef"],
                )
                soft_reasons, hardening_reason = apply_strong_match_hardening(
                    soft_reasons,
                    match_probability_delta_pp,
                )
                rows.append(add_game_info({
                    "Status": "SOFT" if soft_reasons else "DIFF",
                    "Rule": "same individual total parameter has worse favorite coefficient",
                    "Scenario": "same_param_coef_direction",
                    "SoftReason": "; ".join(soft_reasons),
                    "HardeningReason": hardening_reason,
                    "IndividualProbabilityDeltaPp": probability_delta_pp,
                    "SoftProbabilityDeltaThresholdPp": IND_TOTAL_SOFT_PROBABILITY_DELTA_PP,
                    "SoftCoefThreshold": IND_TOTAL_SOFT_COEF_THRESHOLD,
                    "MatchFavoriteProbabilityDeltaPp": match_probability_delta_pp,
                    "StrongMatchProbabilityDeltaThresholdPp": IND_TOTAL_STRONG_MATCH_PROBABILITY_DELTA_PP,
                    "GameId": game_id,
                    "MainGameId": win.get("MainGameId"),
                    "GameType": win.get("GameType"),
                    "Period": win.get("Period"),
                    "Favorite": favorite,
                    "Outsider": outsider,
                    "MatchCoefP1": rounded_number(p1_coef),
                    "MatchProbabilityP1": rounded_probability(p1_coef),
                    "MatchSourceP1": win_sources.get((game_id, "p1")),
                    "MatchCoefP2": rounded_number(p2_coef),
                    "MatchProbabilityP2": rounded_probability(p2_coef),
                    "MatchSourceP2": win_sources.get((game_id, "p2")),
                    "FavoriteEventType": fav_event,
                    "OutsiderEventType": out_event,
                    "FavoriteParam": rounded_number(fav_line["Param"]),
                    "FavoriteCoef": rounded_number(fav_line["Coef"]),
                    "FavoriteProbability": rounded_probability(fav_line["Coef"]),
                    "FavoriteSource": fav_line.get("SourceLabel"),
                    "OutsiderParam": rounded_number(out_line["Param"]),
                    "OutsiderCoef": rounded_number(out_line["Coef"]),
                    "OutsiderProbability": rounded_probability(out_line["Coef"]),
                    "OutsiderSource": out_line.get("SourceLabel"),
                    "FavoriteGameId": fav_line.get("GameId"),
                    "OutsiderGameId": out_line.get("GameId"),
                }, info, win.get("MainGameId")))
            continue

        fav_center = best_param_line(fav_lines)
        out_center = best_param_line(out_lines)
        if fav_center is None or out_center is None or fav_center["Param"] > out_center["Param"]:
            continue
        soft_reasons, abs_param_delta, probability_delta_pp = individual_total_center_soft_reasons(
            fav_center["Param"],
            out_center["Param"],
            fav_center["Coef"],
            out_center["Coef"],
        )
        soft_reasons, hardening_reason = apply_strong_match_hardening(
            soft_reasons,
            match_probability_delta_pp,
        )
        rows.append(add_game_info({
            "Status": "SOFT" if soft_reasons else "DIFF",
            "Rule": "favorite individual total center is not higher than outsider center",
            "Scenario": "different_param_center_direction",
            "SoftReason": "; ".join(soft_reasons),
            "HardeningReason": hardening_reason,
            "CentralParamAbsDelta": abs_param_delta,
            "CentralProbabilityDeltaPp": probability_delta_pp,
            "CentralSoftParamDeltaThreshold": IND_TOTAL_CENTER_SOFT_PARAM_DELTA,
            "CentralSoftProbabilityDeltaThresholdPp": IND_TOTAL_CENTER_SOFT_PROBABILITY_DELTA_PP,
            "MatchFavoriteProbabilityDeltaPp": match_probability_delta_pp,
            "StrongMatchProbabilityDeltaThresholdPp": IND_TOTAL_STRONG_MATCH_PROBABILITY_DELTA_PP,
            "GameId": game_id,
            "MainGameId": win.get("MainGameId"),
            "GameType": win.get("GameType"),
            "Period": win.get("Period"),
            "Favorite": favorite,
            "Outsider": outsider,
            "MatchCoefP1": rounded_number(p1_coef),
            "MatchProbabilityP1": rounded_probability(p1_coef),
            "MatchSourceP1": win_sources.get((game_id, "p1")),
            "MatchCoefP2": rounded_number(p2_coef),
            "MatchProbabilityP2": rounded_probability(p2_coef),
            "MatchSourceP2": win_sources.get((game_id, "p2")),
            "FavoriteEventType": fav_event,
            "OutsiderEventType": out_event,
            "FavoriteParam": rounded_number(fav_center["Param"]),
            "FavoriteCoef": rounded_number(fav_center["Coef"]),
            "FavoriteProbability": rounded_probability(fav_center["Coef"]),
            "FavoriteSource": fav_center.get("SourceLabel"),
            "OutsiderParam": rounded_number(out_center["Param"]),
            "OutsiderCoef": rounded_number(out_center["Coef"]),
            "OutsiderProbability": rounded_probability(out_center["Coef"]),
            "OutsiderSource": out_center.get("SourceLabel"),
            "FavoriteGameId": fav_center.get("GameId"),
            "OutsiderGameId": out_center.get("GameId"),
            "ParamDelta": rounded_number(fav_center["Param"] - out_center["Param"]),
        }, info, win.get("MainGameId")))
    return rows


def analyze_individual_total_favorite_consistency(df):
    return [
        row for row in analyze_individual_total_favorite_consistency_rows(df)
        if not is_mathrobot_individual_total_row(row)
    ]


def analyze_mathrobot_individual_total_favorite_consistency(df):
    rows = []
    for row in analyze_individual_total_favorite_consistency_rows(df):
        if is_mathrobot_individual_total_row(row):
            row = dict(row)
            row["SourcePattern"] = MATHROBOT_SOURCE_MARKER
            rows.append(row)
    return rows


def central_total_lines(df):
    totals = df[
        (df["SportName"] == "Football") &
        (df["Period"] == 0) &
        (df["GameType"].isin(SHOT_RELATION_TYPES)) &
        (df["EventType"].isin(TOTAL_CENTER_EVENTS)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if totals.empty:
        return pd.DataFrame()
    totals["ProbabilityDistance"] = (1 / totals["Coef"] - 0.5).abs()
    totals = totals.sort_values(
        ["MainGameId", "GameType", "ProbabilityDistance", "Coef", "GameId"],
        kind="mergesort",
    )
    return totals.groupby(["MainGameId", "GameType"], as_index=False).first()


def outcome_lines(df):
    outcomes = df[
        (df["SportName"] == "Football") &
        (df["Period"] == 0) &
        (df["GameType"].isin(SHOT_RELATION_TYPES)) &
        (df["EventType"].isin(["p1", "p2"]))
    ].copy()
    if outcomes.empty:
        return pd.DataFrame()
    outcomes["SourceLabel"] = outcomes.apply(source_label, axis=1)
    pivot = outcomes.pivot_table(
        index=["MainGameId", "GameId", "GameType"],
        columns="EventType",
        values="Coef",
        aggfunc="mean",
    ).reset_index()
    source_pivot = outcomes.pivot_table(
        index=["MainGameId", "GameId", "GameType"],
        columns="EventType",
        values="SourceLabel",
        aggfunc="first",
    ).reset_index()
    source_pivot = source_pivot.rename(columns={"p1": "p1_source", "p2": "p2_source"})
    pivot = pivot.merge(source_pivot, on=["MainGameId", "GameId", "GameType"], how="left")
    if "p1" not in pivot.columns:
        pivot["p1"] = pd.NA
    if "p2" not in pivot.columns:
        pivot["p2"] = pd.NA
    return pivot


def analyze_football_stat_relations(df):
    if df.empty:
        return []
    info = game_info_map(df)
    rows = []

    centers = central_total_lines(df)
    if not centers.empty:
        center_pivot = centers.pivot_table(
            index="MainGameId",
            columns="GameType",
            values="Param",
            aggfunc="first",
        ).reset_index()
        for _, item in center_pivot.iterrows():
            main_game_id = item.get("MainGameId")
            shots_on_target = item.get("ShotsOnTarget")
            shot_by_gates = item.get("ShotByGates")
            if pd.notna(shots_on_target) and pd.notna(shot_by_gates) and shots_on_target > shot_by_gates:
                source = centers[
                    (centers["MainGameId"] == main_game_id) &
                    (centers["GameType"] == "ShotsOnTarget")
                ].iloc[0]
                target = centers[
                    (centers["MainGameId"] == main_game_id) &
                    (centers["GameType"] == "ShotByGates")
                ].iloc[0]
                rows.append(add_game_info({
                    "Status": "DIFF",
                    "MainGameId": main_game_id,
                    "Rule": "ShotsOnTarget center greater than ShotByGates center",
                    "SourceGameType": "ShotsOnTarget",
                    "TargetGameType": "ShotByGates",
                    "SourceGameId": source.get("GameId"),
                    "TargetGameId": target.get("GameId"),
                    "SourceCenterParam": round(shots_on_target, 4),
                    "TargetCenterParam": round(shot_by_gates, 4),
                    "SourceCenterCoef": rounded_number(source.get("Coef")),
                    "SourceCenterProbability": rounded_probability(source.get("Coef")),
                    "SourceCenterSource": source_label(source),
                    "TargetCenterCoef": rounded_number(target.get("Coef")),
                    "TargetCenterProbability": rounded_probability(target.get("Coef")),
                    "TargetCenterSource": source_label(target),
                    "SourceCenterEventType": source.get("EventType"),
                    "TargetCenterEventType": target.get("EventType"),
                }, info, main_game_id))

    outcomes = outcome_lines(df)
    if not outcomes.empty:
        by_main = {
            main_game_id: group.set_index("GameType")
            for main_game_id, group in outcomes.groupby("MainGameId", dropna=False)
        }
        for source_type in ("ShotByGates", "ShotsOnTarget"):
            for main_game_id, group in by_main.items():
                if source_type not in group.index or "GoalFromGates" not in group.index:
                    continue
                source = group.loc[source_type]
                target = group.loc["GoalFromGates"]
                source_fav = get_match_favorite_by_coef_zone(source.get("p1"), source.get("p2"))
                if source_fav not in {"p1", "p2"} or pd.isna(target.get("p1")) or pd.isna(target.get("p2")):
                    continue
                source_target_coef = target.get("p1") if source_fav == "p1" else target.get("p2")
                opponent_target_coef = target.get("p2") if source_fav == "p1" else target.get("p1")
                if source_target_coef > opponent_target_coef:
                    continue
                target_fav = "p1" if target.get("p1") < target.get("p2") else "p2"
                rows.append(add_game_info({
                    "Status": "DIFF",
                    "MainGameId": main_game_id,
                    "Rule": f"{source_type} favorite is not outsider on GoalFromGates",
                    "SourceGameType": source_type,
                    "TargetGameType": "GoalFromGates",
                    "SourceGameId": source.get("GameId"),
                    "TargetGameId": target.get("GameId"),
                    "SourceFavorite": source_fav,
                    "TargetFavorite": target_fav,
                    "SourceCoefP1": rounded_number(source.get("p1")),
                    "SourceProbabilityP1": rounded_probability(source.get("p1")),
                    "SourceContoraP1": source.get("p1_source"),
                    "SourceCoefP2": rounded_number(source.get("p2")),
                    "SourceProbabilityP2": rounded_probability(source.get("p2")),
                    "SourceContoraP2": source.get("p2_source"),
                    "TargetCoefP1": rounded_number(target.get("p1")),
                    "TargetProbabilityP1": rounded_probability(target.get("p1")),
                    "TargetContoraP1": target.get("p1_source"),
                    "TargetCoefP2": rounded_number(target.get("p2")),
                    "TargetProbabilityP2": rounded_probability(target.get("p2")),
                    "TargetContoraP2": target.get("p2_source"),
                }, info, main_game_id))
    return rows


def coef_zone(coef):
    if pd.isna(coef):
        return None
    if coef < 1.8:
        return "favorite"
    if coef < 2.3:
        return "equal"
    return "outsider"


def favorite_by_zone(p1, p2):
    p1_zone = coef_zone(p1)
    p2_zone = coef_zone(p2)
    favorites = []
    if p1_zone == "favorite":
        favorites.append("p1")
    if p2_zone == "favorite":
        favorites.append("p2")
    if len(favorites) == 1:
        return favorites[0], p1_zone, p2_zone
    if len(favorites) > 1:
        return "both_favorite", p1_zone, p2_zone
    if p1_zone is None or p2_zone is None:
        return None, p1_zone, p2_zone
    return "no_favorite", p1_zone, p2_zone


def implied_probability_delta(p1, p2):
    if pd.isna(p1) or pd.isna(p2) or p1 <= 0 or p2 <= 0:
        return None
    return abs(1 / p1 - 1 / p2)


def normalize_subsport(row):
    direct = row.get("SubSport")
    if isinstance(direct, str) and direct.strip():
        value = direct.strip()
        aliases = {
            "call of duty": "CoD",
            "cod": "CoD",
            "cs 2": "CS2",
            "counter-strike 2": "CS2",
            "counter strike 2": "CS2",
            "dota": "Dota2",
            "dota 2": "Dota2",
            "dota2": "Dota2",
            "valorant": "Valorant",
        }
        return aliases.get(value.lower(), value)

    text = " ".join(
        str(row.get(column, ""))
        for column in ["SportName", "GameVid", "Champ", "Opp1", "Opp2"]
    ).lower()
    if "valorant" in text:
        return "Valorant"
    if "call of duty" in text or " cod" in f" {text} ":
        return "CoD"
    if "dota2" in text or "dota 2" in text:
        return "Dota2"
    if "cs2" in text or "cs 2" in text or "counter-strike 2" in text or "counter strike 2" in text:
        return "CS2"
    return direct


def is_esports_soft_period_conflict(item, game_info):
    subsport = normalize_subsport(game_info)
    if subsport not in PERIOD_CONFLICT_ESPORTS_SUBSPORTS:
        return False
    match_delta = implied_probability_delta(item.get("p1_match"), item.get("p2_match"))
    period_delta = implied_probability_delta(item.get("p1_period"), item.get("p2_period"))
    if match_delta is None or period_delta is None:
        return False
    return (
        match_delta < PERIOD_CONFLICT_ESPORTS_MATCH_PROBABILITY_DELTA and
        period_delta < PERIOD_CONFLICT_ESPORTS_PERIOD_PROBABILITY_DELTA
    )


def analyze_period_conflicts(df):
    if df.empty:
        return []
    wins = df[(df["EventType"].isin(["p1", "p2"])) & (df["GameType"] == "Main")].copy()
    if wins.empty:
        return []
    wins["SourceLabel"] = wins.apply(source_label, axis=1)
    pivot = wins.pivot_table(
        index=["MainGameId", "Period"],
        columns="EventType",
        values="Coef",
        aggfunc="mean",
    ).reset_index()
    source_pivot = wins.pivot_table(
        index=["MainGameId", "Period"],
        columns="EventType",
        values="SourceLabel",
        aggfunc="first",
    ).reset_index().rename(columns={"p1": "p1_source", "p2": "p2_source"})
    pivot = pivot.merge(source_pivot, on=["MainGameId", "Period"], how="left")
    gameid_pivot = wins.pivot_table(
        index=["MainGameId", "Period"],
        values="GameId",
        aggfunc="first",
    ).reset_index()
    pivot = pivot.merge(gameid_pivot, on=["MainGameId", "Period"], how="left")
    if "p1" not in pivot.columns or "p2" not in pivot.columns:
        return []

    match = pivot[pivot["Period"] == 0].copy()
    periods = pivot[pivot["Period"] != 0].copy()
    if match.empty or periods.empty:
        return []
    match[["match_fav", "match_p1_zone", "match_p2_zone"]] = match.apply(
        lambda row: pd.Series(favorite_by_zone(row["p1"], row["p2"])), axis=1
    )
    periods[["period_fav", "period_p1_zone", "period_p2_zone"]] = periods.apply(
        lambda row: pd.Series(favorite_by_zone(row["p1"], row["p2"])), axis=1
    )
    merged = periods.merge(
        match[["MainGameId", "GameId", "match_fav", "p1", "p2", "p1_source", "p2_source", "match_p1_zone", "match_p2_zone"]],
        on="MainGameId",
        how="inner",
        suffixes=("_period", "_match"),
    )
    conflicts = merged[
        (merged["match_fav"].isin(["p1", "p2"])) &
        (merged["period_fav"].isin(["p1", "p2"])) &
        (merged["match_fav"] != merged["period_fav"])
    ].copy()
    if conflicts.empty:
        return []
    info = game_info_map(df)
    rows = []
    for _, item in conflicts.iterrows():
        gi = info.get(item["MainGameId"], {})
        if is_esports_soft_period_conflict(item, gi):
            continue
        match_probability_delta = implied_probability_delta(item["p1_match"], item["p2_match"])
        period_probability_delta = implied_probability_delta(item["p1_period"], item["p2_period"])
        rows.append({
            "Status": "DIFF",
            "MainGameId": item["MainGameId"],
            "GameId": item.get("GameId_period"),
            "MatchGameId": item.get("GameId_match"),
            "PeriodGameId": item.get("GameId_period"),
            "GameType": "Main",
            "Sport": gi.get("SportName"),
            "SubSport": normalize_subsport(gi),
            "Champ": gi.get("Champ"),
            "Opp1": gi.get("Opp1"),
            "Opp2": gi.get("Opp2"),
            "Start": gi.get("Start"),
            "Period": item["Period"],
            "MatchFavorite": item["match_fav"],
            "MatchP1": item["p1_match"],
            "MatchProbabilityP1": rounded_probability(item["p1_match"]),
            "MatchSourceP1": item.get("p1_source_match"),
            "MatchP2": item["p2_match"],
            "MatchProbabilityP2": rounded_probability(item["p2_match"]),
            "MatchSourceP2": item.get("p2_source_match"),
            "MatchP1Zone": item["match_p1_zone"],
            "MatchP2Zone": item["match_p2_zone"],
            "PeriodFavorite": item["period_fav"],
            "PeriodP1": item["p1_period"],
            "PeriodProbabilityP1": rounded_probability(item["p1_period"]),
            "PeriodSourceP1": item.get("p1_source_period"),
            "PeriodP2": item["p2_period"],
            "PeriodProbabilityP2": rounded_probability(item["p2_period"]),
            "PeriodSourceP2": item.get("p2_source_period"),
            "PeriodP1Zone": item["period_p1_zone"],
            "PeriodP2Zone": item["period_p2_zone"],
            "MatchProbabilityDelta": round(match_probability_delta, 6) if match_probability_delta is not None else None,
            "PeriodProbabilityDelta": round(period_probability_delta, 6) if period_probability_delta is not None else None,
        })
    return rows


def analyze_tennis_what_earlear(df):
    if df.empty:
        return []
    tennis = df[
        (df["SportName"] == "Tennis") &
        (df["EventType"] == "Total_B") &
        (df["GameType"].isin(["Ace", "Breaks"])) &
        (df["Coef"].between(1.5, 3.0))
    ].drop_duplicates().copy()
    if tennis.empty:
        return []
    pivot = tennis.pivot_table(
        index=["MainGameId", "SportName", "Champ", "Opp1", "Opp2", "Start", "Period"],
        columns="GameType",
        values="Param",
        aggfunc="mean",
    ).reset_index()
    if "Ace" not in pivot.columns or "Breaks" not in pivot.columns:
        return []
    pivot = pivot.dropna(subset=["Ace", "Breaks"], how="any")
    earlier = df[
        (df["SportName"] == "Tennis") &
        (df["EventType"].isin(["ace_before_break", "break_before_ace"]))
    ].drop_duplicates().copy()
    if earlier.empty:
        return []
    earlier_pivot = earlier.pivot_table(
        index=["MainGameId"],
        columns="EventType",
        values="Coef",
        aggfunc="mean",
    ).reset_index()
    merged = pivot.merge(earlier_pivot, on="MainGameId", how="inner")
    if "ace_before_break" not in merged.columns or "break_before_ace" not in merged.columns:
        return []
    bad = merged[
        ((merged["Ace"] > merged["Breaks"]) & (merged["ace_before_break"] > 2.0)) |
        ((merged["Breaks"] > merged["Ace"]) & (merged["break_before_ace"] > 2.0))
    ].copy()
    rows = []
    for _, item in bad.iterrows():
        rows.append({
            "Status": "DIFF",
            "MainGameId": item["MainGameId"],
            "Sport": item["SportName"],
            "Champ": item["Champ"],
            "Opp1": item["Opp1"],
            "Opp2": item["Opp2"],
            "Start": item["Start"],
            "Period": item["Period"],
            "Param_Ace": item["Ace"],
            "Param_Breaks": item["Breaks"],
            "koef_ace_before_break": item["ace_before_break"],
            "koef_break_before_ace": item["break_before_ace"],
        })
    return rows


def tennis_special_first_serve_rows(df):
    required = {"SportName", "GroupId", "MainGameId", "Period", "Coef", "Param"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()
    source = df.copy()
    source["GroupId"] = pd.to_numeric(source["GroupId"], errors="coerce")
    rows = source[
        (source["SportName"] == "Tennis") &
        (source["GroupId"].isin(
            set(TENNIS_FIRST_SERVE_PERCENT_GROUPS) |
            set(TENNIS_FIRST_SERVE_HANDICAP_GROUPS)
        )) &
        (source["Coef"] > 1) &
        (source["Param"].notna())
    ].copy()
    if rows.empty:
        return rows
    rows["Side"] = rows["GroupId"].map({
        **TENNIS_FIRST_SERVE_PERCENT_GROUPS,
        **TENNIS_FIRST_SERVE_HANDICAP_GROUPS,
    })
    rows["Metric"] = rows["GroupId"].map(
        lambda group_id: "percent" if group_id in TENNIS_FIRST_SERVE_PERCENT_GROUPS else "handicap"
    )
    rows["Source"] = rows.apply(source_label, axis=1)
    rows["SourceKey"] = rows.apply(
        lambda row: f"{row.get('ContoraName', '')}|{row.get('Contora', '')}",
        axis=1,
    )
    rows["Probability"] = 1 / rows["Coef"]
    rows["ProbabilityDistance"] = (rows["Probability"] - 0.5).abs()
    return rows.sort_values(
        ["MainGameId", "Period", "SourceKey", "Metric", "Side", "ProbabilityDistance", "Coef", "Param", "GameId"],
        na_position="last",
        kind="mergesort",
    )


def analyze_tenis_special(df):
    rows = tennis_special_first_serve_rows(df)
    if rows.empty:
        return []
    centers = rows.drop_duplicates(
        ["MainGameId", "Period", "SourceKey", "Metric", "Side"],
        keep="first",
    )
    pivot = centers.pivot_table(
        index=["MainGameId", "Period", "SourceKey"],
        columns=["Metric", "Side"],
        values=["Param", "Coef", "Probability", "GameId", "GroupId", "Source"],
        aggfunc="first",
    )
    pivot.columns = [f"{metric}_{side}_{field}" for field, metric, side in pivot.columns]
    pivot = pivot.reset_index()

    required_columns = [
        "percent_p1_Param",
        "percent_p2_Param",
        "handicap_p1_Param",
        "handicap_p2_Param",
    ]
    if not set(required_columns).issubset(pivot.columns):
        return []
    pivot = pivot.dropna(subset=required_columns)
    if pivot.empty:
        return []

    info = game_info_map(df)
    result = []
    for _, item in pivot.iterrows():
        percent_p1 = item["percent_p1_Param"]
        percent_p2 = item["percent_p2_Param"]
        if percent_p1 == percent_p2:
            continue
        favorite = "p1" if percent_p1 > percent_p2 else "p2"
        handicap_p1 = item["handicap_p1_Param"]
        handicap_p2 = item["handicap_p2_Param"]
        if favorite == "p1":
            if handicap_p1 < handicap_p2:
                continue
            expected = "handicap_p1 < handicap_p2"
        else:
            if handicap_p2 < handicap_p1:
                continue
            expected = "handicap_p2 < handicap_p1"

        gi = info.get(item["MainGameId"], {})
        result.append({
            "Status": "DIFF",
            "Rule": "first serve percent favorite should have lower first serve handicap",
            "Scenario": "first_serve_percent_handicap_direction",
            "MainGameId": item["MainGameId"],
            "GameId": item.get(f"handicap_{favorite}_GameId"),
            "GameType": "Statistics",
            "Sport": gi.get("SportName"),
            "Champ": gi.get("Champ"),
            "Opp1": gi.get("Opp1"),
            "Opp2": gi.get("Opp2"),
            "Start": gi.get("Start"),
            "Period": item["Period"],
            "SourceKey": item["SourceKey"],
            "Source": item.get("percent_p1_Source") or item.get("percent_p2_Source"),
            "Favorite": favorite,
            "Expected": expected,
            "PercentParamP1": rounded_number(percent_p1),
            "PercentParamP2": rounded_number(percent_p2),
            "PercentParamDelta": rounded_number(percent_p1 - percent_p2),
            "PercentCoefP1": rounded_number(item.get("percent_p1_Coef")),
            "PercentCoefP2": rounded_number(item.get("percent_p2_Coef")),
            "PercentProbabilityP1": rounded_number(item.get("percent_p1_Probability"), 6),
            "PercentProbabilityP2": rounded_number(item.get("percent_p2_Probability"), 6),
            "PercentGameIdP1": item.get("percent_p1_GameId"),
            "PercentGameIdP2": item.get("percent_p2_GameId"),
            "PercentGroupIdP1": item.get("percent_p1_GroupId"),
            "PercentGroupIdP2": item.get("percent_p2_GroupId"),
            "HandicapParamP1": rounded_number(handicap_p1),
            "HandicapParamP2": rounded_number(handicap_p2),
            "HandicapParamDelta": rounded_number(handicap_p1 - handicap_p2),
            "HandicapCoefP1": rounded_number(item.get("handicap_p1_Coef")),
            "HandicapCoefP2": rounded_number(item.get("handicap_p2_Coef")),
            "HandicapProbabilityP1": rounded_number(item.get("handicap_p1_Probability"), 6),
            "HandicapProbabilityP2": rounded_number(item.get("handicap_p2_Probability"), 6),
            "HandicapGameIdP1": item.get("handicap_p1_GameId"),
            "HandicapGameIdP2": item.get("handicap_p2_GameId"),
            "HandicapGroupIdP1": item.get("handicap_p1_GroupId"),
            "HandicapGroupIdP2": item.get("handicap_p2_GroupId"),
        })
    return sorted(result, key=lambda row: abs(float(row["PercentParamDelta"])), reverse=True)


def basketball_period_delta_limit(full_param):
    if pd.isna(full_param):
        return None
    if full_param < 5:
        return 0.5
    if full_param < 10:
        return 1.0
    if full_param < 15:
        return 1.5
    if full_param < 20:
        return 2.0
    if full_param < 25:
        return 2.5
    if full_param < 30:
        return 3.0
    return 3.5


def basketball_monotonicity_param_tolerance(min_param):
    if pd.isna(min_param):
        return 0.0
    if min_param < 10:
        return 1.0
    if min_param < 20:
        return 1.5
    if min_param < 30:
        return 2.0
    if min_param > 30:
        return 2.5
    return 0.0


def basketball_allowed_monotonicity_gap(left_param, left_coef, right_param, right_coef):
    if any(pd.isna(value) for value in [left_param, left_coef, right_param, right_coef]):
        return False
    param_diff = abs(right_param - left_param)
    tolerance = basketball_monotonicity_param_tolerance(min(left_param, right_param))
    if tolerance <= 0 or param_diff > tolerance:
        return False
    probability_diff = abs(1 / left_coef - 1 / right_coef)
    return probability_diff <= 0.03


def basketball_player_centers(df):
    required_columns = {"SportName", "GameType", "EventType", "Player", "MainGameId", "Period", "Coef", "Param"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    basketball = df[
        (df["SportName"] == "Basketball") &
        (df["GameType"] == "GoalPlayers") &
        (df["Player"].fillna("").astype(str).str.strip() != "") &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if basketball.empty:
        return pd.DataFrame()

    point_players = basketball[
        basketball["EventType"].isin(BASKETBALL_PLAYER_POINT_EVENTS)
    ][["MainGameId", "Player"]].drop_duplicates()
    if point_players.empty:
        return pd.DataFrame()

    centers = basketball[basketball["EventType"].isin(BASKETBALL_EVENT_STAT)].merge(
        point_players,
        on=["MainGameId", "Player"],
        how="inner",
    )
    if centers.empty:
        return pd.DataFrame()

    centers["Stat"] = centers["EventType"].map(BASKETBALL_EVENT_STAT)
    centers["ProbabilityDistance"] = (1 / centers["Coef"] - 0.5).abs()
    centers["Probability"] = 1 / centers["Coef"]
    centers["SourceLabel"] = centers.apply(source_label, axis=1)
    centers = centers.sort_values(
        ["MainGameId", "Player", "Period", "Stat", "ProbabilityDistance", "Coef", "Param"],
        kind="mergesort",
    )
    return centers.drop_duplicates(["MainGameId", "Player", "Period", "Stat"])


def analyze_basketball_player_periods(centers):
    if centers.empty:
        return []
    points = centers[centers["Stat"] == "points"].copy()
    if points.empty:
        return []
    by_key = {
        (row["MainGameId"], row["Player"], row["Period"]): row
        for _, row in points.iterrows()
    }
    rows = []
    for (main_game_id, player, period), period_row in by_key.items():
        if period not in BASKETBALL_PERIOD_EXPECTATIONS:
            continue
        full_row = by_key.get((main_game_id, player, 0))
        if full_row is None:
            continue
        divider = BASKETBALL_PERIOD_EXPECTATIONS[period]
        expected = full_row["Param"] / divider
        delta = period_row["Param"] - expected
        abs_delta = abs(delta)
        delta_limit = basketball_period_delta_limit(full_row["Param"])
        if delta_limit is None or abs_delta <= delta_limit:
            continue
        status = near_delta_status(abs_delta, delta_limit, BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN)
        rows.append({
            "Status": status,
            "Rule": "player points period center deviates from full game share",
            "MainGameId": main_game_id,
            "GameId": period_row.get("GameId"),
            "GameType": period_row.get("GameType"),
            "Sport": period_row.get("SportName"),
            "Champ": period_row.get("Champ"),
            "Opp1": period_row.get("Opp1"),
            "Opp2": period_row.get("Opp2"),
            "Start": period_row.get("Start"),
            "Player": player,
            "Stat": "points",
            "EventType": period_row.get("EventType"),
            "Period": period,
            "PeriodParam": round(period_row["Param"], 4),
            "PeriodCoef": round(period_row["Coef"], 4),
            "PeriodProbability": rounded_probability(period_row["Coef"]),
            "PeriodSource": period_row.get("SourceLabel"),
            "FullGameId": full_row.get("GameId"),
            "FullParam": round(full_row["Param"], 4),
            "FullCoef": round(full_row["Coef"], 4),
            "FullProbability": rounded_probability(full_row["Coef"]),
            "FullSource": full_row.get("SourceLabel"),
            "ExpectedParam": round(expected, 4),
            "Delta": round(delta, 4),
            "DeltaLimit": round(delta_limit, 4),
            "SoftDeltaMargin": BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN,
            "SoftReason": (
                f"abs(delta) <= delta limit + {BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN}"
                if status == "SOFT" else None
            ),
        })
    return rows


def analyze_basketball_player_monotonicity(df):
    required_columns = {"SportName", "GameType", "EventType", "Player", "MainGameId", "GameId", "Period", "Coef", "Param"}
    if df.empty or not required_columns.issubset(df.columns):
        return []

    basketball = df[
        (df["SportName"] == "Basketball") &
        (df["GameType"] == "GoalPlayers") &
        (df["Player"].fillna("").astype(str).str.strip() != "") &
        (df["EventType"].isin(BASKETBALL_EVENT_STAT)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if basketball.empty:
        return []

    point_players = basketball[
        basketball["EventType"].isin(BASKETBALL_PLAYER_POINT_EVENTS)
    ][["MainGameId", "Player"]].drop_duplicates()
    basketball = basketball.merge(point_players, on=["MainGameId", "Player"], how="inner")
    if basketball.empty:
        return []

    rows = []
    group_columns = ["MainGameId", "GameId", "Period", "EventType", "Player"]
    for _, group in basketball.groupby(group_columns, dropna=False):
        ordered = group.sort_values(["Param", "Coef"], kind="mergesort")
        records = list(ordered.to_dict("records"))
        if len(records) < 2:
            continue
        event_type = records[0].get("EventType")
        is_over = str(event_type).endswith("_B") or str(event_type).endswith("_tb")
        is_under = str(event_type).endswith("_M") or str(event_type).endswith("_tm")
        if not is_over and not is_under:
            continue
        for left, right in zip(records, records[1:]):
            left_coef = left.get("Coef")
            right_coef = right.get("Coef")
            violation = (is_over and right_coef < left_coef) or (is_under and right_coef > left_coef)
            if not violation:
                continue
            if basketball_allowed_monotonicity_gap(left.get("Param"), left_coef, right.get("Param"), right_coef):
                continue
            probability_diff = abs(1 / left_coef - 1 / right_coef)
            rows.append({
                "Status": "DIFF",
                "Rule": "player total coefficient monotonicity violation",
                "MainGameId": left.get("MainGameId"),
                "GameId": left.get("GameId"),
                "GameType": left.get("GameType"),
                "Sport": left.get("SportName"),
                "Champ": left.get("Champ"),
                "Opp1": left.get("Opp1"),
                "Opp2": left.get("Opp2"),
                "Start": left.get("Start"),
                "Player": left.get("Player"),
                "Stat": BASKETBALL_EVENT_STAT.get(event_type),
                "EventType": event_type,
                "Period": left.get("Period"),
                "Direction": "over" if is_over else "under",
                "LeftParam": rounded_number(left.get("Param")),
                "LeftCoef": round(left_coef, 4),
                "LeftProbability": rounded_probability(left_coef),
                "LeftSource": source_label(left),
                "RightParam": rounded_number(right.get("Param")),
                "RightCoef": round(right_coef, 4),
                "RightProbability": rounded_probability(right_coef),
                "RightSource": source_label(right),
                "ParamDiff": rounded_abs_diff(left.get("Param"), right.get("Param")),
                "ProbabilityDiff": round(probability_diff, 6),
            })
    return rows


def analyze_basketball_player_combinations(centers):
    if centers.empty:
        return []
    period_zero = centers[centers["Period"] == 0].copy()
    if period_zero.empty:
        return []
    by_key = {
        (row["MainGameId"], row["Player"], row["Stat"]): row
        for _, row in period_zero.iterrows()
    }
    combos = {
        "points_rebounds": ("points", "rebounds"),
        "points_assists": ("points", "assists"),
        "rebounds_assists": ("rebounds", "assists"),
        "points_rebounds_assists": ("points", "rebounds", "assists"),
    }
    rows = []
    for (main_game_id, player, stat), combo_row in by_key.items():
        if stat not in combos:
            continue
        components = combos[stat]
        component_rows = [by_key.get((main_game_id, player, component)) for component in components]
        if any(row is None for row in component_rows):
            continue
        expected = sum(row["Param"] for row in component_rows)
        delta = combo_row["Param"] - expected
        abs_delta = abs(delta)
        delta_limit = 1.5
        if abs_delta <= delta_limit:
            continue
        status = near_delta_status(abs_delta, delta_limit, BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN)
        row = {
            "Status": status,
            "Rule": "player combined stat center differs from component centers",
            "MainGameId": main_game_id,
            "GameId": combo_row.get("GameId"),
            "GameType": combo_row.get("GameType"),
            "Sport": combo_row.get("SportName"),
            "Champ": combo_row.get("Champ"),
            "Opp1": combo_row.get("Opp1"),
            "Opp2": combo_row.get("Opp2"),
            "Start": combo_row.get("Start"),
            "Player": player,
            "Stat": stat,
            "EventType": combo_row.get("EventType"),
            "Period": 0,
            "CenterParam": round(combo_row["Param"], 4),
            "CenterCoef": round(combo_row["Coef"], 4),
            "CenterProbability": rounded_probability(combo_row["Coef"]),
            "CenterSource": combo_row.get("SourceLabel"),
            "ExpectedParam": round(expected, 4),
            "Delta": round(delta, 4),
            "DeltaLimit": delta_limit,
            "SoftDeltaMargin": BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN,
            "SoftReason": (
                f"abs(delta) <= delta limit + {BASKETBALL_PLAYER_NEAR_DELTA_SOFT_MARGIN}"
                if status == "SOFT" else None
            ),
        }
        for component, component_row in zip(components, component_rows):
            row[f"{component}Param"] = round(component_row["Param"], 4)
            row[f"{component}Coef"] = round(component_row["Coef"], 4)
            row[f"{component}Probability"] = rounded_probability(component_row["Coef"])
            row[f"{component}Source"] = component_row.get("SourceLabel")
        rows.append(row)
    return rows


def analyze_basketball_players(df):
    centers = basketball_player_centers(df)
    rows = []
    rows.extend(analyze_basketball_player_periods(centers))
    rows.extend(analyze_basketball_player_monotonicity(df))
    rows.extend(analyze_basketball_player_combinations(centers))
    return rows


def basketball_q4_handicap_rows(df):
    required = {"SportName", "GameType", "Period", "EventType", "Coef", "Param"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()
    rows = df[
        (df["SportName"] == "Basketball") &
        (df["GameType"] == "Main") &
        (df["Period"].isin([1, 4])) &
        (df["EventType"].isin(BASKETBALL_HANDICAP_EVENTS)) &
        (df["Coef"] > 1) &
        (df["Param"].notna())
    ].copy()
    if rows.empty:
        return rows
    rows["Probability"] = 1 / rows["Coef"]
    rows["CoefDistance"] = (rows["Coef"] - 1.95).abs()
    rows["SourceLabel"] = rows.apply(source_label, axis=1)
    return rows


def basketball_q4_handicap_centers(rows):
    if rows.empty:
        return rows
    ordered = rows.sort_values(
        ["MainGameId", "EventType", "Period", "CoefDistance", "Coef", "Param"],
        kind="mergesort",
    )
    return ordered.drop_duplicates(["MainGameId", "EventType", "Period"], keep="first")


def basketball_q4_same_param_lines(rows):
    if rows.empty:
        return {}
    ordered = rows.sort_values(
        ["MainGameId", "EventType", "Period", "Param", "CoefDistance", "Coef", "GameId"],
        kind="mergesort",
    )
    best = ordered.drop_duplicates(["MainGameId", "EventType", "Period", "Param"], keep="first")
    return {
        (row["MainGameId"], row["EventType"], row["Period"], row["Param"]): row
        for _, row in best.iterrows()
    }


def analyze_basketball_q4_handicap_shift(df):
    rows = basketball_q4_handicap_rows(df)
    if rows.empty:
        return []

    centers = basketball_q4_handicap_centers(rows)
    same_param_lines = basketball_q4_same_param_lines(rows)
    center_by_key = {
        (row["MainGameId"], row["EventType"], row["Period"]): row
        for _, row in centers.iterrows()
    }

    result = []
    for (main_game_id, event_type, period), q1 in center_by_key.items():
        if period != 1:
            continue
        q4_center = center_by_key.get((main_game_id, event_type, 4))
        if q4_center is None:
            continue

        base = {
            "Status": "DIFF",
            "Rule": "basketball fourth quarter handicap differs from first quarter",
            "MainGameId": main_game_id,
            "GameType": q1.get("GameType"),
            "Sport": q1.get("SportName"),
            "Champ": q1.get("Champ"),
            "Opp1": q1.get("Opp1"),
            "Opp2": q1.get("Opp2"),
            "Start": q1.get("Start"),
            "EventType": event_type,
            "Q1GameId": q1.get("GameId"),
            "Q1Param": rounded_number(q1.get("Param")),
            "Q1Coef": rounded_number(q1.get("Coef")),
            "Q1Probability": rounded_number(q1.get("Probability"), 6),
            "Q1Source": q1.get("SourceLabel"),
            "Q4CentralGameId": q4_center.get("GameId"),
            "Q4CentralParam": rounded_number(q4_center.get("Param")),
            "Q4CentralCoef": rounded_number(q4_center.get("Coef")),
            "Q4CentralProbability": rounded_number(q4_center.get("Probability"), 6),
            "Q4CentralSource": q4_center.get("SourceLabel"),
        }

        same_q4 = same_param_lines.get((main_game_id, event_type, 4, q1["Param"]))
        if same_q4 is not None:
            probability_delta = same_q4["Probability"] - q1["Probability"]
            abs_probability_delta = abs(probability_delta)
            if abs_probability_delta <= BASKETBALL_Q4_HANDICAP_PROBABILITY_DELTA_THRESHOLD:
                continue
            row = dict(base)
            row.update({
                "Scenario": "same_param_probability_delta",
                "Q4SameParamGameId": same_q4.get("GameId"),
                "Q4SameParam": rounded_number(same_q4.get("Param")),
                "Q4SameParamCoef": rounded_number(same_q4.get("Coef")),
                "Q4SameParamProbability": rounded_number(same_q4.get("Probability"), 6),
                "Q4SameParamSource": same_q4.get("SourceLabel"),
                "ProbabilityDelta": round(probability_delta, 6),
                "AbsProbabilityDelta": round(abs_probability_delta, 6),
                "ProbabilityDeltaThreshold": BASKETBALL_Q4_HANDICAP_PROBABILITY_DELTA_THRESHOLD,
            })
            result.append(row)
            continue

        param_delta = q4_center["Param"] - q1["Param"]
        abs_param_delta = abs(param_delta)
        if abs_param_delta <= BASKETBALL_Q4_HANDICAP_PARAM_DELTA_THRESHOLD:
            continue
        row = dict(base)
        row.update({
            "Scenario": "missing_param_central_param_delta",
            "ParamDelta": round(param_delta, 4),
            "AbsParamDelta": round(abs_param_delta, 4),
            "ParamDeltaThreshold": BASKETBALL_Q4_HANDICAP_PARAM_DELTA_THRESHOLD,
        })
        result.append(row)

    return sorted(
        result,
        key=lambda row: (
            row.get("AbsProbabilityDelta", 0),
            row.get("AbsParamDelta", 0),
        ),
        reverse=True,
    )


CHECKS = {
    "period_deviations_average": analyze_period_deviations_average,
    "poisson_total_consistency": analyze_poisson_total_consistency,
    "bounded_score_total_consistency": analyze_bounded_score_total_consistency,
    "stat_conflicts": analyze_stat_conflicts,
    "individual_total_favorite_consistency": analyze_individual_total_favorite_consistency,
    "mathrobot_individual_total_favorite_consistency": analyze_mathrobot_individual_total_favorite_consistency,
    "football_stat_relations": analyze_football_stat_relations,
    "basketball_players": analyze_basketball_players,
    "basketball_q4_handicap_shift": analyze_basketball_q4_handicap_shift,
    "period_conflicts": analyze_period_conflicts,
    "tennis_special_what_earlear": analyze_tennis_what_earlear,
    "tenis_special": analyze_tenis_special,
}


def analyze_all_checks(snapshot, reports_dir):
    games = load_games(snapshot)
    df = apply_exclusions(games_to_events(games))
    reports_dir = Path(reports_dir)
    summaries = {}
    csvs = {}
    with ThreadPoolExecutor(max_workers=len(CHECKS)) as executor:
        futures = {executor.submit(fn, df): check_name for check_name, fn in CHECKS.items()}
        results = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    for check_name in CHECKS:
        rows = results.get(check_name, [])
        output = reports_dir / f"{check_name}.csv"
        write_csv(output, rows)
        summaries[check_name] = summary(rows, output)
        csvs[check_name] = output
    return summaries, csvs
