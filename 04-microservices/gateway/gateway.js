// The API gateway (JavaScript, Node.js without packages): the only entry point of the photo
// service. It checks who calls (authentication), limits the requests of each user, sends each
// request to the correct service (routing), and tries again when a service does not answer.
//
// Its data: the account names of the users (users.csv), for the demo tokens.

import { readFileSync } from "node:fs";
import { createServer } from "node:http";

const backends = {
  photos: "http://photos:8000",
  keywords: "http://keywords-lb:8000", // nginx, in front of the instances
  search: "http://search:8000",
};

// a demo "identity": the token of the user ckaestne is "token-ckaestne"
const tokens = new Map();
const [header, ...rows] = readFileSync("users.csv", "utf8").trim().split("\n");
const columns = header.split(",");
for (const row of rows) {
  const user = Object.fromEntries(row.split(",").map((v, i) => [columns[i], v]));
  tokens.set(`token-${user.account_name}`, Number(user.user_id));
}

class HttpError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

const requestTimes = new Map(); // user -> times of their requests in the last second

function user(request) {
  const token = (request.headers.authorization ?? "").replace(/^Bearer /, "");
  if (!tokens.has(token)) throw new HttpError(401, "unknown token");
  const uid = tokens.get(token);
  const now = performance.now();
  const recent = (requestTimes.get(uid) ?? []).filter((t) => now - t < 1000);
  recent.push(now);
  requestTimes.set(uid, recent);
  if (recent.length > 20) throw new HttpError(429, "too many requests"); // 20 per second
  return uid;
}

async function get(service, path, retries = 1) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    let r;
    try {
      r = await fetch(backends[service] + path, { signal: AbortSignal.timeout(2000) });
    } catch {
      continue; // no answer (network error or timeout): try again
    }
    if (r.status < 400) return r.json();
    if (r.status < 500) {
      // an error of the request: do not try again
      throw new HttpError(r.status, (await r.json()).detail);
    }
  }
  throw new HttpError(503, `${service} is not available`);
}

const routes = [
  [/^\/api\/photos\/(\d+)$/, async (request, [id]) => {
    user(request);
    return get("photos", `/photos/${id}`);
  }],
  [/^\/api\/photos\/(\d+)\/keywords$/, async (request, [id]) => {
    user(request);
    return get("keywords", `/keywords/${id}`);
  }],
  [/^\/api\/search$/, async (request, _, params) => {
    const uid = user(request);
    const q = params.get("q");
    if (!q) throw new HttpError(422, "the parameter q is missing");
    const bundle = params.get("bundle") !== "false";
    const start = performance.now();
    const ids = await get("search", `/search?q=${encodeURIComponent(q)}&user_id=${uid}`);
    let found;
    if (bundle) { // one call for all photos
      found = ids.length ? await get("photos", `/photos?ids=${ids.join(",")}`) : [];
    } else { // one call per photo
      found = [];
      for (const id of ids) found.push(await get("photos", `/photos/${id}`));
    }
    const ms = performance.now() - start;
    const calls = 1 + (bundle ? Math.min(ids.length, 1) : ids.length);
    return { query: q, photos: found, calls, ms };
  }],
];

function send(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

createServer(async (request, response) => {
  const url = new URL(request.url, "http://gateway");
  try {
    for (const [pattern, handler] of routes) {
      const match = url.pathname.match(pattern);
      if (request.method === "GET" && match) {
        return send(response, 200, await handler(request, match.slice(1), url.searchParams));
      }
    }
    throw new HttpError(404, "not found");
  } catch (e) {
    if (!(e instanceof HttpError)) console.error(e);
    send(response, e.status ?? 500, { detail: e.status ? e.message : "internal error" });
  }
}).listen(8000, () => console.log(`gateway: ${tokens.size} users, port 8000`));
