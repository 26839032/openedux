/**
 * Cloudflare Worker: POST /api/visit → increment counter, append IP / UA / country (KV).
 * GET /api/visit/stats with Authorization: Bearer <ADMIN_TOKEN> → JSON { total, recent }.
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

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
