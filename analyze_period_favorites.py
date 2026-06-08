import argparse
import csv
import json
import zipfile
from collections import defaultdict
from pathlib import Path


HOME_WIN_EVENT_ID = 1
AWAY_WIN_EVENT_ID = 3
FAVORITE_THRESHOLD = 1.8
OUTSIDER_THRESHOLD = 2.3


def load_games(snapshot_zip):
    with zipfile.ZipFile(snapshot_zip) as archive:
        json_name = next((name for name in archive.namelist() if name.lower().endswith(".json")), None)
        if json_name is None:
            raise RuntimeError(f"Snapshot ZIP has no .json file: {snapshot_zip}")
        with archive.open(json_name) as f:
            return json.load(f)


def first_coef(game, event_id):
    for event in game.get("Events") or []:
        if event.get("EventId") == event_id:
            return event.get("Coef")
    return None


def favorite_for_game(game):
    p1_coef = first_coef(game, HOME_WIN_EVENT_ID)
    p2_coef = first_coef(game, AWAY_WIN_EVENT_ID)

    if p1_coef is None or p2_coef is None:
        return None, p1_coef, p2_coef
    if p1_coef == p2_coef:
        return "tie", p1_coef, p2_coef
    if p1_coef < p2_coef:
        return "p1", p1_coef, p2_coef
    return "p2", p1_coef, p2_coef


def coef_zone(coef):
    if coef is None:
        return None
    if coef < FAVORITE_THRESHOLD:
        return "favorite"
    if coef < OUTSIDER_THRESHOLD:
        return "equal"
    return "outsider"


def favorite_by_zone(game):
    p1_coef = first_coef(game, HOME_WIN_EVENT_ID)
    p2_coef = first_coef(game, AWAY_WIN_EVENT_ID)
    p1_zone = coef_zone(p1_coef)
    p2_zone = coef_zone(p2_coef)

    favorite_sides = []
    if p1_zone == "favorite":
        favorite_sides.append("p1")
    if p2_zone == "favorite":
        favorite_sides.append("p2")

    if len(favorite_sides) == 1:
        favorite = favorite_sides[0]
    elif len(favorite_sides) > 1:
        favorite = "both_favorite"
    elif p1_zone is None or p2_zone is None:
        favorite = None
    else:
        favorite = "no_favorite"

    return favorite, p1_coef, p2_coef, p1_zone, p2_zone


def favorite_name(game, favorite):
    if favorite == "p1":
        return game.get("Opp1")
    if favorite == "p2":
        return game.get("Opp2")
    if favorite == "tie":
        return "tie"
    return None


def period_sort_value(period):
    return (period is None, period if period is not None else 10**12)


