import json
from datetime import datetime, timezone


CHECK_TITLES = {
    "period_deviations_average": "Main = Period (average)",
    "total_deviations_average": "Total = Ind total 1 + Ind Total 2 (average)",
    "stat_conflicts": "Stat Conflicts",
    "individual_total_favorite_consistency": "Individual Total Favorite Consistency",
    "football_stat_relations": "Football Stat Relations",
    "basketball_players": "basketball players",
    "basketball_q4_handicap_shift": "Basketball Q4 Handicap Shift",
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
    if check_name == "individual_total_favorite_consistency":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("GameId", "")),
            str(row.get("GameType", "")),
            str(row.get("Scenario", "")),
            str(row.get("FavoriteEventType", "")),
            str(row.get("FavoriteParam", "")),
        ])
    if check_name == "football_stat_relations":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("Rule", "")),
            str(row.get("SourceGameType", "")),
            str(row.get("TargetGameType", "")),
        ])
    if check_name == "basketball_players":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("Rule", "")),
            str(row.get("GameId", "")),
            str(row.get("Period", "")),
            str(row.get("Player", "")),
            str(row.get("EventType", "")),
            str(row.get("Stat", "")),
        ])
    if check_name == "basketball_q4_handicap_shift":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("EventType", "")),
            str(row.get("Scenario", "")),
            str(row.get("Q1Param", "")),
        ])
    if check_name == "tennis_special_what_earlear":
        return "|".join([
            check_name,
            str(row.get("MainGameId", "")),
            str(row.get("Period", "")),
        ])
    return check_name + "|" + json.dumps(row, ensure_ascii=False, sort_keys=True)
