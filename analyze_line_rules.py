import csv
import json
import zipfile
from collections import defaultdict
from pathlib import Path

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
        json_name = next(name for name in archive.namelist() if name.lower().endswith(".json"))
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
    cols = ["MainGameId", "SportName", "Champ", "Opp1", "Opp2", "Start"]
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

    mean_param = filtered.groupby(
        ["GameId", "MainGameId", "GameType", "Period", "EventType"], dropna=False
    ).agg(Param=("Param", "mean")).reset_index()

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
                if threshold is None or abs(delta) <= threshold:
                    continue
                row = {
                    "Status": "DIFF",
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
                    "Delta": round(delta, 4),
                    "CriticalDelta": threshold,
                    "GID0": item[p0_gid],
                }
                for period, col, gid_col in zip(periods, period_cols, period_gids):
                    row[f"P{period}"] = round(item[col], 4)
                    row[f"GID{period}"] = item[gid_col]
                rows.append(row)
    return sorted(rows, key=lambda row: abs(float(row["Delta"])), reverse=True)


def analyze_total_deviations_average(df):
    if df.empty:
        return []
    filtered = df[
        (df["SportName"] == "Football") &
        (df["Coef"].between(1.65, 2.3)) &
        (df["EventType"].isin([
            "Total_B", "Total_M",
            "IndTotal_1_B", "IndTotal_1_M",
            "IndTotal_2_B", "IndTotal_2_M",
        ]))
    ].copy()
    if filtered.empty:
        return []
    filtered["CoefDistance"] = (filtered["Coef"] - 1.95).abs()
    closest_param = filtered.sort_values(
        ["MainGameId", "GameType", "Period", "EventType", "CoefDistance", "Coef"]
    ).drop_duplicates(
        ["MainGameId", "GameType", "Period", "EventType"],
        keep="first",
    )
    pivot = closest_param.pivot_table(
        index=["MainGameId", "GameType"],
        columns=["EventType", "Period"],
        values="Param",
        aggfunc="first",
    )
    pivot.columns = [f"{event}_{period}_param" for event, period in pivot.columns]
    pivot = pivot.reset_index()
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
                if delta <= 1.5:
                    continue
                gi = info.get(item["MainGameId"], {})
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
                    "Total": round(item[total_col], 4),
                    "IndTotal1": round(item[ind1_col], 4),
                    "IndTotal2": round(item[ind2_col], 4),
                    "Expected": round(expected, 4),
                    "Delta": round(delta, 4),
                })
    return sorted(rows, key=lambda row: float(row["Delta"]), reverse=True)


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


def analyze_stat_conflicts(df):
    if df.empty:
        return []
    wins = df[
        (df["EventType"].isin(["p1", "p2"])) &
        (df["GameType"] == "Main") &
        (df["SportName"] == "Football") &
        (df["Period"] == 0)
    ].pivot_table(index="MainGameId", columns="EventType", values="Coef", aggfunc="mean").reset_index()
    if wins.empty or "p1" not in wins.columns or "p2" not in wins.columns:
        return []

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
        first = group.iloc[0]
        match_p1 = first.get("p1")
        match_p2 = first.get("p2")
        max_coef = 1.7 if stat_type == "Corners" else 2.2
        match_fav = get_match_favorite(match_p1, match_p2, max_coef=max_coef)
        stat_p1 = group[group["EventType"] == "p1"]["Coef"].iloc[0] if "p1" in set(group["EventType"]) else None
        stat_p2 = group[group["EventType"] == "p2"]["Coef"].iloc[0] if "p2" in set(group["EventType"]) else None
        stat_fav = get_stat_favorite(stat_p1, stat_p2, stat_type)
        if match_fav == "noone" or stat_fav == "noone" or match_fav == stat_fav:
            continue
        if stat_type == "Tackles":
            favorite_coef = match_p1 if match_fav == "p1" else match_p2
            if pd.isna(favorite_coef) or favorite_coef > 1.4:
                continue
        rows.append({
            "Status": "DIFF",
            "GameId": game_id,
            "MainGameId": first.get("MainGameId"),
            "Sport": first.get("SportName"),
            "Champ": first.get("Champ"),
            "Opp1": first.get("Opp1"),
            "Opp2": first.get("Opp2"),
            "Start": first.get("Start"),
            "StatType": stat_type,
            "MatchCoefP1": match_p1,
            "MatchCoefP2": match_p2,
            "StatCoefP1": stat_p1,
            "StatCoefP2": stat_p2,
            "MatchFavorite": match_fav,
            "StatFavorite": stat_fav,
        })
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


def analyze_period_conflicts(df):
    if df.empty:
        return []
    wins = df[(df["EventType"].isin(["p1", "p2"])) & (df["GameType"] == "Main")].copy()
    if wins.empty:
        return []
    pivot = wins.pivot_table(
        index=["MainGameId", "Period"],
        columns="EventType",
        values="Coef",
        aggfunc="mean",
    ).reset_index()
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
        match[["MainGameId", "match_fav", "p1", "p2", "match_p1_zone", "match_p2_zone"]],
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
        rows.append({
            "Status": "DIFF",
            "MainGameId": item["MainGameId"],
            "GameType": "Main",
            "Sport": gi.get("SportName"),
            "Champ": gi.get("Champ"),
            "Opp1": gi.get("Opp1"),
            "Opp2": gi.get("Opp2"),
            "Start": gi.get("Start"),
            "Period": item["Period"],
            "MatchFavorite": item["match_fav"],
            "MatchP1": item["p1_match"],
            "MatchP2": item["p2_match"],
            "MatchP1Zone": item["match_p1_zone"],
            "MatchP2Zone": item["match_p2_zone"],
            "PeriodFavorite": item["period_fav"],
            "PeriodP1": item["p1_period"],
            "PeriodP2": item["p2_period"],
            "PeriodP1Zone": item["period_p1_zone"],
            "PeriodP2Zone": item["period_p2_zone"],
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


CHECKS = {
    "period_deviations_average": analyze_period_deviations_average,
    "total_deviations_average": analyze_total_deviations_average,
    "stat_conflicts": analyze_stat_conflicts,
    "period_conflicts": analyze_period_conflicts,
    "tennis_special_what_earlear": analyze_tennis_what_earlear,
}


def analyze_all_checks(snapshot, reports_dir):
    games = load_games(snapshot)
    df = apply_exclusions(games_to_events(games))
    reports_dir = Path(reports_dir)
    summaries = {}
    csvs = {}
    for check_name, fn in CHECKS.items():
        rows = fn(df)
        output = reports_dir / f"{check_name}.csv"
        write_csv(output, rows)
        summaries[check_name] = summary(rows, output)
        csvs[check_name] = output
    return summaries, csvs
