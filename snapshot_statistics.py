from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Europe/Minsk")


def parse_start_hour(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).hour


def game_key(game):
    main_game_id = game.get("MainGameId") or game.get("GameId")
    game_type = game.get("GameType")
    return (main_game_id, game_type)


def count_events(game):
    return len(game.get("Events") or [])


def collect_snapshot_statistics(games):
    sport = defaultdict(lambda: {
        "main_games": set(),
        "game_type_keys": set(),
        "event_types": set(),
        "games_count": 0,
        "events_count": 0,
    })
    subsport = defaultdict(lambda: {
        "main_games": set(),
        "games_count": 0,
        "events_count": 0,
    })
    hourly = defaultdict(lambda: {
        "main_games": set(),
        "game_type_keys": set(),
        "event_types": set(),
        "games_count": 0,
        "events_count": 0,
    })

    for game in games:
        main_game_id = game.get("MainGameId") or game.get("GameId")
        if main_game_id is None:
            continue
        sport_name = game.get("SportName") or str(game.get("Sport") or "Unknown")
        subsport_name = game.get("SubSport")
        events = game.get("Events") or []
        events_count = len(events)
        key = game_key(game)
        event_types = {
            event.get("EventType")
            for event in events
            if event.get("EventType") not in (None, "")
        }

        sport_item = sport[sport_name]
        sport_item["main_games"].add(main_game_id)
        sport_item["game_type_keys"].add(key)
        sport_item["event_types"].update(event_types)
        sport_item["games_count"] += 1
        sport_item["events_count"] += events_count

        if subsport_name not in (None, ""):
            subsport_item = subsport[str(subsport_name)]
            subsport_item["main_games"].add(main_game_id)
            subsport_item["games_count"] += 1
            subsport_item["events_count"] += events_count

        hour = parse_start_hour(game.get("Start"))
        if hour is not None:
            hourly_item = hourly[(sport_name, hour)]
            hourly_item["main_games"].add(main_game_id)
            hourly_item["game_type_keys"].add(key)
            hourly_item["event_types"].update(event_types)
            hourly_item["games_count"] += 1
            hourly_item["events_count"] += events_count

    return {
        "sport": sport,
        "subsport": subsport,
        "hourly": hourly,
    }


def build_snapshot_statistics_rows(games, run_id):
    stats = collect_snapshot_statistics(games)

    sport_rows = []
    for sport_name, item in sorted(stats["sport"].items()):
        sport_rows.append({
            "run_id": run_id,
            "sport": sport_name,
            "unique_main_games": len(item["main_games"]),
            "unique_main_game_types": len(item["game_type_keys"]),
            "unique_event_types": len(item["event_types"]),
            "games_count": item["games_count"],
            "events_count": item["events_count"],
        })

    subsport_rows = []
    for subsport_name, item in sorted(stats["subsport"].items()):
        subsport_rows.append({
            "run_id": run_id,
            "subsport": subsport_name,
            "unique_main_games": len(item["main_games"]),
            "games_count": item["games_count"],
            "events_count": item["events_count"],
        })

    hourly_rows = []
    for (sport_name, hour), item in sorted(stats["hourly"].items()):
        hourly_rows.append({
            "run_id": run_id,
            "sport": sport_name,
            "hour_local": hour,
            "unique_main_games": len(item["main_games"]),
            "unique_main_game_types": len(item["game_type_keys"]),
            "unique_event_types": len(item["event_types"]),
            "games_count": item["games_count"],
            "events_count": item["events_count"],
        })

    return {
        "sport": sport_rows,
        "subsport": subsport_rows,
        "hourly": hourly_rows,
    }
