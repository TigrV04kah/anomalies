const { handleError, sendJson, supabaseFetch } = require("./_supabase");

const ALLOWED_STATUSES = new Set([
  "DIFF",
  "NO_PERIOD_FAVORITE",
  "PERIOD_BOTH_FAVORITE",
  "PERIOD_NO_FAVORITE",
  "SAME"
]);

const ACTIVE_CHECK_TITLES = [
  "Main = Period (average)",
  "Total = Ind total 1 + Ind Total 2 (average)",
  "Stat Conflicts",
  "Individual Total Favorite Consistency",
  "Football Stat Relations",
  "basketball players",
  "Basketball Q4 Handicap Shift",
  "Period Conflicts",
  "Tennis Special. What Earlear"
];

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("allow", "GET");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const status = ALLOWED_STATUSES.has(req.query.status) ? req.query.status : "DIFF";
    const verdict = req.query.verdict || "unreviewed";
    const checkTitle = req.query.check_title || "all";
    const scope = req.query.scope === "history" ? "history" : "current";
    const limit = Math.min(Number.parseInt(req.query.limit || "100", 10) || 100, 500);
    const latestRuns = await supabaseFetch("monitor_runs", {
      params: {
        select: "run_id",
        order: "started_at.desc",
        limit: "1"
      }
    });
    const latestRunId = latestRuns[0]?.run_id;

    const params = {
      select: "result_key,check_name,check_title,status,first_seen_at,last_seen_at,last_run_id,occurrence_count,payload_json,verdict,review_comment,reviewed_by,reviewed_at",
      status: `eq.${status}`,
      order: "last_seen_at.desc",
      limit: String(limit)
    };

    if (checkTitle !== "all") {
      params.check_title = `eq.${checkTitle}`;
    } else {
      params.check_title = `in.(${ACTIVE_CHECK_TITLES.map(title => `"${title}"`).join(",")})`;
    }
    if (scope === "current" && latestRunId) {
      params.last_run_id = `eq.${latestRunId}`;
    }

    if (verdict === "unreviewed") {
      params.verdict = "is.null";
    } else if (verdict === "reviewed") {
      params.verdict = "not.is.null";
    } else if (verdict === "defect" || verdict === "normal") {
      params.verdict = `eq.${verdict}`;
    }

    let items;
    try {
      items = await supabaseFetch("check_results", { params });
    } catch (error) {
      const missingCheckTitle = String(error.message || "").includes("check_title");
      if (!missingCheckTitle) throw error;
      const legacyParams = {
        ...params,
        select: "result_key,check_name,status,first_seen_at,last_seen_at,last_run_id,occurrence_count,payload_json,verdict,review_comment,reviewed_by,reviewed_at"
      };
      delete legacyParams.check_title;
      if (checkTitle !== "all") {
        legacyParams.check_name = "eq.favorite_by_period";
      }
      items = await supabaseFetch("check_results", { params: legacyParams });
      items = items.map(item => ({
        ...item,
        check_title: item.check_name === "favorite_by_period"
          ? "discrepancy between favorites by period"
          : item.check_name
      }));
    }

    const statsBaseParams = {
      select: "verdict",
      status: `eq.${status}`,
      limit: "10000"
    };
    if (checkTitle !== "all") {
      statsBaseParams.check_title = `eq.${checkTitle}`;
    } else {
      statsBaseParams.check_title = `in.(${ACTIVE_CHECK_TITLES.map(title => `"${title}"`).join(",")})`;
    }
    if (scope === "current" && latestRunId) {
      statsBaseParams.last_run_id = `eq.${latestRunId}`;
    }
    let statsRows;
    try {
      statsRows = await supabaseFetch("check_results", { params: statsBaseParams });
    } catch (error) {
      const missingCheckTitle = String(error.message || "").includes("check_title");
      if (!missingCheckTitle) throw error;
      const legacyStatsParams = { ...statsBaseParams };
      delete legacyStatsParams.check_title;
      if (checkTitle !== "all") {
        legacyStatsParams.check_name = "eq.favorite_by_period";
      }
      statsRows = await supabaseFetch("check_results", { params: legacyStatsParams });
    }
    const stats = { new: 0, defect: 0, normal: 0 };
    for (const row of statsRows) {
      if (row.verdict === "defect") stats.defect += 1;
      else if (row.verdict === "normal") stats.normal += 1;
      else stats.new += 1;
    }

    sendJson(res, 200, { items, stats });
  } catch (error) {
    handleError(res, error);
  }
};
