/* DocuFlow front-end: login, upload, processing, review, summary, history, templates, settings. */
const App = { user: null, info: null, presets: null };

/* ---------- language (English first, Urdu labels optional) ---------- */
const T = {
  en: { home: "Home", history: "History", templates: "Templates", settings: "Settings", signout: "Sign out",
        headline: "Turn your invoices into Excel", sub: "Upload invoices, bills, receipts or forms. Get a clean spreadsheet in minutes, no typing.",
        drop: "Drag and drop invoices here", choose: "Choose files", photo: "Take a photo", start: "Start processing",
        recent: "Recent batches", review: "Review", approve: "Approve", skip: "Skip", flag: "Flag", language: "اردو" },
  ur: { home: "ہوم", history: "ہسٹری", templates: "ٹیمپلیٹس", settings: "سیٹنگز", signout: "سائن آؤٹ",
        headline: "اپنی انوائسز کو ایکسل میں بدلیں", sub: "انوائسز، بل، رسیدیں یا فارم اپ لوڈ کریں۔ چند منٹ میں صاف ستھری شیٹ، بغیر ٹائپنگ کے۔",
        drop: "انوائسز یہاں ڈریگ کر کے چھوڑیں", choose: "فائلیں منتخب کریں", photo: "تصویر لیں", start: "پروسیسنگ شروع کریں",
        recent: "حالیہ بیچ", review: "جائزہ", approve: "منظور", skip: "چھوڑیں", flag: "نشان لگائیں", language: "English" },
};
let LANG = localStorage.getItem("df_lang") || "en";
const t = (k) => `<span class="i18n">${esc((T[LANG] || T.en)[k] || T.en[k] || k)}</span>`;
const tt = (k) => (T[LANG] || T.en)[k] || T.en[k] || k;

const DOC_STATUS = {
  queued: ["neutral", "Waiting"], processing: ["info pulse", "Processing"], done: ["ok", "Ready"],
  needs_review: ["warn", "Needs review"], approved: ["ok", "Approved"], skipped: ["neutral", "Skipped"],
  flagged: ["err", "Flagged"], failed: ["err", "Couldn't read"],
};
const BATCH_STATUS = { processing: ["info pulse", "Processing"], needs_review: ["warn", "Needs review"], done: ["ok", "Done"], queued: ["info pulse", "Processing"] };
const badge = (map, s) => { const [c, l] = map[s] || ["neutral", s]; return `<span class="badge ${c}">${esc(l)}</span>`; };
const ATTENTION = ["needs_review", "failed", "flagged"];

/* ---------- shell ---------- */
function brandHTML() {
  const i = App.info || {};
  const name = i.company_name || "DocuFlow";
  return `<a class="brand" href="#/">${i.logo_url ? `<img src="${esc(i.logo_url)}" alt="${esc(name)} logo">` : `<span class="brand-mark">${esc(name[0] || "D")}</span>`}<span>${esc(name)}</span></a>`;
}

function shell(active, html, { wide = false } = {}) {
  const nav = [["home", "#/", "home"], ["history", "#/history", "history"], ["templates", "#/templates", "layers"], ["settings", "#/settings", "settings"]];
  const isDemo = App.user?.email === "demo@docuflow.app";
  $("#app").innerHTML = `
    ${isDemo ? `<div class="demo-banner">You're using the demo account. All sample invoices are fictitious and clearly labelled as samples.</div>` : ""}
    <header class="topbar">
      ${brandHTML()}
      <nav class="nav" aria-label="Main">${nav.map(([k, href, ic]) => `<a href="${href}" class="${active === k ? "active" : ""}">${icon(ic)}${t(k)}</a>`).join("")}</nav>
      <div class="spacer"></div>
      <div class="profile">
        <button class="avatar" id="avatarBtn" aria-label="Profile menu">${esc(initials(App.user?.name))}</button>
        <div class="menu hidden" id="profileMenu">
          <div class="menu-head"><div style="font-weight:600">${esc(App.user?.name)}</div><div class="muted small">${esc(App.user?.email)}</div>
            <div class="tiny muted" style="margin-top:2px;text-transform:capitalize">${esc(App.user?.role)}</div></div>
          <button id="langBtn">${icon("globe")} ${esc(tt("language"))}</button>
          <a href="/privacy" target="_blank">${icon("shield")} Privacy statement</a>
          <button id="logoutBtn">${icon("logout")} ${t("signout")}</button>
        </div>
      </div>
    </header>
    <main class="page ${wide ? "wide" : ""}" id="main">${html}</main>
    <nav class="bottom-nav" aria-label="Main">${nav.map(([k, href, ic]) => `<a href="${href}" class="${active === k ? "active" : ""}">${icon(ic)}${t(k)}</a>`).join("")}</nav>`;
  document.body.classList.toggle("lang-ur", LANG === "ur");
  document.body.style.setProperty("--banner-h", isDemo ? "32px" : "0px");
  $("#avatarBtn").onclick = (e) => { e.stopPropagation(); $("#profileMenu").classList.toggle("hidden"); };
  document.addEventListener("click", () => $("#profileMenu")?.classList.add("hidden"), { once: true });
  $("#logoutBtn").onclick = async () => { await api("/api/logout", { method: "POST" }); App.user = null; location.hash = "#/login"; };
  $("#langBtn").onclick = () => { LANG = LANG === "en" ? "ur" : "en"; localStorage.setItem("df_lang", LANG); Router.go(); };
  return $("#main");
}

async function ensureUser() {
  if (!App.info) App.info = await api("/api/app-info");
  setAccent(App.info.accent_color);
  if (!App.user) App.user = await api("/api/me");
  if (!App.settingsCache) App.settingsCache = await api("/api/settings");
  return App.user;
}

const tip = (text) => `<div class="tip">${icon("lightbulb")}<span>${text}</span></div>`;

/* ---------- screen 1: login ---------- */
Router.add("/login", async () => {
  if (!App.info) App.info = await api("/api/app-info");
  setAccent(App.info.accent_color);
  $("#app").innerHTML = `
    <div class="auth-wrap"><div class="card auth-card">
      ${brandHTML()}
      <h1>Welcome back</h1>
      <p class="lead">Sign in to turn invoices into Excel.</p>
      <form id="loginForm" class="stack" novalidate>
        <label class="field">Email<input class="input" type="email" name="email" autocomplete="username" required placeholder="you@company.com"></label>
        <label class="field">Password<input class="input" type="password" name="password" autocomplete="current-password" required placeholder="••••••••"></label>
        <div id="loginErr" class="alert err hidden" role="alert"></div>
        <button class="btn btn-primary btn-lg btn-block" type="submit">Sign in</button>
      </form>
      <div class="divider">or</div>
      <button class="btn btn-block btn-lg" id="demoBtn">${icon("sparkles")} Try with sample invoices</button>
      <p class="tiny muted" style="text-align:center;margin-top:10px">No sign-up needed. Opens a demo account with fictitious sample invoices.</p>
      <div class="privacy-line">${icon("lock")}<span>Your files are private and deleted after processing. <a href="/privacy" target="_blank">Privacy</a></span></div>
    </div></div>`;
  $("#loginForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = $("button[type=submit]", e.target);
    btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Signing in…`;
    try {
      await api("/api/login", { method: "POST", body: { email: f.get("email"), password: f.get("password") } });
      App.user = null;
      location.hash = sessionStorage.getItem("afterLogin") || "#/";
      sessionStorage.removeItem("afterLogin");
    } catch (err) {
      $("#loginErr").textContent = err.message; $("#loginErr").classList.remove("hidden");
      btn.disabled = false; btn.textContent = "Sign in";
    }
  };
  $("#demoBtn").onclick = async () => {
    $("#demoBtn").disabled = true; $("#demoBtn").innerHTML = `<span class="spinner"></span> Opening demo…`;
    const r = await api("/api/demo-login", { method: "POST" });
    App.user = null;
    location.hash = r.sample_batch ? `#/batch/${r.sample_batch}` : "#/";
  };
});

