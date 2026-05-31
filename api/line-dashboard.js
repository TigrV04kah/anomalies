const { handleError, sendJson, supabaseFetch } = require("./_supabase");

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("allow", "GET");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const latestRuns = await supabaseFetch("run_statistics", {
      params: {
        select: "run_id,started_at,snapshot_games",
        order: "started_at.desc",
        limit: "1"
      }
    });
    const latest = latestRuns[0] || null;
    if (!latest?.run_id) {
      sendJson(res, 200, { latest: null, sport: [], subsport: [], hourly: [] });
      return;
    }

    const [sport, subsport, hourly] = await Promise.all([
      supabaseFetch("snapshot_sport_statistics", {
        params: {
          select: "sport,unique_main_games,unique_main_game_types,unique_event_types,games_count,events_count",
          run_id: `eq.${latest.run_id}`,
          order: "unique_main_games.desc"
        }
      }),
      supabaseFetch("snapshot_subsport_statistics", {
        params: {
          select: "subsport,unique_main_games,games_count,events_count",
          run_id: `eq.${latest.run_id}`,
          order: "unique_main_games.desc"
        }
      }),
      supabaseFetch("snapshot_hourly_statistics", {
        params: {
          select: "sport,hour_local,unique_main_games,unique_main_game_types,unique_event_types,games_count,events_count",
          run_id: `eq.${latest.run_id}`,
          order: "sport.asc,hour_local.asc"
        }
      })
    ]);

    sendJson(res, 200, {
      latest,
      sport,
      subsport,
      hourly
    });
  } catch (error) {
    handleError(res, error);
  }
};
