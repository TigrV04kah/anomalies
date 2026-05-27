import argparse
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient


DEFAULT_MONGO_URI = None


def env_value(name):
    value = os.environ.get(name)
    if value:
        return value
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


GAME_TYPE_NAMES = {
    0: "Undefined",
    1: "Main",
    2: "Corners",
    3: "Double",
    4: "Ace",
    6: "Removal",
    7: "PenaltyTime",
    8: "Yellow",
    10: "Cards",
    11: "Miss",
    12: "ShotsOnTarget",
    13: "Offsides",
    14: "Fouls",
    15: "ThrowsOnGoal",
    16: "DopBets",
    17: "Serie",
    18: "ScoredFreeThrows",
    19: "ScoredTwopointShots",
    20: "ScoredThreepointShots",
    21: "Rebounds",
    22: "Pass",
    23: "Losses",
    24: "BlockedShots",
    26: "DoubleFault",
    27: "Crossbar",
    28: "Breaks",
    29: "PossessionPercentage",
    30: "Changes",
    31: "FirstGame",
    32: "SecondGame",
    33: "Bullits",
    34: "Hits",
    35: "Steals",
    36: "DefensiveRebounds",
    37: "OffensiveRebounds",
    38: "ExtraBullets",
    39: "BestOfSets",
    40: "AltIshod",
    41: "ExpressIshod",
    42: "CardsStatistik",
    43: "FastEvent",
    44: "PenaltyLoop",
    45: "SpecialBets",
    46: "TwelveMeterHit",
    47: "BlockShotsHockey",
    48: "Checking",
    49: "Icing",
    50: "WinFaceOffs",
    51: "TestSeries",
    52: "GoalPlayers",
    53: "GoalFromGates",
    54: "GameTime",
    55: "StuffingOuts",
    56: "SecondChancePoints",
    57: "InFastBreakPoints",
    58: "Points3SecondZone",
    59: "Mileage",
    60: "OneMinutesEvents",
    61: "NineInnings",
    62: "Save",
    63: "StatTeamAttack",
    64: "Statistika",
    65: "Morning",
    66: "Afternoon",
    67: "ThatEarlier",
    68: "TwoMinuteSuspension",
    69: "Knockdown",
    70: "AltExpress",
    71: "ResultAndTotal",
    72: "ShootingTime",
    73: "FirstSession",
    74: "SecondSession",
    75: "ThrowOnGoal",
    76: "ErrorsOnFiling",
    77: "Block",
    78: "PercentageOfFeed",
    79: "TakeOff",
    80: "ScoreReboundsTransfer",
    81: "Points",
    82: "AccentStrikes",
    83: "RefereeScoreCards",
    84: "FirstGeim",
    85: "GoalsInMost",
    86: "StatGoal",
    87: "StatCorner",
    88: "StatYellowCard",
    89: "StatFouls",
    90: "StatOffside",
    91: "StatShotsOnTarget",
    92: "BreakPoint",
    93: "StatShot",
    94: "StatChanges",
    95: "ShotByGates",
    96: "ClearencesAttemted",
    97: "ClearencesComleted",
    98: "TacklesNotGainingBall",
    99: "TacklesGainingBall",
    100: "DeliverySoloRunsPenaltyArea",
    101: "DeliverySoloRunsAttackingThird",
    102: "Tackles",
    103: "GoalkeeperTouches",
    104: "DeliveryAttackingThird",
    105: "SoloRunsAttackingThird",
    106: "DeliveryPenaltyArea",
    107: "SoloRunsPenaltyArea",
    108: "DuelRefereeingBrigades",
    109: "DuelPlayersGoals",
    110: "Dribbling",
    111: "AirCombat",
    112: "ExpectedGoals",
    113: "FirstMiniSession",
    114: "SecondMiniSession",
    115: "ThirdMiniSession",
    116: "FourthMiniSession",
    117: "FifthMiniSession",
    118: "SixthMiniSession",
    119: "SeventhMiniSession",
    120: "EighthMiniSession",
    121: "PlayingCards",
    122: "AttendanceMatch",
    123: "Interceptions",
    124: "VideoAssistantReferee",
    125: "DuelPlayersGoalPass",
    126: "SevenMeterThrows",
    127: "PlayerComparison",
    128: "UnforcedErrors",
    129: "DuelPlayersYellowCard",
    130: "MiniSet",
    131: "RaidPoints",
    132: "TacklePoints",
    133: "DuelPlayersOffside",
    134: "DuelPlayersAssists",
    135: "MedicalTeam",
    136: "DuelPlayersShotsOnTarget",
    137: "DuelPlayersFouls",
    138: "FirstGameGoalPlayers",
    139: "SecondGameGoalPlayers",
    140: "NRNB",
    141: "PunchesThrown",
    142: "PunchesLanded",
    100500: "Unknown",
}


