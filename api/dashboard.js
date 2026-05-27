const { handleError, sendJson, supabaseFetch } = require("./_supabase");

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("allow", "GET");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const limit = Math.min(Number.parseInt(req.query.limit || "20", 10) || 20, 100);
    const runs = await supabaseFetch("run_statistics", {
      params: {
        select: "run_id,started_at,finished_at,duration_seconds,mode,changed_games,snapshot_games,total_anomalies,checks_with_anomalies,synced_results,updated_since,max_dd,check_counts_json,status_counts_json,synced_counts_json",
        order: "started_at.desc",
        limit: String(limit)
      }
    });

    const runIds = runs.map(run => run.run_id).filter(Boolean);
    let checks = [];
    if (runIds.length) {
      checks = await supabaseFetch("run_check_statistics", {
        params: {
          select: "run_id,check_name,check_title,rows_count,status_counts_json,synced_rows",
          run_id: `in.(${runIds.map(id => `"${id}"`).join(",")})`,
          order: "run_id.desc,check_name.asc",
          limit: String(limit * 10)
        }
      });
    }

    const checksByRun = {};
    for (const check of checks) {
      if (!checksByRun[check.run_id]) checksByRun[check.run_id] = [];
      checksByRun[check.run_id].push(check);
    }

    sendJson(res, 200, {
      runs,
      checksByRun,
      latest: runs[0] || null
    });
  } catch (error) {
    handleError(res, error);
  }
};