/* ---------- screen 2: home / upload ---------- */
Router.add("/", async () => {
  await ensureUser();
  const [batches, presets] = await Promise.all([api("/api/batches"), api("/api/presets")]);
  App.presets = presets;
  const settings = App.info;
  const main = shell("home", `
    <div class="page-head"><div><h1>${t("headline")}</h1><p>${t("sub")}</p></div></div>
    <div class="card card-pad">
      <div class="dropzone" id="dz" tabindex="0" role="button" aria-label="Upload files">
        <div class="dz-icon">${icon("upload")}</div>
        <h3>${t("drop")}</h3>
        <p>PDF, JPG, PNG or a ZIP folder &nbsp;·&nbsp; up to ${settings.max_files} files at once</p>
        <div class="dz-actions">
          <button class="btn btn-primary" id="chooseBtn" type="button">${icon("files")} ${t("choose")}</button>
          <button class="btn" id="photoBtn" type="button">${icon("camera")} ${t("photo")}</button>
        </div>
        <input type="file" id="fileInput" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.zip,image/*,application/pdf" hidden>
        <input type="file" id="camInput" accept="image/*" capture="environment" hidden>
        <p class="small" style="margin:16px 0 0">New here? <a href="#" id="sampleLink">Use sample files</a> to see how it works in one click.</p>
      </div>
      <div id="picked" class="picked hidden"></div>
      <div class="options">
        <div><div class="opt-label">Document type</div><div class="chips" id="docType">
          ${Object.entries(presets.doc_types).map(([k, v], i) => `<button class="chip ${i === 0 ? "active" : ""}" data-v="${k}" type="button">${esc(v)}</button>`).join("")}</div></div>
        <div><div class="opt-label">Output format</div><div class="chips" id="outFmt">
          <button class="chip active" data-v="xlsx" type="button">${icon("table")} Excel</button><button class="chip" data-v="csv" type="button">CSV</button></div></div>
        <div><div class="opt-label">Template (columns and names)</div><select class="input" id="presetSel"></select></div>
        <div><div class="opt-label">Batch name <span class="muted">(optional)</span></div><input class="input" id="batchName" placeholder="e.g. September supplier bills" maxlength="120"></div>
      </div>
      <div class="upload-foot">
        <div class="privacy-line" style="margin:0">${icon("lock")}<span>Your files are private and ${retentionText()}. Never used to train AI.</span></div>
        <button class="btn btn-primary btn-lg" id="startBtn" disabled>${icon("arrowRight")} ${t("start")}</button>
      </div>
    </div>
    <div style="margin:14px 2px 26px">${tip("You can drop a whole ZIP folder, or take a photo of a paper invoice from your phone.")}</div>
    <div class="card">
      <div class="card-head"><h2>${t("recent")}</h2>${batches.length ? `<a href="#/history" class="small">View all</a>` : ""}</div>
      ${batches.length ? batches.slice(0, 5).map(batchRow).join("") : `
        <div class="empty"><div class="empty-icon">${icon("files")}</div><h3>No batches yet</h3><p>Upload your first invoices above, or try the sample files to see the result.</p>
        <button class="btn" id="sampleBtn2">${icon("sparkles")} Try sample files</button></div>`}
    </div>`);

  let files = [];
  let docType = "invoice", outFmt = "xlsx";
  const fillPresets = () => {
    const opts = presets.presets.filter((p) => p.doc_type === docType);
    $("#presetSel").innerHTML = opts.length ? opts.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("") : `<option value="">Default columns</option>`;
  };
  fillPresets();
  const renderPicked = () => {
    const box = $("#picked");
    box.classList.toggle("hidden", !files.length);
    $("#startBtn").disabled = !files.length;
    $("#startBtn").innerHTML = `${icon("arrowRight")} ${t("start")}${files.length ? ` (${files.length} file${files.length > 1 ? "s" : ""})` : ""}`;
    box.innerHTML = `<div class="row between" style="margin-bottom:8px"><strong class="small">${files.length} file${files.length !== 1 ? "s" : ""} ready</strong>
      <button class="btn btn-ghost btn-sm" id="clearFiles">Clear</button></div>
      <div class="picked-list">${files.map((f, i) => `<span class="file-pill">${icon(f.name.toLowerCase().endsWith(".zip") ? "zip" : /\.(jpe?g|png|webp|heic)$/i.test(f.name) ? "image" : "file")}<span title="${esc(f.name)}">${esc(f.name)}</span><button data-rm="${i}" aria-label="Remove ${esc(f.name)}">${icon("x")}</button></span>`).join("")}</div>`;
    $("#clearFiles").onclick = () => { files = []; renderPicked(); };
    $$("[data-rm]", box).forEach((b) => (b.onclick = () => { files.splice(+b.dataset.rm, 1); renderPicked(); }));
  };
  const addFiles = (list) => {
    const ok = /\.(pdf|jpe?g|png|webp|zip|heic|bmp|tiff?)$/i;
    const bad = [...list].filter((f) => !ok.test(f.name));
    files.push(...[...list].filter((f) => ok.test(f.name)));
    if (bad.length) toast(`${bad.length} file(s) skipped: only PDF, JPG, PNG or ZIP are accepted`, "warn");
    if (files.length > settings.max_files) { files = files.slice(0, settings.max_files); toast(`Only the first ${settings.max_files} files were kept`, "warn"); }
    renderPicked();
  };
  const dz = $("#dz");
  $("#chooseBtn").onclick = (e) => { e.stopPropagation(); $("#fileInput").click(); };
  $("#photoBtn").onclick = (e) => { e.stopPropagation(); $("#camInput").click(); };
  dz.onclick = (e) => { if (e.target === dz || e.target.closest(".dz-icon, h3")) $("#fileInput").click(); };
  dz.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } };
  $("#fileInput").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  $("#camInput").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
  $$("#docType .chip").forEach((c) => (c.onclick = () => { $$("#docType .chip").forEach((x) => x.classList.remove("active")); c.classList.add("active"); docType = c.dataset.v; fillPresets(); }));
  $$("#outFmt .chip").forEach((c) => (c.onclick = () => { $$("#outFmt .chip").forEach((x) => x.classList.remove("active")); c.classList.add("active"); outFmt = c.dataset.v; }));
  $$(".batch-row", main).forEach((r) => (r.onclick = () => (location.hash = `#/batch/${r.dataset.id}`)));

  const useSample = async (e) => {
    e?.preventDefault();
    askNotify();
    const r = await api("/api/batches/sample", { method: "POST" });
    location.hash = `#/batch/${r.id}/processing`;
  };
  $("#sampleLink").onclick = useSample;
  $("#sampleBtn2") && ($("#sampleBtn2").onclick = useSample);

  $("#startBtn").onclick = () => {
    askNotify();
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    fd.append("doc_type", docType); fd.append("output_format", outFmt);
    if ($("#presetSel").value) fd.append("preset_id", $("#presetSel").value);
    fd.append("name", $("#batchName").value);
    const btn = $("#startBtn");
    btn.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/batches");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) btn.innerHTML = `<span class="spinner" style="border-color:rgba(255,255,255,.35);border-top-color:#fff"></span> Uploading ${Math.round((e.loaded / e.total) * 100)}%`; };
    xhr.onload = () => {
      let j = {}; try { j = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status === 200) {
        toast(`Uploaded ${files.length} file${files.length > 1 ? "s" : ""}`);
        (j.skipped || []).forEach((s) => toast(s, "warn", 5000));
        location.hash = `#/batch/${j.id}/processing`;
      } else { toast(j.detail || "Upload failed. Please try again.", "err"); btn.disabled = false; renderPicked(); }
    };
    xhr.onerror = () => { toast("Upload failed. Check your internet connection and try again.", "err"); btn.disabled = false; renderPicked(); };
    xhr.send(fd);
  };
});

function retentionText() {
  const r = App.settingsCache?.retention;
  return r === "immediate" ? "deleted right after you download the result" : r === "7d" ? "deleted automatically after 7 days" : "deleted automatically after 30 days";
}

function batchRow(b) {
  return `<div class="batch-row" data-id="${b.id}">
    <div class="batch-icon">${icon("files")}</div>
    <div class="grow"><div class="name">${esc(b.name)} ${b.is_sample ? `<span class="badge info plain" style="margin-left:4px">Sample</span>` : ""}</div>
      <div class="small muted">${b.files} file${b.files !== 1 ? "s" : ""} · ${fmt.when(b.created_at)}${b.vendors?.length ? ` · ${esc(b.vendors.slice(0, 2).join(", "))}${b.vendor_count > 2 ? ` +${b.vendor_count - 2}` : ""}` : ""}</div></div>
    ${b.status === "needs_review" ? `<span class="badge warn">${b.attention} need${b.attention === 1 ? "s" : ""} review</span>` : badge(BATCH_STATUS, b.status)}
    ${icon("chevronRight", "muted")}</div>`;
}

function askNotify() {
  try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch {}
}
function notify(title, body) {
  try { if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification(title, { body }); } catch {}
}

