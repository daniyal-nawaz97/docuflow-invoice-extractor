/* Clickable demo: answers the app's API calls from saved demo data, in the browser. Version __VERSION__ */
const BASE = "__BASE__";
let MANIFEST = null;
let STATE = {}; // the visitor's changes (e.g. approved documents), kept in this browser only
let stateLoaded = false;
const STATE_URL = BASE + "/__demo_state__";

async function loadState() {
  if (stateLoaded) return;
  stateLoaded = true;
  try { const r = await (await caches.open("demo-state-__VERSION__")).match(STATE_URL); if (r) STATE = await r.json(); } catch {}
}
async function saveState() {
  try { await (await caches.open("demo-state-__VERSION__")).put(STATE_URL, new Response(JSON.stringify(STATE), { headers: { "content-type": "application/json" } })); } catch {}
}

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k.startsWith("demo-state-") && k !== "demo-state-__VERSION__") await caches.delete(k);
  await self.clients.claim();
})()));

async function manifest() {
  if (!MANIFEST) MANIFEST = await (await fetch(BASE + "/demo-data/manifest.json?v=__VERSION__")).json();
  return MANIFEST;
}

function normKey(url) {
  const u = new URL(url);
  const q = [...u.searchParams.entries()].filter(([, v]) => v !== "").sort((a, b) => (a[0] + "=" + a[1] < b[0] + "=" + b[1] ? -1 : 1));
  const path = u.pathname.slice(BASE.length) || "/";
  const qs = q.map(([k, v]) => encodeURIComponent(k).replace(/%20/g, "+") + "=" + encodeURIComponent(v).replace(/%20/g, "+")).join("&");
  return path + (qs ? "?" + qs : "");
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}
const readOnly = (what) => json({ detail: (what || "This") + " works in the live version. This clickable demo uses sample data." }, 403);

async function serve(entry) {
  if (!entry) return null;
  const r = await fetch(BASE + "/demo-data/" + entry.f);
  const headers = { "content-type": entry.t };
  if (entry.d) headers["content-disposition"] = entry.d;
  return new Response(await r.arrayBuffer(), { status: entry.s || 200, headers });
}

async function getJSON(key) {
  const m = await manifest();
  const e = m.get[key];
  if (!e) return null;
  return (await fetch(BASE + "/demo-data/" + e.f)).json();
}

importScripts(BASE + "/sw-hooks.js?v=__VERSION__"); // defines HOOKS = { get(key, ctx), post(method, key, body, ctx) }

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin || !url.pathname.startsWith(BASE + "/api/")) return;
  event.respondWith(handle(event.request));
});

async function handle(req) {
  const m = await manifest();
  await loadState();
  const key = normKey(req.url);
  const ctx = { m, STATE, json, readOnly, serve, getJSON, key, normKey };
  try {
    if (key === "/api/logout") { STATE.out = true; await saveState(); return json({ ok: true }); }
    if (key === "/api/login" || key === "/api/demo-login") { STATE.out = false; await saveState(); return (await serve(m.post["POST /api/demo-login"])) || json({ ok: true }); }
    if (key === "/api/me" && STATE.out) return json({ detail: "Please sign in" }, 401);
    if (req.method === "GET" || req.method === "HEAD") {
      if (self.HOOKS && HOOKS.get) { const r = await HOOKS.get(key, ctx); if (r) return r; }
      const hit = await serve(m.get[key]);
      if (hit) return hit;
      const bare = await serve(m.get[key.split("?")[0]]);
      if (bare) return bare;
      return json({ detail: "This view isn't part of the clickable demo. The live version shows it." }, 404);
    }
    let body = null;
    const ct = req.headers.get("content-type") || "";
    if (ct.includes("json")) { try { body = await req.json(); } catch {} }
    if (self.HOOKS && HOOKS.post) { const r = await HOOKS.post(req.method, key, body, ctx); if (r) { await saveState(); return r; } }
    const saved = await serve(m.post[req.method + " " + key]);
    if (saved) return saved;
    if (ct.includes("multipart")) return readOnly("Uploading your own files");
    return readOnly("Saving changes");
  } catch (e) {
    return json({ detail: "Demo error: " + e.message }, 500);
  }
}
