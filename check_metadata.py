import json
from datetime import datetime, timezone


CHECK_TITLES = {
    "period_deviations_average": "Main = Period (average)",
    "total_deviations_average": "Total = Ind total 1 + Ind Total 2 (average)",
    "stat_conflicts": "Stat Conflicts",
    "period_conflicts": "Period Conflicts",
    "tennis_special_what_earlear": "Tennis Special. What Earlear",
}


def check_title(check_name):
    return CHECK_TITLES.get(check_name, check_name)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def stable_key(check_name, row):
    if check_name == "period_conflicts":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("GameType", "")),
            str(row.get("Period", "")),
        ])
    if check_name == "period_deviations_average":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("GameType", "")),
            str(row.get("EventType", "")),
            str(row.get("Periods", "")),
        ])
    if check_name == "total_deviations_average":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("GameType", "")),
            str(row.get("Period", "")),
            str(row.get("Type", "")),
        ])
    if check_name == "stat_conflicts":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("GameId", "")),
            str(row.get("StatType", "")),
        ])
    if check_name == "tennis_special_what_earlear":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("Period", "")),
        ])
    return check_name + "|" + json.dumps(row, ensure_ascii=False, sort_keys=True)