/* ---------- screen 3: processing ---------- */
Router.add("/batch/:id/processing", async ({ id }) => {
  await ensureUser();
  let stopped = false, started = Date.now(), firstDone = null;
  const main = shell("home", `<div id="proc"><div class="card"><div class="proc-head"><div class="skeleton" style="height:26px;width:40%"></div><div class="skeleton" style="height:10px;margin-top:20px"></div></div></div></div>`);
  const stageText = (d) => {
    if (d.status === "queued") return `<span class="stage">${icon("clock")} Waiting…</span>`;
    if (d.status === "processing") return `<span class="stage"><span class="spinner"></span>${d.stage === "extracting" ? "Extracting…" : "Reading…"}</span>`;
    if (d.status === "failed") return `<span class="badge err">Couldn't read</span>`;
    if (d.status === "needs_review") return `<span class="badge warn">Needs check</span>`;
    return `<span class="badge ok">Done</span>`;
  };
  const tick = async () => {
    if (stopped) return;
    let data;
    try { data = await api(`/api/batches/${id}`); } catch (e) { if (!stopped) setTimeout(tick, 2500); return; }
    const docs = data.documents, total = docs.length;
    const done = docs.filter((d) => !["queued", "processing"].includes(d.status)).length;
    if (done && !firstDone) firstDone = { t: Date.now(), n: done };
    let eta = "";
    if (done < total && done > 0) {
      const rate = (Date.now() - started) / done;
      const left = ((total - done) * rate) / 60000;
      eta = left < 1 ? "less than a minute left" : `about ${Math.ceil(left)} minute${Math.ceil(left) > 1 ? "s" : ""} left`;
    } else if (!done) eta = "starting…";
    $("#proc").innerHTML = `
      <div class="card"><div class="proc-head">
        <div class="row between wrap"><div><h1 style="font-size:22px">${esc(data.batch.name)}</h1>
          <p class="muted small" style="margin-top:4px">${esc(data.batch.doc_type_label)} · ${esc(data.batch.preset_name || "Default columns")}</p></div>
          ${done === total ? `<a class="btn btn-primary" href="#/batch/${id}">See results ${icon("arrowRight")}</a>` : ""}</div>
        <div class="count"><strong>${done} of ${total} files done</strong><span>${done === total ? "Finished" : eta}</span></div>
        <div class="progress ${done === total ? "ok" : ""}"><div style="width:${total ? (done / total) * 100 : 0}%"></div></div>
        ${done < total ? `<div style="margin-top:14px">${tip("You can leave this page. We'll let you know when it's finished.")}</div>` : ""}
      </div>
      <div class="proc-list">${docs.map((d) => `
        <div class="proc-item"><div class="thumb" ${d.has_preview ? `style="background-image:url('/api/documents/${d.id}/pages/1')"` : ""}>${d.has_preview ? "" : icon(/\.(jpe?g|png|webp)$/i.test(d.filename) ? "image" : "file")}</div>
          <div class="grow"><div style="font-weight:550;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(d.filename)}</div>
          <div class="small muted">${d.status === "failed" ? esc(d.error) : d.vendor ? `${esc(d.vendor)}${d.total != null ? ` · ${fmt.money(d.total, d.currency)}` : ""}` : "&nbsp;"}</div></div>
          ${stageText(d)}</div>`).join("")}</div></div>`;
    if (data.batch.status === "done") {
      stopped = true;
      const att = data.stats.attention;
      notify("Your batch is ready", `${total} files processed${att ? `, ${att} need a quick check` : ""}.`);
      toast(`All ${total} files processed${att ? `. ${att} need a quick check.` : "."}`);
      setTimeout(() => { if (location.hash === `#/batch/${id}/processing`) location.hash = `#/batch/${id}`; }, 1400);
      return;
    }
    setTimeout(tick, 1200);
  };
  tick();
  return () => { stopped = true; };
});

/* ---------- screen 5: batch summary ---------- */
Router.add("/batch/:id", async ({ id }, query) => {
  await ensureUser();
  const data = await api(`/api/batches/${id}`);
  if (data.batch.status !== "done") { location.hash = `#/batch/${id}/processing`; return; }
  const { batch, documents: docs, stats } = data;
  let filter = query.filter || "all";
  const w = stats.warnings;
  const warnItems = [
    w.duplicate && ["duplicate", "err", "copy", `${w.duplicate} possible duplicate${w.duplicate > 1 ? "s" : ""}`],
    w.mismatch && ["mismatch", "err", "alert", `${w.mismatch} invoice${w.mismatch > 1 ? "s" : ""} where totals do not match`],
    w.quality && ["quality", "warn", "image", `${w.quality} hard-to-read photo${w.quality > 1 ? "s" : ""}`],
    docs.filter((d) => d.status === "failed").length && ["failed", "err", "xCircle", `${docs.filter((d) => d.status === "failed").length} file(s) could not be read`],
  ].filter(Boolean);
  const firstAttention = docs.find((d) => ATTENTION.includes(d.status));
  const main = shell("home", `
    <div class="page-head">
      <div class="grow"><div class="small muted" style="margin-bottom:6px"><a href="#/history">History</a> / Batch</div>
        <div class="row" style="gap:8px"><h1 id="bname">${esc(batch.name)}</h1><button class="btn btn-ghost icon-btn btn-sm" id="renameBtn" aria-label="Rename batch">${icon("edit")}</button>
        ${batch.is_sample ? `<span class="badge info plain">Sample data</span>` : ""}</div>
        <p>${esc(batch.doc_type_label)} · ${esc(batch.preset_name || "Default columns")} · processed ${fmt.when(batch.finished_at)} in ${stats.processing_seconds}s</p></div>
      <div class="row wrap">
        ${firstAttention ? `<a class="btn" href="#/review/${firstAttention.id}?filter=attention">${icon("edit")} Review ${stats.attention} flagged</a>` : `<a class="btn" href="#/review/${docs[0]?.id}">${icon("edit")} Review all</a>`}
        <div class="dl-menu"><div class="row" style="gap:0">
          <button class="btn btn-primary" id="dlMain" style="border-radius:9px 0 0 9px">${icon("download")} Download ${batch.output_format === "csv" ? "CSV" : "Excel"}</button>
          <button class="btn btn-primary icon-btn" id="dlMore" aria-label="More download options" style="border-radius:0 9px 9px 0;border-left:1px solid rgba(255,255,255,.3)">${icon("chevronDown")}</button></div>
          <div class="menu hidden" id="dlMenu">
            <button data-dl="xlsx">${icon("table")} Excel (.xlsx), 3 sheets</button>
            <button data-dl="csv">${icon("file")} CSV (invoices)</button>
            <button data-dl="csv-items">${icon("file")} CSV (line items)</button></div></div>
      </div>
    </div>
    <div class="grid grid-4" style="margin-bottom:16px">
      <div class="card stat"><div class="label">${icon("files")} Files processed</div><div class="value">${stats.processed}</div><div class="sub">${stats.approved} approved</div></div>
      <div class="card stat"><div class="label">${icon("table")} Fields extracted</div><div class="value">${fmt.int(stats.fields)}</div><div class="sub">header fields + line items</div></div>
      <div class="card stat ${stats.attention ? "attention" : "good"}"><div class="label">${icon("alertCircle")} Needs attention</div><div class="value">${stats.attention}</div><div class="sub">${stats.attention ? "check before export" : "all clear"}</div></div>
      <div class="card stat good"><div class="label">${icon("clock")} Time saved</div><div class="value">${fmt.duration(stats.time_saved_minutes)}</div><div class="sub">vs about ${stats.manual_minutes_per_doc} min typing per file</div></div>
    </div>
    <div class="summary-grid">
      <div class="card">
        <div class="card-head"><h2>Files</h2><div class="seg" id="filterSeg">
          ${[["all", "All"], ["attention", "Needs attention"], ["approved", "Approved"]].map(([k, l]) => `<button data-f="${k}" class="${filter === k ? "active" : ""}">${l}</button>`).join("")}</div></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>File</th><th class="hide-sm">Vendor</th><th class="hide-sm">Invoice No</th><th class="hide-sm">Date</th><th class="right">Total</th><th>Status</th></tr></thead>
        <tbody id="docRows"></tbody></table></div>
      </div>
      <div class="stack">
        <div class="card warn-panel"><div class="card-head"><h2>Warnings</h2></div>
          ${warnItems.length ? warnItems.map(([k, cls, ic, text]) => `<div class="warn-item" data-w="${k}"><span class="warn-dot ${cls}">${icon(ic)}</span><span class="grow small" style="font-weight:550">${esc(text)}</span>${icon("chevronRight", "muted")}</div>`).join("")
            : `<div class="warn-item" style="cursor:default"><span class="warn-dot ok">${icon("check")}</span><span class="small">No duplicates or total mismatches found.</span></div>`}
        </div>
        <div class="card card-pad"><h3 style="margin-bottom:8px">What's in the Excel file</h3>
          <ul class="small" style="margin:0;padding-left:18px;color:var(--text-2)">
            <li><b>Invoices</b>: one row per file</li><li><b>Line Items</b>: one row per item, linked by invoice number</li><li><b>Needs Review</b>: anything flagged, with the reason</li></ul>
          <div style="margin-top:12px">${tip("Approve flagged files first so the export is fully checked.")}</div></div>
      </div>
    </div>`);
  const rows = () => {
    let list = docs;
    if (filter === "attention") list = docs.filter((d) => ATTENTION.includes(d.status));
    else if (filter === "approved") list = docs.filter((d) => d.status === "approved");
    else if (["duplicate", "mismatch", "quality"].includes(filter)) list = docs.filter((d) => d.warnings.some((w) => w.type === filter));
    else if (filter === "failed") list = docs.filter((d) => d.status === "failed");
    $("#docRows").innerHTML = list.length ? list.map((d) => `
      <tr class="clickable" data-id="${d.id}"><td><div class="row" style="gap:10px"><div class="thumb" style="width:30px;height:38px;${d.has_preview ? `background-image:url('/api/documents/${d.id}/pages/1')` : ""}">${d.has_preview ? "" : icon("file")}</div>
        <div class="file-cell"><div class="fn" title="${esc(d.filename)}">${esc(d.filename)}</div>
        ${d.warnings.length ? `<div class="tiny" style="color:${d.warnings.some((w) => ["duplicate", "mismatch"].includes(w.type)) ? "var(--err)" : "var(--warn)"}">${esc(d.warnings[0].text)}</div>` : d.attention ? `<div class="tiny" style="color:var(--warn)">${d.attention} field${d.attention > 1 ? "s" : ""} to check</div>` : ""}</div></div></td>
        <td class="hide-sm"><div class="vendor-cell" title="${esc(d.vendor || "")}">${esc(d.vendor || "—")}</div></td><td class="hide-sm nowrap">${esc(d.invoice_no || "—")}</td><td class="hide-sm nowrap">${fmt.date(d.date, App.settingsCache?.date_format)}</td>
        <td class="right num nowrap">${fmt.money(d.total, d.currency)}</td><td>${badge(DOC_STATUS, d.status)}</td></tr>`).join("")
      : `<tr><td colspan="6"><div class="empty" style="padding:28px">${filter === "attention" ? `<h3>Nothing needs attention</h3><p>Every file is ready to export.</p>` : `<p>No files here yet.</p>`}</div></td></tr>`;
    $$("#docRows tr[data-id]").forEach((r) => (r.onclick = () => (location.hash = `#/review/${r.dataset.id}${filter === "attention" ? "?filter=attention" : ""}`)));
    $$("#filterSeg button").forEach((b) => b.classList.toggle("active", b.dataset.f === filter));
  };
  rows();
  $$("#filterSeg button").forEach((b) => (b.onclick = () => { filter = b.dataset.f; rows(); }));
  $$(".warn-item[data-w]").forEach((el) => (el.onclick = () => { filter = el.dataset.w; rows(); $("#docRows").scrollIntoView({ behavior: "smooth", block: "center" }); }));
  const dl = (kind) => {
    const url = kind === "csv-items" ? `/api/batches/${id}/export?format=csv&sheet=line_items` : `/api/batches/${id}/export?format=${kind}`;
    download(url); toast("Download started");
  };
  $("#dlMain").onclick = () => dl(batch.output_format === "csv" ? "csv" : "xlsx");
  $("#dlMore").onclick = (e) => { e.stopPropagation(); $("#dlMenu").classList.toggle("hidden"); document.addEventListener("click", () => $("#dlMenu")?.classList.add("hidden"), { once: true }); };
  $$("#dlMenu [data-dl]").forEach((b) => (b.onclick = () => dl(b.dataset.dl)));
  $("#renameBtn").onclick = () => modal({
    title: "Rename batch", body: `<input class="input" id="newName" value="${esc(batch.name)}" maxlength="120">`, confirm: "Save",
    onConfirm: async (m) => { const name = $("#newName", m).value; await api(`/api/batches/${id}`, { method: "PATCH", body: { name } }); $("#bname").textContent = name; toast("Batch renamed"); },
  });
});

