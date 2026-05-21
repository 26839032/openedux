/**
 * Cloudflare Worker:
 *   POST /api/visit → increment counter, append IP / UA / country (KV).
 *   GET  /api/visit/stats → JSON { total, recent } (auth required).
 *   GET  /api/like?article=<slug> → JSON { likes, already_liked }.
 *   POST /api/like → like an article, JSON body { article: "<slug>" }.
 */

const VALID_ARTICLES = new Set([
  "why-i-started-openedux",
  "long-term-ai-conversations",
  "my-ai-assisted-workflow-for-deep-work",
  "why-smart-people-still-feel-overwhelmed",
  "why-you-keep-forgetting-your-new-year-wishes",
]);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    // POST /api/visit — record a page visit
    if (url.pathname === "/api/visit" && request.method === "POST") {
      const ip =
        request.headers.get("CF-Connecting-IP") ||
        request.headers.get("X-Forwarded-For") ||
        "unknown";
      const ua = request.headers.get("User-Agent") || "";
      const country = request.headers.get("CF-IPCountry") || "";

      ctx.waitUntil(recordVisit(env, ip, ua, country));

      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    // GET /api/visit/stats — admin stats (auth required)
    if (url.pathname === "/api/visit/stats" && request.method === "GET") {
      const auth = request.headers.get("Authorization");
      if (!env.ADMIN_TOKEN || auth !== `Bearer ${env.ADMIN_TOKEN}`) {
        return new Response("Unauthorized", { status: 401 });
      }
      const total = parseInt((await env.VISIT_KV.get("total")) || "0", 10);
      const raw = await env.VISIT_KV.get("recent");
      let recent = [];
      try {
        recent = raw ? JSON.parse(raw) : [];
      } catch {
        recent = [];
      }
      return Response.json(
        { total, recent },
        { headers: { ...corsHeaders(request), "Content-Type": "application/json" } }
      );
    }

    // GET /api/like?article=<slug> — get like count and liked status
    if (url.pathname === "/api/like" && request.method === "GET") {
      const article = url.searchParams.get("article");
      if (!article || !VALID_ARTICLES.has(article)) {
        return new Response("Bad Request", { status: 400, headers: corsHeaders(request) });
      }

      const countKey = "likes:" + article;
      const count = parseInt((await env.VISIT_KV.get(countKey)) || "0", 10);

      const fp = await visitorFingerprint(request);
      const likedKey = "liked:" + article;
      const raw = await env.VISIT_KV.get(likedKey);
      let likedSet = [];
      try { likedSet = raw ? JSON.parse(raw) : []; } catch { likedSet = []; }
      const alreadyLiked = likedSet.includes(fp);

      return Response.json(
        { likes: count, already_liked: alreadyLiked },
        { headers: { ...corsHeaders(request), "Content-Type": "application/json" } }
      );
    }

    // POST /api/like — like an article
    if (url.pathname === "/api/like" && request.method === "POST") {
      let body;
      try { body = await request.json(); } catch { body = {}; }
      const article = body?.article;
      if (!article || typeof article !== "string" || !VALID_ARTICLES.has(article)) {
        return new Response("Bad Request", { status: 400, headers: corsHeaders(request) });
      }

      const fp = await visitorFingerprint(request);

      // Rate limit: one POST per visitor per 60s
      const rlKey = "ratelimit:" + fp;
      const rl = await env.VISIT_KV.get(rlKey);
      if (rl) {
        return Response.json(
          { likes: null, error: "rate_limited" },
          { status: 429, headers: { ...corsHeaders(request), "Content-Type": "application/json" } }
        );
      }

      const countKey = "likes:" + article;
      const likedKey = "liked:" + article;

      const raw = await env.VISIT_KV.get(likedKey);
      let likedSet = [];
      try { likedSet = raw ? JSON.parse(raw) : []; } catch { likedSet = []; }

      let alreadyLiked = likedSet.includes(fp);
      let newCount;

      if (!alreadyLiked) {
        likedSet.push(fp);
        newCount = parseInt((await env.VISIT_KV.get(countKey)) || "0", 10) + 1;
        await env.VISIT_KV.put(countKey, String(newCount));
        await env.VISIT_KV.put(likedKey, JSON.stringify(likedSet));
      } else {
        newCount = parseInt((await env.VISIT_KV.get(countKey)) || "0", 10);
      }

      // Set rate limit with 60s TTL
      ctx.waitUntil(env.VISIT_KV.put(rlKey, "1", { expirationTtl: 60 }));

      return Response.json(
        { likes: newCount, already_liked: alreadyLiked },
        { headers: { ...corsHeaders(request), "Content-Type": "application/json" } }
      );
    }

    return new Response("Not Found", { status: 404 });
  },
};

/** @param {Request} request */
function corsHeaders(request) {
  const origin = request.headers.get("Origin");
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

/**
 * @param {{ VISIT_KV: KVNamespace }} env
 * @param {string} ip
 * @param {string} ua
 * @param {string} country
 */
/** Simple SHA-256 fingerprint from IP + UA, returning first 16 hex chars. */
async function visitorFingerprint(request) {
  const ip =
    request.headers.get("CF-Connecting-IP") ||
    request.headers.get("X-Forwarded-For") ||
    "unknown";
  const ua = request.headers.get("User-Agent") || "";
  const encoder = new TextEncoder();
  const data = encoder.encode(ip + ":" + ua);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.slice(0, 8).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function recordVisit(env, ip, ua, country) {
  const totalKey = "total";
  const n = parseInt((await env.VISIT_KV.get(totalKey)) || "0", 10);
  await env.VISIT_KV.put(totalKey, String(n + 1));

  const raw = await env.VISIT_KV.get("recent");
  let recent = [];
  try {
    recent = raw ? JSON.parse(raw) : [];
  } catch {
    recent = [];
  }
  recent.unshift({
    t: Date.now(),
    ip,
    ua: ua.slice(0, 512),
    country,
  });
  if (recent.length > 200) recent = recent.slice(0, 200);
  await env.VISIT_KV.put("recent", JSON.stringify(recent));
}
