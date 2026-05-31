import argparse
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import MongoClient

from analyze_line_rules import analyze_all_checks
from export_line_snapshot import DEFAULT_MONGO_URI, convert_game, env_value, load_reference_json
from snapshot_statistics import build_snapshot_statistics_rows
from supabase_store import is_configured as supabase_is_configured
from supabase_store import sync_run_results as sync_supabase_run_results
from supabase_store import sync_snapshot_statistics


DEFAULT_STATE_PATH = Path("linegame_state.json")
DEFAULT_REFERENCE_PATH = Path("line_reference_maps.json")
DEFAULT_SNAPSHOT_PATH = Path("snapshots/current_line_snapshot.zip")
DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_OVERLAP_MINUTES = 1


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_state(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_snapshot(path):
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as archive:
        json_name = next(name for name in archive.namelist() if name.lower().endswith(".json"))
        with archive.open(json_name) as f:
            return json.load(f)


def save_snapshot(path, games):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    json_name = path.with_suffix(".json").name
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(json_name, json.dumps(games, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp_path, path)


def build_query(state, snapshot_exists, overlap, incremental=False):
    if not incremental:
        return {}, "full", None
    last_dd = parse_dt(state.get("last_dd"))
    if not last_dd or not snapshot_exists:
        return {}, "full", None
    updated_since = last_dd - overlap
    return {"DD": {"$gte": updated_since}}, "incremental", updated_since


def fetch_changed_games(query, refs, limit=0):
    uri = env_value("LINE_MONGO_URI") or DEFAULT_MONGO_URI
    if not uri:
        raise RuntimeError("LINE_MONGO_URI environment variable is required")
    collection = MongoClient(uri)["Line"]["LineGame"]
    cursor = collection.find(query, no_cursor_timeout=True).batch_size(1000)
    if limit:
        cursor = cursor.limit(limit)

    games = []
    max_dd = None
    try:
        for doc in cursor:
            dd = doc.get("DD")
            if dd is not None and (max_dd is None or dd > max_dd):
                max_dd = dd
            games.append(convert_game(doc, refs))
    finally:
        cursor.close()
    return games, max_dd


def merge_games(existing_games, changed_games):
    by_game_id = {game.get("GameId"): game for game in existing_games if game.get("GameId") is not None}
    for game in changed_games:
        game_id = game.get("GameId")
        if game_id is not None:
            by_game_id[game_id] = game
    return sorted(by_game_id.values(), key=lambda game: (game.get("MainGameId") or 0, str(game.get("GameType")), game.get("Period") or 0, game.get("GameId") or 0))


def run(args):
    run_started_at = datetime.now(timezone.utc)
    run_id = run_started_at.strftime("%Y%m%dT%H%M%S%fZ")
    state_path = Path(args.state)
    snapshot_path = Path(args.snapshot)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    refs = load_reference_json(args.reference_json)
    state = load_state(state_path)
    snapshot_exists = snapshot_path.exists()
    overlap = timedelta(minutes=args.overlap_minutes)
    query, mode, updated_since = build_query(state, snapshot_exists, overlap, incremental=args.incremental)

    print(f"Mode: {mode}")
    if updated_since:
        print(f"Mongo query: DD >= {updated_since.isoformat()}")
    else:
        print("Mongo query: full LineGame")

    changed_games, max_dd = fetch_changed_games(query, refs, limit=args.limit)
    print(f"Fetched changed games: {len(changed_games)}")

    if mode == "full":
        current_games = changed_games
    else:
        current_games = merge_games(load_snapshot(snapshot_path), changed_games)

    if not current_games:
        raise RuntimeError("No games available after fetch/merge; snapshot was not written")

    save_snapshot(snapshot_path, current_games)
    print(f"Saved snapshot: {snapshot_path.resolve()}")
    print(f"Current snapshot games: {len(current_games)}")

    check_summaries, check_csvs = analyze_all_checks(snapshot_path, reports_dir)
    for check_name, check_summary in check_summaries.items():
        print(f"{check_name}: rows={check_summary['rows']} statuses={check_summary['status_counts']}")

    if not supabase_is_configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_PUBLISHABLE_KEY "
            "must be set to save check results"
        )
    run_finished_at = datetime.now(timezone.utc)
    synced_results = sync_supabase_run_results(
        run_id=run_id,
        mode=mode,
        changed_games=len(changed_games),
        snapshot_games=len(current_games),
        summary=check_summaries,
        check_csvs=check_csvs,
        started_at=run_started_at.isoformat(),
        finished_at=run_finished_at.isoformat(),
        duration_seconds=(run_finished_at - run_started_at).total_seconds(),
        updated_since=updated_since.isoformat() if updated_since else None,
        max_dd=max_dd.replace(tzinfo=timezone.utc).isoformat() if max_dd else None,
    )
    print(f"Synced Supabase rows: {synced_results}")
    snapshot_stats = build_snapshot_statistics_rows(current_games, run_id)
    synced_snapshot_stats = sync_snapshot_statistics(snapshot_stats)
    print(f"Synced snapshot statistics: {synced_snapshot_stats}")

    if max_dd is not None:
        state["last_dd"] = max_dd.replace(tzinfo=timezone.utc).isoformat()
        state["last_success_at"] = datetime.now(timezone.utc).isoformat()
        state["snapshot"] = str(snapshot_path)
        state["last_run_id"] = run_id
        state["last_results_sink"] = "supabase"
        state["last_mode"] = mode
        state["last_changed_games"] = len(changed_games)
        save_state(state_path, state)
        print(f"Updated state: {state_path.resolve()}")
        print(f"last_dd={state['last_dd']}")
    else:
        print("State not updated: no changed documents with DD")

    return {
        "mode": mode,
        "changed_games": len(changed_games),
        "snapshot_games": len(current_games),
        "run_id": run_id,
        "check_summaries": check_summaries,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--reference-json", default=str(DEFAULT_REFERENCE_PATH))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT_PATH))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--overlap-minutes", type=int, default=DEFAULT_OVERLAP_MINUTES)
    parser.add_argument("--incremental", action="store_true", help="Debug mode: fetch only games updated since the previous run")
    parser.add_argument("--force-full", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=0, help="Debug limit for Mongo query")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