/* ---------- screen 4: review ---------- */
Router.add("/review/:id", async ({ id }, query) => {
  await ensureUser();
  const onlyAttention = query.filter === "attention";
  let doc = await api(`/api/documents/${id}`);
  let zoom = 1, activeKey = null, dirty = false, saving = false;
  const edited = new Set();
  const dateFmt = App.settingsCache?.date_format || "DD/MM/YYYY";

  const main = shell("home", "", { wide: true });
  main.classList.remove("page");
  main.style.padding = "0";

  const siblingsForNav = () => (onlyAttention ? doc.siblings.filter((s) => ATTENTION.includes(s.status) || s.id === doc.id) : doc.siblings);
  const statusOf = (k) => doc.checks[k]?.status || "ok";
  const iconFor = { ok: "check", warn: "alert", error: "x", empty: "minus" };

  function fieldValue(def) {
    const v = doc.fields[def.key];
    if (v === undefined || v === null) return "";
    if (def.kind === "money") return Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (def.kind === "date") return fmt.date(v, dateFmt) === "—" ? v : fmt.date(v, dateFmt);
    return v;
  }

  function render() {
    const nav = siblingsForNav();
    const pos = nav.findIndex((s) => s.id === doc.id);
    const pagesHTML = doc.pages.length && !doc.files_deleted ? doc.pages.map((p) => `
      <div class="page-wrap" data-page="${p.n}" style="width:${zoom * 100}%;max-width:${Math.round(p.w * 0.75 * zoom)}px;">
        <img src="${p.url}" alt="Page ${p.n} of ${esc(doc.filename)}" draggable="false">
        ${boxesFor(p)}</div>`).join("")
      : `<div class="no-preview"><div><div class="empty-icon" style="margin:0 auto 12px;width:52px;height:52px;border-radius:14px;background:#fff;display:grid;place-items:center">${icon(doc.files_deleted ? "lock" : "file")}</div>
         <p>${doc.files_deleted ? "The original file was deleted by your privacy setting. Extracted data is kept." : esc(doc.error || "No preview available")}</p></div></div>`;
    const warn = doc.warnings.map((w) => `<div class="alert ${["duplicate", "mismatch"].includes(w.type) ? "err" : w.type === "info" ? "info" : "warn"}">${icon(w.type === "duplicate" ? "copy" : w.type === "info" ? "info" : "alert")}<div>${esc(w.text)}${w.of ? ` <a href="#/review/${w.of}">Open it</a>` : ""}</div></div>`).join("");
    const itemsSum = doc.items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
    $("#main").innerHTML = `
      <div class="review">
        <section class="viewer" aria-label="Original document">
          <div class="viewer-bar">
            <span class="fname grow" title="${esc(doc.filename)}">${esc(doc.filename)}</span>
            <span class="badge neutral plain hide-sm">${esc({ pdf: "PDF", scan: "Scanned PDF", photo: "Photo" }[doc.kind] || "File")}${doc.pages.length > 1 ? ` · ${doc.pages.length} pages` : ""}</span>
            <button class="btn btn-ghost icon-btn btn-sm" id="zOut" aria-label="Zoom out">${icon("zoomOut")}</button>
            <span class="small muted num" style="width:40px;text-align:center">${Math.round(zoom * 100)}%</span>
            <button class="btn btn-ghost icon-btn btn-sm" id="zIn" aria-label="Zoom in">${icon("zoomIn")}</button>
            <button class="btn btn-ghost icon-btn btn-sm" id="zFit" aria-label="Fit width">${icon("maximize")}</button>
            ${!doc.files_deleted ? `<a class="btn btn-ghost btn-sm hide-sm" href="/api/documents/${doc.id}/original" target="_blank">Original</a>` : ""}
          </div>
          <div class="viewer-scroll" id="vscroll">${pagesHTML}</div>
        </section>
        <section class="editor" aria-label="Extracted data">
          <div class="editor-scroll">
            <div class="row between wrap" style="margin-bottom:12px">
              <div class="status-strip">${badge(DOC_STATUS, doc.status)}
                <span class="badge neutral plain">${doc.engine === "ai" ? `${icon("sparkles")} Read by AI` : "Offline reader"}</span>
                ${doc.reviewed_by && ["approved", "flagged", "skipped"].includes(doc.status) ? `<span class="small muted">by ${esc(doc.reviewed_by)}</span>` : ""}</div>
              <a class="small" href="#/batch/${doc.batch_id}">${esc(doc.batch_name)}</a>
            </div>
            <div class="stack" style="gap:8px">${warn}</div>
            <div class="row between" style="margin-top:16px"><h3>Extracted data</h3><span class="tiny muted hide-sm">Click a value to see where it was found</span></div>
            <div class="fields">${doc.field_defs.map((def) => {
              const st0 = statusOf(def.key), st = st0 === "empty" ? "none" : st0, c = doc.checks[def.key] || {};
              return `<div class="frow ${st}" data-row="${def.key}">
                <label for="f_${def.key}">${esc(def.label)}</label>
                <input class="input ${def.kind === "money" ? "num" : ""}" id="f_${def.key}" data-key="${def.key}" data-kind="${def.kind}" value="${esc(fieldValue(def))}" placeholder="${st === "error" || st === "warn" ? "Not found, type it in" : ""}" autocomplete="off" inputmode="${def.kind === "money" ? "decimal" : "text"}">
                <span class="ficon ${st}" title="${esc(c.reason || (st === "ok" ? "Looks right" : ""))}">${st === "none" ? "" : icon(iconFor[st] || "check")}</span>
                ${c.reason && st !== "ok" ? `<div class="reason">${esc(c.reason)}</div>` : ""}</div>`;
            }).join("")}</div>
            ${doc.include_line_items ? `
            <div class="row between" style="margin-top:22px"><h3>Line items <span class="muted" style="font-weight:500">(${doc.items.length})</span></h3>
              <span class="small muted num">Sum: ${fmt.money(itemsSum)}</span></div>
            <div class="table-wrap"><table class="items-table"><thead><tr><th style="width:46%">Description</th><th class="right">Qty</th><th class="right">Unit price</th><th class="right">Amount</th><th></th></tr></thead>
              <tbody>${doc.items.map((it, i) => `<tr class="${it.check?.status === "warn" ? "warn" : ""}" data-item="${i}" title="${esc(it.check?.reason || "")}">
                <td><input data-i="${i}" data-f="description" value="${esc(it.description)}" aria-label="Description"></td>
                <td><input class="right num" data-i="${i}" data-f="quantity" value="${esc(it.quantity ?? "")}" inputmode="decimal" aria-label="Quantity"></td>
                <td><input class="right num" data-i="${i}" data-f="unit_price" value="${it.unit_price != null ? fmt.money(it.unit_price) : ""}" inputmode="decimal" aria-label="Unit price"></td>
                <td><input class="right num" data-i="${i}" data-f="amount" value="${it.amount != null ? fmt.money(it.amount) : ""}" inputmode="decimal" aria-label="Amount"></td>
                <td><button class="btn btn-ghost icon-btn btn-sm del" data-del="${i}" aria-label="Delete row">${icon("trash")}</button></td></tr>`).join("")}</tbody></table></div>
            <button class="btn btn-ghost btn-sm" id="addItem" style="margin-top:6px">${icon("plus")} Add row</button>` : ""}
            <div style="margin-top:18px">${tip("Press <kbd>Enter</kbd> to approve and open the next file. Use <kbd>←</kbd> <kbd>→</kbd> to move between files.")}</div>
          </div>
          <div class="editor-actions">
            <button class="btn btn-primary" id="approveBtn">${icon("check")} ${t("approve")} <kbd class="hide-sm">Enter</kbd></button>
            <button class="btn" id="skipBtn">${icon("skip")} ${t("skip")}</button>
            <button class="btn btn-danger" id="flagBtn">${icon("flag")} ${t("flag")}</button>
            <span class="grow"></span><span class="small muted" id="saveState"></span>
          </div>
        </section>
      </div>
      <div class="review-foot">
        <button class="btn btn-sm" id="prevBtn" ${pos <= 0 ? "disabled" : ""}>${icon("chevronLeft")} <span class="hide-sm">Previous</span></button>
        <div class="row" style="gap:14px"><span class="pos num">${pos + 1} of ${nav.length}</span>
          <label class="row small" style="gap:8px;cursor:pointer"><span class="switch"><input type="checkbox" id="attnToggle" ${onlyAttention ? "checked" : ""}><span></span></span><span class="hide-sm">Only show files that need attention</span><span class="tiny" style="display:none">Attention</span></label></div>
        <button class="btn btn-sm" id="nextBtn" ${pos >= nav.length - 1 ? "disabled" : ""}><span class="hide-sm">Next</span> ${icon("chevronRight")}</button>
      </div>`;
    bind();
    if (activeKey) highlight(activeKey, false);
  }

  function boxesFor(p) {
    const pad = 4;
    const out = [];
    for (const def of doc.field_defs) {
      const c = doc.checks[def.key];
      if (!c?.box || c.page !== p.n) continue;
      const [x0, y0, x1, y1] = c.box;
      out.push(`<div class="hl ${c.status}" data-hl="${def.key}" title="${esc(def.label)}" style="left:${((x0 - pad) / p.w) * 100}%;top:${((y0 - pad) / p.h) * 100}%;width:${((x1 - x0 + pad * 2) / p.w) * 100}%;height:${((y1 - y0 + pad * 2) / p.h) * 100}%"></div>`);
    }
    doc.items.forEach((it, i) => {
      if (!it.box || it.page !== p.n) return;
      const [x0, y0, x1, y1] = it.box;
      out.push(`<div class="hl ${it.check?.status === "warn" ? "warn" : ""}" data-hl="item-${i}" style="left:${((x0 - pad) / p.w) * 100}%;top:${((y0 - pad) / p.h) * 100}%;width:${((x1 - x0 + pad * 2) / p.w) * 100}%;height:${((y1 - y0 + pad * 2) / p.h) * 100}%"></div>`);
    });
    return out.join("");
  }

  function highlight(key, scroll = true) {
    activeKey = key;
    $$(".hl.active").forEach((h) => h.classList.remove("active"));
    $$(".frow.focused").forEach((r) => r.classList.remove("focused"));
    $$(".items-table tr.active").forEach((r) => r.classList.remove("active"));
    const hl = $(`.hl[data-hl="${key}"]`);
    if (key.startsWith("item-")) $(`.items-table tr[data-item="${key.slice(5)}"]`)?.classList.add("active");
    else $(`.frow[data-row="${key}"]`)?.classList.add("focused");
    if (hl) {
      hl.classList.add("active");
      if (scroll) {
        const sc = $("#vscroll"), r = hl.getBoundingClientRect(), sr = sc.getBoundingClientRect();
        sc.scrollTo({ top: sc.scrollTop + r.top - sr.top - sr.height / 2 + r.height / 2, left: sc.scrollLeft + r.left - sr.left - sr.width / 2 + r.width / 2, behavior: "smooth" });
      }
    }
  }

  function collect() {
    const fields = {};
    $$(".fields input[data-key]").forEach((inp) => {
      let v = inp.value.trim();
      if (inp.dataset.kind === "money") v = v.replace(/,/g, "");
      if (inp.dataset.kind === "date" && v) {
        const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);
        if (m && dateFmt === "DD/MM/YYYY") v = `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
        if (m && dateFmt === "MM/DD/YYYY") v = `${m[3]}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
      }
      fields[inp.dataset.key] = v === "" ? null : v;
    });
    const items = doc.items.map((it, i) => {
      const get = (f) => $(`.items-table input[data-i="${i}"][data-f="${f}"]`)?.value.trim().replace(/,/g, "") ?? "";
      return { ...it, description: $(`.items-table input[data-i="${i}"][data-f="description"]`)?.value.trim() ?? it.description, quantity: get("quantity"), unit_price: get("unit_price"), amount: get("amount") };
    });
    return { fields, items };
  }

  async function save(action) {
    if (saving) return null;
    saving = true;
    $("#saveState") && ($("#saveState").innerHTML = `<span class="row" style="gap:6px"><span class="spinner"></span>Saving…</span>`);
    try {
      const body = { action };
      if (dirty) Object.assign(body, collect(), { edited_keys: [...edited] });
      doc = await api(`/api/documents/${doc.id}`, { method: "PATCH", body });
      dirty = false; edited.clear();
      return doc;
    } catch (e) { toast(e.message, "err"); $("#saveState") && ($("#saveState").textContent = "Not saved"); return null; }
    finally { saving = false; }
  }

  async function act(action) {
    const before = siblingsForNav().map((s) => s.id);
    const idx = before.indexOf(doc.id);
    const r = await save(action);
    if (!r) return;
    toast({ approve: "Approved", skip: "Skipped", flag: "Flagged for follow-up" }[action], action === "flag" ? "warn" : "ok", 1600);
    // pick the next document: in attention mode, the next one still needing attention
    const sib = r.siblings;
    let nextId = null;
    // after an action, move on to files that still wait for a person (flagged ones are already handled)
    const pool = onlyAttention ? sib.filter((s) => ["needs_review", "failed"].includes(s.status) && s.id !== r.id) : sib;
    if (onlyAttention) {
      const after = pool.find((s) => sib.findIndex((x) => x.id === s.id) > sib.findIndex((x) => x.id === r.id));
      nextId = (after || pool[0])?.id;
    } else nextId = sib[idx + 1]?.id || null;
    if (nextId) location.hash = `#/review/${nextId}${onlyAttention ? "?filter=attention" : ""}`;
    else { toast("All done! Every file in this batch has been reviewed.", "ok", 3500); location.hash = `#/batch/${r.batch_id}`; }
  }

  async function move(delta) {
    const nav = siblingsForNav();
    const pos = nav.findIndex((s) => s.id === doc.id);
    const target = nav[pos + delta];
    if (!target) return;
    if (dirty) await save();
    location.hash = `#/review/${target.id}${onlyAttention ? "?filter=attention" : ""}`;
  }

  function bind() {
    $$(".fields input[data-key]").forEach((inp) => {
      inp.addEventListener("focus", () => highlight(inp.dataset.key));
      inp.addEventListener("input", () => { dirty = true; edited.add(inp.dataset.key); $("#saveState").textContent = "Unsaved changes"; });
    });
    $$(".items-table input").forEach((inp) => {
      inp.addEventListener("focus", () => highlight(`item-${inp.dataset.i}`));
      inp.addEventListener("input", () => { dirty = true; $("#saveState").textContent = "Unsaved changes"; });
    });
    $$(".hl").forEach((h) => (h.onclick = () => {
      const k = h.dataset.hl;
      if (k.startsWith("item-")) $(`.items-table input[data-i="${k.slice(5)}"][data-f="description"]`)?.focus();
      else $(`#f_${k}`)?.focus();
    }));
    $$("[data-del]").forEach((b) => (b.onclick = () => { const c = collect(); doc.items = c.items; doc.fields = { ...doc.fields }; doc.items.splice(+b.dataset.del, 1); dirty = true; keepFieldsAndRender(c.fields); }));
    $("#addItem") && ($("#addItem").onclick = () => { const c = collect(); doc.items = c.items; doc.items.push({ description: "", quantity: null, unit_price: null, amount: null }); dirty = true; keepFieldsAndRender(c.fields); $$(".items-table tr:last-child input")[0]?.focus(); });
    $("#zIn").onclick = () => { zoom = Math.min(3, +(zoom + 0.25).toFixed(2)); rerenderKeep(); };
    $("#zOut").onclick = () => { zoom = Math.max(0.5, +(zoom - 0.25).toFixed(2)); rerenderKeep(); };
    $("#zFit").onclick = () => { zoom = 1; rerenderKeep(); };
    $("#approveBtn").onclick = () => act("approve");
    $("#skipBtn").onclick = () => act("skip");
    $("#flagBtn").onclick = () => act("flag");
    $("#prevBtn").onclick = () => move(-1);
    $("#nextBtn").onclick = () => move(1);
    $("#attnToggle").onchange = (e) => { location.hash = `#/review/${doc.id}${e.target.checked ? "?filter=attention" : ""}`; };
  }

  function keepFieldsAndRender(fieldsNow) {
    // keep typed (unsaved) header values while re-rendering
    const typed = {};
    $$(".fields input[data-key]").forEach((i) => (typed[i.dataset.key] = i.value));
    render();
    Object.entries(typed).forEach(([k, v]) => { const i = $(`#f_${k}`); if (i) i.value = v; });
    $("#saveState").textContent = "Unsaved changes";
  }
  function rerenderKeep() {
    const c = dirty ? collect() : null;
    const typed = {};
    $$(".fields input[data-key]").forEach((i) => (typed[i.dataset.key] = i.value));
    const itemVals = $$(".items-table input").map((i) => i.value);
    render();
    Object.entries(typed).forEach(([k, v]) => { const i = $(`#f_${k}`); if (i) i.value = v; });
    $$(".items-table input").forEach((i, n) => (i.value = itemVals[n] ?? i.value));
    if (c) $("#saveState").textContent = "Unsaved changes";
  }

  const onKey = (e) => {
    if ($(".modal-bg")) return;
    const tag = e.target.tagName;
    const inField = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (e.key === "Enter" && !e.shiftKey && tag !== "BUTTON" && tag !== "A" && tag !== "TEXTAREA" && e.target.type !== "checkbox") { e.preventDefault(); act("approve"); }
    else if (!inField && e.key === "ArrowRight") { e.preventDefault(); move(1); }
    else if (!inField && e.key === "ArrowLeft") { e.preventDefault(); move(-1); }
    else if (e.key === "Escape" && inField) e.target.blur();
  };
  document.addEventListener("keydown", onKey);
  const beforeUnload = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
  window.addEventListener("beforeunload", beforeUnload);

  render();
  // start on the first field that needs attention
  const firstBad = doc.field_defs.find((d) => ["warn", "error"].includes(statusOf(d.key)));
  if (firstBad && window.innerWidth > 1000) setTimeout(() => $(`#f_${firstBad.key}`)?.focus(), 50);

  return () => {
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("beforeunload", beforeUnload);
    if (dirty) { const c = collect(); api(`/api/documents/${doc.id}`, { method: "PATCH", body: { ...c, edited_keys: [...edited] } }).catch(() => {}); }
  };
});

