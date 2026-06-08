const http = require("http");
const fs = require("fs");
const path = require("path");
const root = __dirname;
const port = Number(process.env.PORT || 8766);

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8"
};

function wrap(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  req.query = {};
  for (const [key, value] of url.searchParams.entries()) {
    if (Object.prototype.hasOwnProperty.call(req.query, key)) {
      req.query[key] = Array.isArray(req.query[key])
        ? [...req.query[key], value]
        : [req.query[key], value];
    } else {
      req.query[key] = value;
    }
  }
  return url;
}

function serveFile(res, filePath) {
  fs.readFile(filePath, (error, body) => {
    if (error) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }
    res.setHeader("content-type", types[path.extname(filePath)] || "application/octet-stream");
    res.setHeader("cache-control", "no-store");
    res.end(body);
  });
}

function apiHandler(relativePath) {
  const fullPath = require.resolve(relativePath);
  delete require.cache[fullPath];
  return require(relativePath);
}

const server = http.createServer((req, res) => {
  const url = wrap(req, res);
  if (url.pathname === "/api/anomalies") {
    apiHandler("./api/anomalies")(req, res);
    return;
  }
  if (url.pathname === "/api/review") {
    apiHandler("./api/review")(req, res);
    return;
  }
  if (url.pathname === "/api/dashboard") {
    apiHandler("./api/dashboard")(req, res);
    return;
  }
  if (url.pathname === "/api/line-dashboard") {
    apiHandler("./api/line-dashboard")(req, res);
    return;
  }
  const file = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  serveFile(res, path.join(root, file));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Preview http://127.0.0.1:${port}`);
});