def write_csv(path, fieldnames, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze_games(games, output="period_favorite_check.csv", mismatches_output="period_favorite_mismatches.csv"):
    groups = defaultdict(list)
    for game in games:
        groups[(game.get("MainGameId"), game.get("GameType"))].append(game)

    rows = []
    skipped_no_period0 = 0
    skipped_single_period = 0
    skipped_no_base_favorite = 0

    for (main_game_id, game_type), group in sorted(groups.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        periods = {game.get("Period") for game in group}
        if len(periods) < 2:
            skipped_single_period += 1
            continue

        period0_games = [game for game in group if game.get("Period") == 0]
        if not period0_games:
            skipped_no_period0 += 1
            continue

        base_game = period0_games[0]
        base_favorite, base_p1_coef, base_p2_coef, base_p1_zone, base_p2_zone = favorite_by_zone(base_game)
        if base_favorite in (None, "no_favorite", "both_favorite"):
            skipped_no_base_favorite += 1
            continue

        for game in sorted(group, key=lambda g: (period_sort_value(g.get("Period")), g.get("GameId") or 0)):
            if game.get("Period") == 0:
                continue

            period_favorite, period_p1_coef, period_p2_coef, period_p1_zone, period_p2_zone = favorite_by_zone(game)
            if period_favorite is None:
                status = "NO_PERIOD_FAVORITE"
            elif period_favorite == "no_favorite":
                status = "PERIOD_NO_FAVORITE"
            elif period_favorite == "both_favorite":
                status = "PERIOD_BOTH_FAVORITE"
            elif period_favorite == base_favorite:
                status = "SAME"
            else:
                status = "DIFF"

            rows.append({
                "Status": status,
                "MainGameId": main_game_id,
                "GameType": game_type,
                "BaseGameId": base_game.get("GameId"),
                "PeriodGameId": game.get("GameId"),
                "Sport": game.get("SportName"),
                "Champ": game.get("Champ"),
                "Opp1": game.get("Opp1"),
                "Opp2": game.get("Opp2"),
                "Start": game.get("Start"),
                "BasePeriod": 0,
                "Period": game.get("Period"),
                "BaseFavoriteSide": base_favorite,
                "BaseFavoriteName": favorite_name(base_game, base_favorite),
                "BaseP1Coef": base_p1_coef,
                "BaseP2Coef": base_p2_coef,
                "BaseP1Zone": base_p1_zone,
                "BaseP2Zone": base_p2_zone,
                "PeriodFavoriteSide": period_favorite,
                "PeriodFavoriteName": favorite_name(game, period_favorite),
                "PeriodP1Coef": period_p1_coef,
                "PeriodP2Coef": period_p2_coef,
                "PeriodP1Zone": period_p1_zone,
                "PeriodP2Zone": period_p2_zone,
            })

    fieldnames = [
        "Status", "MainGameId", "GameType", "BaseGameId", "PeriodGameId", "Sport", "Champ",
        "Opp1", "Opp2", "Start", "BasePeriod", "Period", "BaseFavoriteSide", "BaseFavoriteName",
        "BaseP1Coef", "BaseP2Coef", "BaseP1Zone", "BaseP2Zone", "PeriodFavoriteSide",
        "PeriodFavoriteName", "PeriodP1Coef", "PeriodP2Coef", "PeriodP1Zone", "PeriodP2Zone",
    ]

    mismatches = [row for row in rows if row["Status"] == "DIFF"]
    write_csv(output, fieldnames, rows)
    write_csv(mismatches_output, fieldnames, mismatches)

    status_counts = defaultdict(int)
    for row in rows:
        status_counts[row["Status"]] += 1

    return {
        "rows": len(rows),
        "mismatches": len(mismatches),
        "status_counts": dict(sorted(status_counts.items())),
        "skipped_single_period_groups": skipped_single_period,
        "skipped_multi_period_groups_without_period0": skipped_no_period0,
        "skipped_groups_without_clear_base_favorite": skipped_no_base_favorite,
        "output": str(Path(output).resolve()),
        "mismatches_output": str(Path(mismatches_output).resolve()),
    }


def analyze_snapshot(snapshot, output="period_favorite_check.csv", mismatches_output="period_favorite_mismatches.csv"):
    return analyze_games(load_games(snapshot), output=output, mismatches_output=mismatches_output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="line_27.05.2026 current.zip")
    parser.add_argument("--output", default="period_favorite_check.csv")
    parser.add_argument("--mismatches-output", default="period_favorite_mismatches.csv")
    args = parser.parse_args()

    summary = analyze_snapshot(args.snapshot, output=args.output, mismatches_output=args.mismatches_output)

    print(f"Rows: {summary['rows']}")
    print(f"Mismatches: {summary['mismatches']}")
    print(f"Status counts: {summary['status_counts']}")
    print(f"Skipped single-period groups: {summary['skipped_single_period_groups']}")
    print(f"Skipped multi-period groups without period 0: {summary['skipped_multi_period_groups_without_period0']}")
    print(f"Skipped groups without clear base favorite: {summary['skipped_groups_without_clear_base_favorite']}")
    print(f"Saved: {summary['output']}")
    print(f"Saved mismatches: {summary['mismatches_output']}")


if __name__ == "__main__":
    main()