/* ---------- screen 7: history ---------- */
Router.add("/history", async () => {
  await ensureUser();
  const main = shell("history", `
    <div class="page-head"><div><h1>History</h1><p>Every batch you've processed. Reopen one to review or download again.</p></div>
      <a class="btn btn-primary" href="#/">${icon("upload")} New upload</a></div>
    <div class="filters">
      <div class="input-icon">${icon("search")}<input class="input" id="q" placeholder="Search vendor, invoice number, file or batch" autocomplete="off"></div>
      <select class="input" id="st"><option value="">All statuses</option><option value="needs_review">Needs review</option><option value="done">Done</option><option value="processing">Processing</option></select>
      <input class="input" type="date" id="from" aria-label="From date"><input class="input" type="date" id="to" aria-label="To date">
    </div>
    <div class="card" id="hist"><div class="card-body"><div class="skeleton" style="height:18px;margin-bottom:12px"></div><div class="skeleton" style="height:18px;width:70%"></div></div></div>
    <div style="margin-top:14px">${tip("Search works across vendor names, invoice numbers and file names inside every batch.")}</div>`);
  let timer;
  const load = async () => {
    const qs = new URLSearchParams({ q: $("#q").value, status: $("#st").value, date_from: $("#from").value, date_to: $("#to").value });
    const list = await api(`/api/batches?${qs}`);
    const filtered = [...qs.values()].some(Boolean);
    $("#hist").innerHTML = list.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>Batch</th><th class="hide-sm">Date</th><th class="right hide-sm">Files</th><th class="hide-sm">Vendors</th><th>Status</th><th></th></tr></thead><tbody>
      ${list.map((b) => `<tr class="clickable" data-id="${b.id}"><td><div style="font-weight:600">${esc(b.name)}</div>${b.is_sample ? `<span class="badge info plain" style="margin-top:3px">Sample</span>` : `<div class="tiny muted" style="display:none">${b.files} files</div>`}</td>
        <td class="hide-sm nowrap">${fmt.when(b.created_at)}</td><td class="right hide-sm num">${b.files}</td>
        <td class="hide-sm small muted">${esc(b.vendors.join(", "))}${b.vendor_count > 4 ? ` +${b.vendor_count - 4}` : ""}</td>
        <td>${b.status === "needs_review" ? `<span class="badge warn">${b.attention} to review</span>` : badge(BATCH_STATUS, b.status)}</td>
        <td class="right">${b.is_sample === 1 ? "" : `<button class="btn btn-ghost icon-btn btn-sm" data-del="${b.id}" aria-label="Delete batch">${icon("trash")}</button>`}</td></tr>`).join("")}
      </tbody></table></div>`
      : `<div class="empty"><div class="empty-icon">${icon(filtered ? "search" : "history")}</div><h3>${filtered ? "No batches match" : "Nothing here yet"}</h3>
         <p>${filtered ? "Try a different search or clear the filters." : "Your processed batches will appear here."}</p>
         ${filtered ? `<button class="btn" id="clearF">Clear filters</button>` : `<a class="btn btn-primary" href="#/">Upload invoices</a>`}</div>`;
    $$("#hist tr[data-id]").forEach((r) => (r.onclick = (e) => { if (!e.target.closest("[data-del]")) location.hash = `#/batch/${r.dataset.id}`; }));
    $$("#hist [data-del]").forEach((b) => (b.onclick = async () => {
      const ok = await modal({ title: "Delete this batch?", body: "<p>The files and extracted data will be permanently deleted. This can't be undone.</p>", confirm: "Delete", danger: true });
      if (ok) { await api(`/api/batches/${b.dataset.del}`, { method: "DELETE" }); toast("Batch deleted"); load(); }
    }));
    $("#clearF") && ($("#clearF").onclick = () => { ["q", "st", "from", "to"].forEach((k) => ($(`#${k}`).value = "")); load(); });
  };
  $("#q").oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); };
  ["st", "from", "to"].forEach((k) => ($(`#${k}`).onchange = load));
  load();
});

