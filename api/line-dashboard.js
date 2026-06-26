const { handleError, sendJson, supabaseFetch } = require("./_supabase");

function localHour(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Number(new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Minsk",
    hour: "2-digit",
    hour12: false
  }).format(date));
}

function localWeekday(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Minsk",
    weekday: "short"
  }).formatToParts(date);
  const valuePart = parts.find(part => part.type === "weekday")?.value;
  const map = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 };
  return map[valuePart] || null;
}

function averageHourlyByRun(runs, sportRows) {
  const runTime = new Map(runs.map(run => [run.run_id, {
    hour: localHour(run.started_at),
    weekday: localWeekday(run.started_at)
  }]));
  const buckets = new Map();
  for (const row of sportRows) {
    const time = runTime.get(row.run_id);
    if (!time || time.hour === null || time.weekday === null) continue;
    const key = `${row.sport}|${time.weekday}|${time.hour}`;
    if (!buckets.has(key)) {
      buckets.set(key, {
        sport: row.sport,
        weekday_local: time.weekday,
        hour_local: time.hour,
        samples: 0,
        unique_main_games: 0,
        unique_main_game_types: 0,
        unique_event_types: 0,
        games_count: 0,
        events_count: 0
      });
    }
    const bucket = buckets.get(key);
    bucket.samples += 1;
    bucket.unique_main_games += Number(row.unique_main_games) || 0;
    bucket.unique_main_game_types += Number(row.unique_main_game_types) || 0;
    bucket.unique_event_types += Number(row.unique_event_types) || 0;
    bucket.games_count += Number(row.games_count) || 0;
    bucket.events_count += Number(row.events_count) || 0;
  }
  const result = [...buckets.values()].map(row => ({
    sport: row.sport,
    weekday_local: row.weekday_local,
    hour_local: row.hour_local,
    samples: row.samples,
    unique_main_games_avg: row.unique_main_games / row.samples,
    unique_main_game_types_avg: row.unique_main_game_types / row.samples,
    unique_event_types_avg: row.unique_event_types / row.samples,
    games_count_avg: row.games_count / row.samples,
    events_count_avg: row.events_count / row.samples
  }));
  const sportAverages = new Map();
  for (const row of result) {
    const current = sportAverages.get(row.sport) || { sum: 0, count: 0 };
    current.sum += row.unique_main_games_avg;
    current.count += 1;
    sportAverages.set(row.sport, current);
  }
  return result.map(row => {
    const avg = sportAverages.get(row.sport);
    return {
      ...row,
      sport_average_main_games: avg ? avg.sum / avg.count : 0,
      relative_to_sport_average: avg && avg.sum > 0 ? row.unique_main_games_avg / (avg.sum / avg.count) : 0
    };
  }).sort((a, b) => a.sport.localeCompare(b.sport) || a.weekday_local - b.weekday_local || a.hour_local - b.hour_local);
}

function chunks(items, size) {
  const result = [];
  for (let index = 0; index < items.length; index += size) {
    result.push(items.slice(index, index + size));
  }
  return result;
}

async function fetchPaged(table, { params = {}, maxRows = 1000, pageSize = 1000 } = {}) {
  const rows = [];
  while (rows.length < maxRows) {
    const limit = Math.min(pageSize, maxRows - rows.length);
    const page = await supabaseFetch(table, {
      params: {
        ...params,
        limit: String(limit),
        offset: String(rows.length)
      }
    });
    rows.push(...page);
    if (page.length < limit) break;
  }
  return rows;
}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("allow", "GET");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const historyLimit = Math.min(Number.parseInt(req.query.history_limit || "5000", 10) || 5000, 5000);
    const selectedSport = String(req.query.sport || "").trim();
    const runs = await fetchPaged("run_statistics", {
      maxRows: historyLimit,
      params: {
        select: "run_id,started_at,snapshot_games",
        order: "started_at.desc"
      }
    });
    const latest = runs[0] || null;
    if (!latest?.run_id) {
      sendJson(res, 200, { latest: null, sport: [], subsport: [], hourlyAverage: [], historyRuns: 0 });
      return;
    }
    const runIds = runs.map(run => run.run_id).filter(Boolean);

    const [sport, subsport, gameType] = await Promise.all([
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
      supabaseFetch("snapshot_game_type_statistics", {
        params: {
          select: "sport,game_type,unique_main_games,unique_event_types,games_count,events_count",
          run_id: `eq.${latest.run_id}`,
          order: "sport.asc,unique_main_games.desc",
          limit: "5000"
        }
      })
    ]);
    const sportHistory = [];
    if (selectedSport) {
      for (const chunk of chunks(runIds, 100)) {
        const rows = await fetchPaged("snapshot_sport_statistics", {
          maxRows: chunk.length,
          params: {
            select: "run_id,sport,unique_main_games,unique_main_game_types,unique_event_types,games_count,events_count",
            sport: `eq.${selectedSport}`,
            run_id: `in.(${chunk.map(id => `"${id}"`).join(",")})`,
            order: "run_id.asc"
          }
        });
        sportHistory.push(...rows);
      }
    }

    sendJson(res, 200, {
      latest,
      sport,
      subsport,
      gameType,
      hourlyAverage: averageHourlyByRun(runs, sportHistory),
      selectedSport: selectedSport || null,
      historyRuns: runs.length
    });
  } catch (error) {
    handleError(res, error);
  }
};
