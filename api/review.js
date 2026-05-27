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

    const rows = await supabaseFetch("check_results", {
      method: "PATCH",
      params: { result_key: `eq.${resultKey}` },
      prefer: "return=representation",
      body: {
        verdict,
        review_comment: reviewComment,
        reviewed_by: reviewedBy,
        reviewed_at: new Date().toISOString()
      }
    });

    sendJson(res, 200, { item: rows && rows[0] ? rows[0] : null });
  } catch (error) {
    handleError(res, error);
  }
};
