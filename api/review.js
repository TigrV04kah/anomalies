const { handleError, sendJson, supabaseFetch } = require("./_supabase");

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", chunk => {
      raw += chunk;
      if (raw.length > 1_000_000) {
        reject(new Error("Request body is too large"));
        req.destroy();
      }
    });
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function isMissingCycleTable(error) {
  const message = String(error && error.message || "");
  return (
    message.includes("defect_review_cycles") &&
    (
      message.includes("Could not find") ||
      message.includes("does not exist") ||
      message.includes("schema cache")
    )
  );
}

async function closeOpenReviewCycle(resultKey, verdict, reviewComment, reviewedBy, reviewedAt) {
  try {
    const cycles = await supabaseFetch("defect_review_cycles", {
      params: {
        select: "id,opened_at",
        result_key: `eq.${resultKey}`,
        reviewed_at: "is.null",
        order: "opened_at.desc",
        limit: "1"
      }
    });
    const cycle = cycles && cycles[0];
    if (!cycle) return null;

    const responseSeconds = Math.max(
      0,
      (new Date(reviewedAt).getTime() - new Date(cycle.opened_at).getTime()) / 1000
    );
    const rows = await supabaseFetch("defect_review_cycles", {
      method: "PATCH",
      params: { id: `eq.${cycle.id}` },
      prefer: "return=representation",
      body: {
        verdict,
        review_comment: reviewComment,
        reviewed_by: reviewedBy,
        reviewed_at: reviewedAt,
        response_seconds: responseSeconds,
        updated_at: reviewedAt
      }
    });
    return rows && rows[0] ? rows[0] : null;
  } catch (error) {
    if (isMissingCycleTable(error)) return null;
    throw error;
  }
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST" && req.method !== "PATCH") {
    res.setHeader("allow", "POST, PATCH");
    sendJson(res, 405, { error: "Method not allowed" });
    return;
  }

  try {
    const body = await readBody(req);
    const resultKey = body.result_key;
    const verdict = body.verdict;
    const reviewComment = (body.review_comment || "").trim();
    const reviewedBy = (body.reviewed_by || "").trim() || "web-user";

    if (!resultKey) {
      sendJson(res, 400, { error: "result_key is required" });
      return;
    }
    if (verdict !== "defect" && verdict !== "normal") {
      sendJson(res, 400, { error: "verdict must be defect or normal" });
      return;
    }

    const reviewedAt = new Date().toISOString();
    const rows = await supabaseFetch("check_results", {
      method: "PATCH",
      params: { result_key: `eq.${resultKey}` },
      prefer: "return=representation",
      body: {
        verdict,
        review_comment: reviewComment,
        reviewed_by: reviewedBy,
        reviewed_at: reviewedAt
      }
    });
    const cycle = await closeOpenReviewCycle(resultKey, verdict, reviewComment, reviewedBy, reviewedAt);

    sendJson(res, 200, { item: rows && rows[0] ? rows[0] : null, cycle });
  } catch (error) {
    handleError(res, error);
  }
};