def as_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def iso_z(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_reference_maps(snapshot_zip):
    refs = {
        "sports": {},
        "events": {},
        "contoras": {},
    }
    if not snapshot_zip:
        return refs

    with zipfile.ZipFile(snapshot_zip) as archive:
        json_name = next(name for name in archive.namelist() if name.lower().endswith(".json"))
        with archive.open(json_name) as f:
            games = json.load(f)

    for game in games:
        sport = game.get("Sport")
        if sport is not None and game.get("SportName"):
            refs["sports"][sport] = game["SportName"]

        for event in game.get("Events") or []:
            event_id = event.get("EventId")
            if event_id is not None:
                refs["events"][event_id] = {
                    "EventType": event.get("EventType"),
                    "GroupId": event.get("GroupId"),
                    "GroupName": event.get("GroupName"),
                }

            contora = event.get("Contora")
            if contora is not None and event.get("ContoraName"):
                refs["contoras"][contora] = event["ContoraName"]

    return refs


def load_reference_json(path):
    if not path:
        return None
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "sports": {int(k): v for k, v in data.get("sports", {}).items()},
        "events": {int(k): v for k, v in data.get("events", {}).items()},
        "contoras": {int(k): v for k, v in data.get("contoras", {}).items()},
    }


def save_reference_json(refs, path):
    data = {
        "sports": {str(k): v for k, v in sorted(refs["sports"].items())},
        "events": {str(k): v for k, v in sorted(refs["events"].items())},
        "contoras": {str(k): v for k, v in sorted(refs["contoras"].items())},
    }
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def type_name(value):
    return GAME_TYPE_NAMES.get(value, value)


def convert_event(event, refs):
    event_id = event.get("T")
    event_ref = refs["events"].get(event_id, {})
    contora = event.get("Cn")

    return {
        "EventId": event_id,
        "EventType": event_ref.get("EventType"),
        "Param": as_float(event.get("P")),
        "Player": event.get("N"),
        "Coef": as_float(event.get("C")),
        "CoefOrig": as_float(event.get("OC")),
        "Contora": contora,
        "GroupId": event_ref.get("GroupId"),
        "GroupName": event_ref.get("GroupName"),
        "ContoraName": refs["contoras"].get(contora),
    }


def convert_game(doc, refs):
    sport = doc.get("S")
    return {
        "Events": [convert_event(event, refs) for event in (doc.get("E") or [])],
        "GameId": doc.get("I"),
        "MainGameId": doc.get("MI"),
        "ConstId": doc.get("K"),
        "ChampId": doc.get("CI"),
        "Sport": sport,
        "SportName": refs["sports"].get(sport),
        "Champ": doc.get("C"),
        "Opp1": doc.get("H"),
        "Opp2": doc.get("A"),
        "Start": iso_z(doc.get("St")),
        "GameType": type_name(doc.get("T")),
        "GameVid": type_name(doc.get("V")),
        "Period": doc.get("Pr"),
        "MaxBet": doc.get("MB"),
        "RiskGroup": doc.get("R"),
        "ChampRiskGroup": doc.get("CR"),
    }


def build_query(args):
    query = {}
    if args.updated_since:
        query["DD"] = {"$gte": datetime.fromisoformat(args.updated_since.replace("Z", "+00:00"))}
    if args.sport is not None:
        query["S"] = args.sport
    return query


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="Output zip path")
    parser.add_argument("--reference-zip", default=None, help="Old line snapshot zip for names")
    parser.add_argument("--reference-json", default="line_reference_maps.json", help="Saved reference maps JSON")
    parser.add_argument("--save-reference-only", action="store_true", help="Only save reference JSON and exit")
    parser.add_argument("--updated-since", default=None, help="Only Mongo DD >= this ISO datetime")
    parser.add_argument("--sport", type=int, default=None, help="Only one sport id, for example 1")
    parser.add_argument("--limit", type=int, default=0, help="Debug limit")
    args = parser.parse_args()

    refs = load_reference_json(args.reference_json) if Path(args.reference_json).exists() else None
    if refs is None:
        refs = load_reference_maps(args.reference_zip)
        if args.reference_json:
            save_reference_json(refs, args.reference_json)
            print(f"Saved reference maps: {Path(args.reference_json).resolve()}")

    if args.save_reference_only:
        return
    uri = env_value("LINE_MONGO_URI") or DEFAULT_MONGO_URI
    if not uri:
        raise RuntimeError("LINE_MONGO_URI environment variable is required")
    collection = MongoClient(uri)["Line"]["LineGame"]

    query = build_query(args)
    cursor = collection.find(query, no_cursor_timeout=True).batch_size(1000)
    if args.limit:
        cursor = cursor.limit(args.limit)

    games = []
    try:
        for doc in cursor:
            games.append(convert_game(doc, refs))
    finally:
        cursor.close()

    timestamp = datetime.now().strftime("%d.%m.%Y %H-%M")
    output = Path(args.output or f"line_{timestamp}.zip")
    json_name = output.with_suffix(".json").name

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(json_name, json.dumps(games, ensure_ascii=False, separators=(",", ":")))

    print(f"Saved {output.resolve()}")
    print(f"Games: {len(games)}")
    print(f"Reference maps: sports={len(refs['sports'])}, events={len(refs['events'])}, contoras={len(refs['contoras'])}")


if __name__ == "__main__":
    main()
