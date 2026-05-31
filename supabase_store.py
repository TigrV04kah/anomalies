import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from check_metadata import check_title, stable_key, utc_now


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


def is_configured():
    return bool(env_value("SUPABASE_URL") and supabase_key())


def supabase_key():
    return env_value("SUPABASE_SERVICE_ROLE_KEY") or env_value("SUPABASE_PUBLISHABLE_KEY")


def headers():
    key = supabase_key()
    return {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "prefer": "resolution=merge-duplicates,return=minimal",
    }


def rest_url(table, on_conflict=None):
    base = env_value("SUPABASE_URL").rstrip("/")
    url = f"{base}/rest/v1/{table}"
    if on_conflict:
        url += "?" + urllib.parse.urlencode({"on_conflict": on_conflict})
    return url


def post_json(table, rows, on_conflict):
    if not rows:
        return
    request = urllib.request.Request(
        rest_url(table, on_conflict=on_conflict),
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        headers=headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase {table} upsert failed: HTTP {exc.code}: {body}") from exc


def try_post_json(table, rows, on_conflict):
    try:
        post_json(table, rows, on_conflict)
        return True
    except RuntimeError as exc:
        message = str(exc)
        missing_table = (
            "Could not find the table" in message or
            "relation" in message and "does not exist" in message
        )
        if not missing_table:
            raise
        print(
            f"Warning: Supabase table '{table}' is missing; "
            "run the corresponding supabase_migration_*.sql file to enable this statistic."
        )
        return False


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def load_check_rows(check_name, csv_path, run_id):
    seen_at = utc_now()
    title = check_title(check_name)
    rows = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "result_key": stable_key(check_name, row),
                "check_name": check_name,
                "check_title": title,
                "status": row.get("Status", ""),
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "last_run_id": run_id,
                "occurrence_count": 1,
                "payload_json": row,
            })
    return rows


def build_run_statistics(
    run_id,
    mode,
    changed_games,
    snapshot_games,
    summary,
    synced,
    started_at,
    finished_at,
    duration_seconds,
    updated_since=None,
    max_dd=None,
):
    check_counts = {check_name: data.get("rows", 0) for check_name, data in summary.items()}
    status_counts = {check_name: data.get("status_counts", {}) for check_name, data in summary.items()}
    total_anomalies = sum(check_counts.values())
    checks_with_anomalies = sum(1 for count in check_counts.values() if count)
    run_stats = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 3),
        "mode": mode,
        "changed_games": changed_games,
        "snapshot_games": snapshot_games,
        "total_anomalies": total_anomalies,
        "checks_with_anomalies": checks_with_anomalies,
        "synced_results": sum(synced.values()),
        "updated_since": updated_since,
        "max_dd": max_dd,
        "check_counts_json": check_counts,
        "status_counts_json": status_counts,
        "synced_counts_json": synced,
    }
    check_stats = []
    for check_name, data in summary.items():
        check_stats.append({
            "run_id": run_id,
            "check_name": check_name,
            "check_title": check_title(check_name),
            "rows_count": data.get("rows", 0),
            "status_counts_json": data.get("status_counts", {}),
            "synced_rows": synced.get(check_name, 0),
        })
    return run_stats, check_stats


def sync_run_results(
    run_id,
    mode,
    changed_games,
    snapshot_games,
    summary,
    check_csvs,
    started_at=None,
    finished_at=None,
    duration_seconds=0,
    updated_since=None,
    max_dd=None,
):
    started_at = started_at or utc_now()
    finished_at = finished_at or utc_now()
    run_row = {
        "run_id": run_id,
        "started_at": started_at,
        "mode": mode,
        "changed_games": changed_games,
        "snapshot_games": snapshot_games,
        "summary_json": summary,
    }
    post_json("monitor_runs", [run_row], on_conflict="run_id")

    synced = {}
    for check_name, csv_path in check_csvs.items():
        rows = load_check_rows(check_name, csv_path, run_id)
        for batch in chunks(rows, 500):
            post_json("check_results", batch, on_conflict="result_key")
        synced[check_name] = len(rows)
    run_stats, check_stats = build_run_statistics(
        run_id=run_id,
        mode=mode,
        changed_games=changed_games,
        snapshot_games=snapshot_games,
        summary=summary,
        synced=synced,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        updated_since=updated_since,
        max_dd=max_dd,
    )
    stats_synced = try_post_json("run_statistics", [run_stats], on_conflict="run_id")
    check_stats_synced = True
    for batch in chunks(check_stats, 500):
        check_stats_synced = try_post_json("run_check_statistics", batch, on_conflict="run_id,check_name") and check_stats_synced
    synced["_run_statistics"] = 1 if stats_synced else 0
    synced["_run_check_statistics"] = len(check_stats) if check_stats_synced else 0
    return synced


def sync_snapshot_statistics(rows_by_table):
    table_map = {
        "sport": ("snapshot_sport_statistics", "run_id,sport"),
        "game_type": ("snapshot_game_type_statistics", "run_id,sport,game_type"),
        "subsport": ("snapshot_subsport_statistics", "run_id,subsport"),
        "hourly": ("snapshot_hourly_statistics", "run_id,sport,hour_local"),
    }
    synced = {}
    for key, rows in rows_by_table.items():
        table, conflict = table_map[key]
        count = 0
        for batch in chunks(rows, 500):
            if try_post_json(table, batch, on_conflict=conflict):
                count += len(batch)
        synced[key] = count
    return synced
