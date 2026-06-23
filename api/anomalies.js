const { handleError, sendJson, supabaseFetch } = require("./_supabase");

const ALLOWED_STATUSES = new Set([
  "DIFF",
  "SOFT",
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
  "MathRobot Individual Total Favorite Consistency",
  "Football Stat Relations",
  "basketball players",
  "Basketball Q4 Handicap Shift",
  "Period Conflicts",
  "Tennis Special. What Earlear",
  "Tenis. Special",
  "Bookmaker Total Disagreement"
];

const INDEPENDENT_CURRENT_CHECK_TITLES = new Set([
  "Bookmaker Total Disagreement"
]);

function normalizeCheckTitles(value) {
  const rawValues = Array.isArray(value) ? value : [value];
  return rawValues
    .flatMap(item => String(item || "").split(","))
    .map(item => item.trim())
    .filter(Boolean);
}

function quotedCheckTitle(title) {
  return `"${String(title).replace(/"/g, '\\"')}"`;
}

function checkTitleFilter(titles) {
  if (titles.length === 1) {
    return `eq.${titles[0]}`;
  }
  return `in.(${titles.map(quotedCheckTitle).join(",")})`;
}

async function latestRunIdForCheckTitle(title, status = "DIFF") {
  const rows = await supabaseFetch("check_results", {
    params: {
      select: "last_run_id",
      check_title: `eq.${title}`,
      status: `eq.${status}`,
      order: "last_seen_at.desc",
      limit: "1"
    }
  });
  return rows[0]?.last_run_id;
}

async function currentRunIdForQuery(selectedCheckTitles, latestRunId, status) {
  if (
    selectedCheckTitles.length === 1 &&
    INDEPENDENT_CURRENT_CHECK_TITLES.has(selectedCheckTitles[0])
  ) {
    return await latestRunIdForCheckTitle(selectedCheckTitles[0], status) || latestRunId;
  }
  return latestRunId;
}

async function fetchCurrentNewCheckStats(latestRunId) {
  const stats = Object.fromEntries(ACTIVE_CHECK_TITLES.map(title => [title, { new: 0 }]));
  stats.all = { new: 0 };
  if (!latestRunId) return stats;

  const params = {
    select: "check_title",
    status: "eq.DIFF",
    verdict: "is.null",
    last_run_id: `eq.${latestRunId}`,
    limit: "10000"
  };

  let rows;
  try {
    rows = await supabaseFetch("check_results", { params });
  } catch (error) {
    const missingCheckTitle = String(error.message || "").includes("check_title");
    if (!missingCheckTitle) throw error;
    rows = await supabaseFetch("check_results", {
      params: {
        ...params,
        select: "check_name"
      }
    });
  }

  for (const row of rows) {
    const title = row.check_title || row.check_name;
    if (!title) continue;
    if (!stats[title]) stats[title] = { new: 0 };
    stats[title].new += 1;
    stats.all.new += 1;
  }

  for (const title of INDEPENDENT_CURRENT_CHECK_TITLES) {
    const checkRunId = await latestRunIdForCheckTitle(title, "DIFF");
    if (!checkRunId) continue;
    const currentCount = stats[title]?.new || 0;
    const checkRows = await supabaseFetch("check_results", {
      params: {
        select: "result_key",
        check_title: `eq.${title}`,
        status: "eq.DIFF",
        verdict: "is.null",
        last_run_id: `eq.${checkRunId}`,
        limit: "10000"
      }
    });
    stats.all.new += checkRows.length - currentCount;
    stats[title] = { new: checkRows.length };
  }
  return stats;
}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("allow", "GET");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const isSoftScope = req.query.scope === "soft";
    const status = isSoftScope
      ? "SOFT"
      : (ALLOWED_STATUSES.has(req.query.status) ? req.query.status : "DIFF");
    const verdict = req.query.verdict || "unreviewed";
    const requestedCheckTitles = normalizeCheckTitles(req.query.check_title);
    const selectedCheckTitles = requestedCheckTitles.length && !requestedCheckTitles.includes("all")
      ? requestedCheckTitles
      : ACTIVE_CHECK_TITLES;
    const hasExplicitCheckFilter = selectedCheckTitles !== ACTIVE_CHECK_TITLES;
    const scope = req.query.scope === "history" || isSoftScope ? "history" : "current";
    const limit = Math.min(Number.parseInt(req.query.limit || "100", 10) || 100, 500);
    const latestRuns = await supabaseFetch("monitor_runs", {
      params: {
        select: "run_id",
        order: "started_at.desc",
        limit: "1"
      }
    });
    const latestRunId = latestRuns[0]?.run_id;
    const currentRunId = scope === "current"
      ? await currentRunIdForQuery(selectedCheckTitles, latestRunId, status)
      : latestRunId;

    const params = {
      select: "result_key,check_name,check_title,status,first_seen_at,last_seen_at,last_run_id,occurrence_count,payload_json,verdict,review_comment,reviewed_by,reviewed_at",
      status: `eq.${status}`,
      order: "last_seen_at.desc",
      limit: String(limit)
    };

    params.check_title = checkTitleFilter(selectedCheckTitles);
    if (scope === "current" && currentRunId) {
      params.last_run_id = `eq.${currentRunId}`;
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
      if (hasExplicitCheckFilter) {
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
    statsBaseParams.check_title = checkTitleFilter(selectedCheckTitles);
    if (scope === "current" && currentRunId) {
      statsBaseParams.last_run_id = `eq.${currentRunId}`;
    }
    let statsRows;
    try {
      statsRows = await supabaseFetch("check_results", { params: statsBaseParams });
    } catch (error) {
      const missingCheckTitle = String(error.message || "").includes("check_title");
      if (!missingCheckTitle) throw error;
      const legacyStatsParams = { ...statsBaseParams };
      delete legacyStatsParams.check_title;
      if (hasExplicitCheckFilter) {
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

    const checkStats = await fetchCurrentNewCheckStats(latestRunId);

    sendJson(res, 200, { items, stats, check_stats: checkStats });
  } catch (error) {
    handleError(res, error);
  }
};
