/* DocuFlow clickable demo: replays the sample batch with live progress; review decisions and edits are kept in this browser only. */
const ORIGIN = self.location.origin + BASE;
const qp = (key) => Object.fromEntries(new URL(ORIGIN + key).searchParams);
const PER_DOC_MS = 600;
const ATTENTION = ["needs_review", "failed", "flagged"];

function overlayDoc(d) {
  const o = (STATE.docs || {})[d.id];
  return o ? { ...d, ...o } : d;
}

/* how many of the sample batch's files look "done" since the visitor pressed Try with sample invoices */
function progress(total) {
  if (!STATE.sampleStart) return total;
  return Math.min(total, Math.floor((Date.now() - STATE.sampleStart) / PER_DOC_MS));
}

async function batch(id, ctx) {
  const b = await ctx.getJSON(`/api/batches/${id}`);
  if (!b) return null;
  const sample = (await ctx.getJSON("/api/_demo/sample")).id;
  let docs = b.documents.map(overlayDoc);
  const batchOut = { ...b.batch };
  if (STATE.names?.[id]) batchOut.name = STATE.names[id];
  if (id === sample) {
    const done = progress(docs.length);
    if (STATE.sampleStart) {
      batchOut.created_at = new Date(STATE.sampleStart).toISOString();
      if ("finished_at" in batchOut) batchOut.finished_at = done < docs.length ? null : new Date(STATE.sampleStart + docs.length * PER_DOC_MS).toISOString();
    }
    docs = docs.map((d, i) => (i < done ? d : { ...d, status: i === done ? "processing" : "queued", stage: i === done ? "reading" : null, vendor: null, total: null }));
    if (done < docs.length) batchOut.status = "processing";
  }
  const finished = docs.filter((d) => !["queued", "processing"].includes(d.status));
  const stats = { ...b.stats, processed: finished.length, attention: docs.filter((d) => ATTENTION.includes(d.status)).length,
    approved: docs.filter((d) => d.status === "approved").length };
  if (finished.length < docs.length) {
    const f = finished.length / docs.length;
    Object.assign(stats, { fields: Math.round(b.stats.fields * f), processing_seconds: +(finished.length * PER_DOC_MS / 1000).toFixed(1) });
  }
  return { ...b, batch: batchOut, documents: docs, stats };
}

async function documentOut(id, ctx) {
  const d = await ctx.getJSON(`/api/documents/${id}`);
  if (!d) return null;
  const o = (STATE.docs || {})[id] || {};
  return { ...d, ...o, fields: { ...d.fields, ...(o.fields || {}) }, siblings: d.siblings.map(overlayDoc).map(({ id, status }) => ({ id, status })),
    batch_name: STATE.names?.[d.batch_id] || d.batch_name };
}

self.HOOKS = {
  async get(key, ctx) {
    const path = key.split("?")[0];
    let m;
    if (path === "/api/batches") {
      const q = qp(key);
      let list = await ctx.getJSON("/api/batches");
      list = await Promise.all(list.map(async (x) => {
        const b = await batch(x.id, ctx);
        const att = b.documents.filter((d) => ATTENTION.includes(d.status)).length;
        return { ...x, name: b.batch.name, created_at: b.batch.created_at, attention: att, status: b.batch.status === "processing" ? "processing" : att ? "needs_review" : "done", _b: b };
      }));
      list = list.filter((x) => !(STATE.deleted || {})[x.id]);
      if (q.date_from) list = list.filter((x) => x.created_at.slice(0, 10) >= q.date_from);
      if (q.date_to) list = list.filter((x) => x.created_at.slice(0, 10) <= q.date_to);
      if (q.status) list = list.filter((x) => x.status === q.status);
      if (q.q) {
        const ql = q.q.toLowerCase();
        list = list.filter((x) => [x.name, ...x._b.documents.flatMap((d) => [d.vendor || "", d.filename, String(d.invoice_no || "")])].join(" ").toLowerCase().includes(ql));
      }
      return ctx.json(list.map(({ _b, ...x }) => x));
    }
    if ((m = /^\/api\/batches\/([^/]+)$/.exec(path))) { const b = await batch(m[1], ctx); return b ? ctx.json(b) : null; }
    if ((m = /^\/api\/documents\/([^/]+)$/.exec(path))) { const d = await documentOut(m[1], ctx); return d ? ctx.json(d) : null; }
    if (path === "/api/settings" && STATE.settings) return ctx.json({ ...(await ctx.getJSON("/api/settings")), ...STATE.settings });
    return null;
  },
  async post(method, key, body, ctx) {
    const path = key.split("?")[0];
    let m;
    if (path === "/api/batches/sample") {
      const id = (await ctx.getJSON("/api/_demo/sample")).id;
      STATE.sampleStart = Date.now();
      // a fresh run: earlier review decisions on the sample batch start over
      const b = await ctx.getJSON(`/api/batches/${id}`);
      b.documents.forEach((d) => { if (STATE.docs) delete STATE.docs[d.id]; });
      return ctx.json({ id });
    }
    if ((m = /^\/api\/batches\/([^/]+)$/.exec(path))) {
      if (method === "PATCH") { (STATE.names ||= {})[m[1]] = (body?.name || "").trim().slice(0, 120) || "Untitled batch"; return ctx.json({ ok: true }); }
      if (method === "DELETE") {
        if (m[1] === (await ctx.getJSON("/api/_demo/sample")).id) return ctx.json({ detail: "The sample batch is kept for demos" }, 400);
        (STATE.deleted ||= {})[m[1]] = 1; return ctx.json({ ok: true });
      }
    }
    if ((m = /^\/api\/documents\/([^/]+)$/.exec(path)) && method === "PATCH") {
      const id = m[1];
      const orig = await ctx.getJSON(`/api/documents/${id}`);
      const o = ((STATE.docs ||= {})[id] ||= {});
      if (body?.fields) o.fields = { ...(o.fields || {}), ...body.fields };
      if (body?.items) o.items = body.items;
      if (body?.action) {
        const next = { approve: "approved", skip: "skipped", flag: "flagged", reopen: orig.status }[body.action];
        if (!next) return ctx.json({ detail: "Unknown action" }, 400);
        o.status = next;
        const me = await ctx.getJSON("/api/me");
        o.reviewed_by = body.action === "reopen" ? null : me?.name || "Demo user";
      }
      return ctx.json(await documentOut(id, ctx));
    }
    if (path === "/api/settings" && method === "PUT") {
      STATE.settings = { ...(STATE.settings || {}), ...(body || {}) };
      return ctx.json({ ...(await ctx.getJSON("/api/settings")), ...STATE.settings });
    }
    if (/^\/api\/team\/\d+$/.test(path) && method === "PATCH") return ctx.json({ ok: true });
    if (path.startsWith("/api/presets")) return ctx.readOnly("Saving templates");
    return null;
  },
};