/* ---------- screen 8a: templates (presets) ---------- */
Router.add("/templates", async (_, query) => {
  await ensureUser();
  let data = await api("/api/presets");
  let current = data.presets.find((p) => String(p.id) === query.id) || data.presets[0];
  let draft = JSON.parse(JSON.stringify(current));
  const main = shell("templates", `
    <div class="page-head"><div><h1>Templates</h1><p>Choose which fields to extract, rename columns to match your own Excel, and save presets per document type.</p></div>
      <button class="btn" id="newPreset">${icon("plus")} New template</button></div>
    <div class="tpl-layout"><div class="card tpl-list" id="tplList"></div><div class="card" id="tplEdit"></div></div>`);

  const renderList = () => {
    $("#tplList").innerHTML = data.presets.map((p) => `<button class="${p.id === draft.id ? "active" : ""}" data-id="${p.id}"><div style="font-weight:600">${esc(p.name)}</div><div class="small muted">${esc(data.doc_types[p.doc_type])} · ${p.config.fields.filter((f) => f.enabled).length} columns</div></button>`).join("");
    $$("#tplList button").forEach((b) => (b.onclick = () => { current = data.presets.find((p) => p.id === +b.dataset.id); draft = JSON.parse(JSON.stringify(current)); renderList(); renderEdit(); }));
  };
  const renderEdit = () => {
    const f = draft.config.fields;
    $("#tplEdit").innerHTML = `
      <div class="card-head"><h2>${esc(draft.name || "New template")}</h2><div class="row">${draft.id ? `<button class="btn btn-ghost btn-sm btn-danger" id="delPreset">${icon("trash")} Delete</button>` : ""}</div></div>
      <div class="card-body stack" style="gap:18px">
        <div class="grid grid-2"><label class="field">Template name<input class="input" id="pName" value="${esc(draft.name)}" maxlength="80"></label>
          <label class="field">Document type<select class="input" id="pType">${Object.entries(data.doc_types).map(([k, v]) => `<option value="${k}" ${k === draft.doc_type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div>
        ${draft.doc_type === "form" ? `<div class="alert info">${icon("info")}<div>Forms are read as label/value pairs. Every field found on the form becomes a column automatically.</div></div>` : `
        <div><div class="row between" style="margin-bottom:4px"><h3>Columns</h3><span class="small muted">Turn off fields you don't need, rename to match your Excel</span></div>
          ${f.map((x, i) => `<div class="field-row"><label class="switch"><input type="checkbox" data-en="${i}" ${x.enabled ? "checked" : ""}><span></span></label>
            <span class="small muted key">${esc(fieldDefault(x.key))}</span>
            <input class="input" data-lb="${i}" value="${esc(x.label)}" aria-label="Column name for ${esc(fieldDefault(x.key))}">
            <div class="row" style="gap:2px"><button class="btn btn-ghost icon-btn btn-sm" data-up="${i}" ${i === 0 ? "disabled" : ""} aria-label="Move up">${icon("arrowUp")}</button><button class="btn btn-ghost icon-btn btn-sm" data-down="${i}" ${i === f.length - 1 ? "disabled" : ""} aria-label="Move down">${icon("arrowDown")}</button></div></div>`).join("")}</div>
        <label class="row" style="gap:10px;cursor:pointer"><span class="switch"><input type="checkbox" id="pItems" ${draft.config.include_line_items ? "checked" : ""}><span></span></span><span>Include a <b>Line Items</b> sheet</span></label>`}
        <label class="field" style="max-width:260px">Date format in Excel<select class="input" id="pDate">${data.date_formats.map((d) => `<option ${d === draft.config.date_format ? "selected" : ""}>${d}</option>`).join("")}</select></label>
        ${draft.doc_type !== "form" ? `<div><div class="small muted" style="margin-bottom:6px">Preview of your Excel header</div><div class="xl-preview"><table><tr><th>File</th>${f.filter((x) => x.enabled).map((x) => `<th>${esc(x.label)}</th>`).join("")}<th>Status</th></tr>
          <tr><td>invoice_001.pdf</td>${f.filter((x) => x.enabled).map((x) => `<td>${esc(sampleVal(x.key, draft.config.date_format))}</td>`).join("")}<td>Approved</td></tr></table></div></div>` : ""}
        <div class="row" style="justify-content:flex-end"><button class="btn btn-primary" id="savePreset">${icon("check")} Save template</button></div>
      </div>`;
    const sync = () => {
      draft.name = $("#pName").value;
      $$("[data-lb]").forEach((i) => (f[+i.dataset.lb].label = i.value));
      $$("[data-en]").forEach((i) => (f[+i.dataset.en].enabled = i.checked));
      if ($("#pItems")) draft.config.include_line_items = $("#pItems").checked;
      draft.config.date_format = $("#pDate").value;
    };
    $$("[data-en], #pItems, #pDate").forEach((el) => (el.onchange = () => { sync(); renderEdit(); }));
    $$("[data-lb]").forEach((el) => (el.onchange = () => { sync(); renderEdit(); }));
    $("#pName").oninput = sync;
    $("#pType").onchange = (e) => {
      sync();
      draft.doc_type = e.target.value;
      draft.config.fields = (data.fields[draft.doc_type] || []).map((x) => ({ key: x.key, label: x.label, enabled: x.key !== "discount" }));
      renderEdit();
    };
    $$("[data-up]").forEach((b) => (b.onclick = () => { sync(); const i = +b.dataset.up; [f[i - 1], f[i]] = [f[i], f[i - 1]]; renderEdit(); }));
    $$("[data-down]").forEach((b) => (b.onclick = () => { sync(); const i = +b.dataset.down; [f[i + 1], f[i]] = [f[i], f[i + 1]]; renderEdit(); }));
    $("#savePreset").onclick = async () => {
      sync();
      if (!draft.name.trim()) { toast("Please give the template a name", "warn"); return; }
      const body = { name: draft.name, doc_type: draft.doc_type, config: draft.config };
      const saved = draft.id ? await api(`/api/presets/${draft.id}`, { method: "PUT", body }) : await api("/api/presets", { method: "POST", body });
      data = await api("/api/presets");
      draft = JSON.parse(JSON.stringify(data.presets.find((p) => p.id === saved.id)));
      renderList(); renderEdit(); toast("Template saved");
    };
    $("#delPreset") && ($("#delPreset").onclick = async () => {
      if (!(await modal({ title: "Delete template?", body: `<p>“${esc(draft.name)}” will be removed. Past batches keep their data.</p>`, confirm: "Delete", danger: true }))) return;
      await api(`/api/presets/${draft.id}`, { method: "DELETE" });
      data = await api("/api/presets"); draft = JSON.parse(JSON.stringify(data.presets[0])); renderList(); renderEdit(); toast("Template deleted");
    });
  };
  const fieldDefault = (key) => Object.values(data.fields).flat().find((x) => x.key === key)?.label || key;
  const sampleVal = (key, df) => ({ invoice_no: "INV-2041", date: fmt.date("2026-09-12", df), vendor: "ABC Traders", tax_id: "1234567-8", customer: "Your Company", subtotal: "5,000.00", discount: "0.00", tax: "850.00", total: "5,850.00", currency: "PKR" }[key] || "…");
  $("#newPreset").onclick = () => {
    draft = { id: null, name: "", doc_type: "invoice", config: { fields: data.fields.invoice.map((x) => ({ key: x.key, label: x.label, enabled: x.key !== "discount" })), include_line_items: true, date_format: "DD/MM/YYYY" } };
    renderList(); renderEdit(); $("#pName").focus();
  };
  renderList(); renderEdit();
});

/* ---------- screen 8b: settings ---------- */
Router.add("/settings", async (_, query) => {
  await ensureUser();
  const s = await api("/api/settings");
  App.settingsCache = s;
  const isAdmin = App.user.role === "admin";
  let tab = query.tab || "general";
  const main = shell("settings", `
    <div class="settings-layout">
      <div class="page-head"><div><h1>Settings</h1><p>Company details, branding, privacy and team access.</p></div></div>
      ${!isAdmin ? `<div class="alert info" style="margin-bottom:16px">${icon("info")}<div>Only admins can change settings. Ask an admin if something needs updating.</div></div>` : ""}
      <div class="tabs" id="tabs">${[["general", "General"], ["branding", "Branding"], ["privacy", "Privacy"], ["team", "Team"], ["reader", "Reading engine"]].map(([k, l]) => `<button data-t="${k}" class="${tab === k ? "active" : ""}">${l}</button>`).join("")}</div>
      <div id="tabBody"></div>
    </div>`);
  const saveSettings = async (patch) => {
    try { const r = await api("/api/settings", { method: "PUT", body: patch }); Object.assign(s, r); App.settingsCache = s; App.info = await api("/api/app-info"); toast("Settings saved"); return true; }
    catch (e) { toast(e.message, "err"); return false; }
  };
  const bodies = {
    general: () => `<div class="card card-body stack" style="gap:18px">
      <label class="field">Company name<input class="input" id="sName" value="${esc(s.company_name)}" ${isAdmin ? "" : "disabled"}></label>
      <div class="grid grid-2">
        <label class="field">Default currency<select class="input" id="sCur" ${isAdmin ? "" : "disabled"}>${["PKR", "USD", "AED", "EUR", "GBP", "SAR"].map((c) => `<option ${c === s.default_currency ? "selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="field">Date format on screen<select class="input" id="sDate" ${isAdmin ? "" : "disabled"}>${["DD/MM/YYYY", "YYYY-MM-DD", "DD Mon YYYY", "MM/DD/YYYY"].map((c) => `<option ${c === s.date_format ? "selected" : ""}>${c}</option>`).join("")}</select></label></div>
      <label class="field" style="max-width:300px">Interface language<select class="input" id="sLang"><option value="en" ${LANG === "en" ? "selected" : ""}>English</option><option value="ur" ${LANG === "ur" ? "selected" : ""}>اردو (Urdu labels)</option></select></label>
      ${isAdmin ? `<div><button class="btn btn-primary" id="saveGen">Save changes</button></div>` : ""}</div>`,
    branding: () => `<div class="card card-body stack" style="gap:20px">
      <p class="muted">Put your client's logo and colour in the header for a white-label delivery.</p>
      <div class="row wrap" style="gap:18px"><div class="card" style="width:180px;height:70px;display:grid;place-items:center;background:var(--surface-2)">${s.logo_url ? `<img src="${esc(s.logo_url)}" alt="Logo" style="max-height:48px;max-width:150px">` : `<span class="muted small">No logo yet</span>`}</div>
        ${isAdmin ? `<div class="stack" style="gap:8px"><label class="btn">${icon("upload")} Upload logo<input type="file" id="logoIn" accept=".png,.jpg,.jpeg,.svg,.webp" hidden></label>
        ${s.logo_url ? `<button class="btn btn-ghost btn-sm" id="rmLogo">Remove logo</button>` : ""}</div>` : ""}</div>
      <div><div class="small" style="font-weight:600;color:var(--text-2);margin-bottom:8px">Accent colour</div>
        <div class="color-row"><input type="color" id="accIn" value="${esc(s.accent_color)}" ${isAdmin ? "" : "disabled"}>
        ${["#1d4ed8", "#0f766e", "#7c3aed", "#be123c", "#b45309", "#111827"].map((c) => `<button class="swatch" data-c="${c}" style="background:${c}" aria-label="Use ${c}"></button>`).join("")}</div></div>
      ${isAdmin ? `<div><button class="btn btn-primary" id="saveBrand">Save branding</button></div>` : ""}</div>`,
    privacy: () => `<div class="card card-body stack" style="gap:14px">
      <h3>How long should we keep uploaded files?</h3><p class="muted small">Extracted data stays in your history. Original files and previews are deleted on this schedule.</p>
      ${[["immediate", "Delete right after download", "Originals are removed as soon as you download the Excel or CSV."], ["7d", "Keep for 7 days", "Handy if you review over a few days."], ["30d", "Keep for 30 days", "Recommended for monthly accounting cycles."]].map(([v, l, d]) => `
        <label class="radio-card"><input type="radio" name="ret" value="${v}" ${s.retention === v ? "checked" : ""} ${isAdmin ? "" : "disabled"}><div><div style="font-weight:600">${l}</div><div class="small muted">${d}</div></div></label>`).join("")}
      <div class="alert ok">${icon("shield")}<div>Files are private to your company account, sent only over encrypted connections in production, and <b>never used to train AI models</b>. <a href="/privacy" target="_blank">Read the privacy statement</a></div></div>
      ${isAdmin ? `<div><button class="btn btn-primary" id="savePriv">Save privacy setting</button></div>` : ""}</div>`,
    team: () => `<div class="card"><div class="card-head"><h2>Team members</h2>${isAdmin ? `<button class="btn btn-sm btn-primary" id="addMember">${icon("plus")} Add member</button>` : ""}</div><div class="card-body" id="teamList"><div class="skeleton" style="height:40px"></div></div></div>
      <div style="margin-top:12px">${tip("<b>Admins</b> can change settings and templates. <b>Reviewers</b> can upload, review and export.")}</div>`,
    reader: () => `<div class="card card-body stack" style="gap:14px">
      <div class="row" style="gap:14px"><div class="warn-dot ${App.info.ai_enabled ? "ok" : "warn"}" style="width:42px;height:42px">${icon(App.info.ai_enabled ? "sparkles" : "file")}</div>
        <div><h3>${App.info.ai_enabled ? "AI reading is on" : "Offline reader is on"}</h3>
        <p class="muted small">${App.info.ai_enabled ? "Documents are read by an AI model (Groq) that understands any invoice layout, with the offline reader as a backup." : "Documents are read by the built-in offline reader (text layer + OCR). It works without internet and handles common invoice layouts well."}</p></div></div>
      <div class="alert info">${icon("info")}<div>Whatever the engine, every value is checked: totals are re-added, duplicates are detected, and uncertain fields are marked orange for a person to confirm.</div></div></div>`,
  };
  const renderTab = () => {
    $("#tabBody").innerHTML = bodies[tab]();
    $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.t === tab));
    if (tab === "general") {
      $("#sLang").onchange = (e) => { LANG = e.target.value; localStorage.setItem("df_lang", LANG); Router.go(); };
      $("#saveGen") && ($("#saveGen").onclick = () => saveSettings({ company_name: $("#sName").value.trim() || "DocuFlow", default_currency: $("#sCur").value, date_format: $("#sDate").value }).then((ok) => ok && Router.go()));
    }
    if (tab === "branding" && isAdmin) {
      $("#accIn").oninput = (e) => setAccent(e.target.value);
      $$(".swatch").forEach((b) => (b.onclick = () => { $("#accIn").value = b.dataset.c; setAccent(b.dataset.c); }));
      $("#saveBrand").onclick = () => saveSettings({ accent_color: $("#accIn").value }).then((ok) => ok && Router.go());
      $("#logoIn").onchange = async (e) => {
        const fd = new FormData(); fd.append("file", e.target.files[0]);
        try { await api("/api/settings/logo", { method: "POST", form: fd }); App.info = await api("/api/app-info"); Object.assign(s, await api("/api/settings")); toast("Logo updated"); Router.go(); } catch (err) { toast(err.message, "err"); }
      };
      $("#rmLogo") && ($("#rmLogo").onclick = () => saveSettings({ logo_url: "" }).then(() => Router.go()));
    }
    if (tab === "privacy" && isAdmin) $("#savePriv").onclick = () => saveSettings({ retention: $("input[name=ret]:checked").value });
    if (tab === "team") loadTeam();
  };
  const loadTeam = async () => {
    const team = await api("/api/team");
    $("#teamList").innerHTML = team.map((m) => `<div class="member"><span class="avatar" style="cursor:default">${esc(initials(m.name))}</span>
      <div class="grow"><div style="font-weight:600">${esc(m.name)} ${m.id === App.user.id ? `<span class="muted small">(you)</span>` : ""}</div><div class="small muted">${esc(m.email)}</div></div>
      ${isAdmin && m.id !== App.user.id ? `<select class="input" style="width:130px;height:34px" data-role="${m.id}"><option value="admin" ${m.role === "admin" ? "selected" : ""}>Admin</option><option value="reviewer" ${m.role === "reviewer" ? "selected" : ""}>Reviewer</option></select>
        <button class="btn btn-ghost icon-btn btn-sm" data-rm="${m.id}" aria-label="Remove ${esc(m.name)}">${icon("trash")}</button>` : `<span class="badge neutral plain" style="text-transform:capitalize">${esc(m.role)}</span>`}</div>`).join("");
    $$("[data-role]").forEach((sel) => (sel.onchange = async () => { await api(`/api/team/${sel.dataset.role}`, { method: "PATCH", body: { role: sel.value } }); toast("Role updated"); }));
    $$("#teamList [data-rm]").forEach((b) => (b.onclick = async () => {
      if (await modal({ title: "Remove team member?", body: "<p>They will lose access immediately.</p>", confirm: "Remove", danger: true })) { await api(`/api/team/${b.dataset.rm}`, { method: "DELETE" }); toast("Member removed"); loadTeam(); }
    }));
    $("#addMember") && ($("#addMember").onclick = () => modal({
      title: "Add team member", confirm: "Add member",
      body: `<div class="stack"><label class="field">Name<input class="input" id="mName"></label><label class="field">Email<input class="input" id="mEmail" type="email"></label>
        <label class="field">Role<select class="input" id="mRole"><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></label></div>`,
      onConfirm: async (m) => {
        const r = await api("/api/team", { method: "POST", body: { name: $("#mName", m).value, email: $("#mEmail", m).value, role: $("#mRole", m).value } });
        loadTeam();
        setTimeout(() => modal({ title: "Member added", body: `<p>Share this temporary password so they can sign in:</p><p style="margin-top:10px"><code style="font-size:16px;background:var(--surface-2);padding:6px 10px;border-radius:6px">${esc(r.temporary_password)}</code></p>`, confirm: "Done", cancel: null }), 50);
      },
    }));
  };
  $$("#tabs button").forEach((b) => (b.onclick = () => { tab = b.dataset.t; renderTab(); }));
  renderTab();
});

/* ---------- boot ---------- */
(async () => {
  try {
    App.info = await api("/api/app-info");
    setAccent(App.info.accent_color);
    try { App.user = await api("/api/me"); App.settingsCache = await api("/api/settings"); } catch {}
  } catch {}
  Router.start();
})();
