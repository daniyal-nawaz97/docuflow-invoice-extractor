"""Build a static, clickable demo of this app for free hosting (GitHub Pages).

The real app runs once locally with its demo data; every screen's data is saved as files, and a small
service worker in the browser answers the app's API calls from those files. Clicks that would change data
get realistic answers where it makes sense, otherwise a friendly "read-only demo" message.

Used by scripts/build_static_demo.py (project-specific list of pages to capture).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

import httpx

HERE = Path(__file__).resolve().parent
PATHS = r"(api|static|brand|demo-shops|widget\.js|widget|demo-site|landing|privacy|sample-files)"


def norm_key(url: str) -> str:
    """Path + sorted, non-empty query parameters. The service worker normalises the same way."""
    s = urlsplit(url)
    q = sorted((k, v) for k, v in parse_qsl(s.query, keep_blank_values=True) if v != "")
    enc = lambda v: quote(v, safe="!'()*-._~").replace("%20", "+")  # noqa: E731  (same as JS encodeURIComponent)
    return s.path + ("?" + "&".join(f"{enc(k)}={enc(v)}" for k, v in q) if q else "")


def rewrite(text: str, base: str) -> str:
    """Make root-absolute app paths live under the GitHub Pages sub-path (/<repo>/...)."""
    text = re.sub(r"(?<=[\"'`(=\s])/" + PATHS + r"(?=[/?\"'`#)\s.]|$)", lambda m: f"{base}/{m.group(1)}", text)
    text = re.sub(r"(?<=[\"'`])/#/", f"{base}/#/", text)
    text = re.sub(r"href=\"/\"", f'href="{base}/"', text)
    return text


class Server:
    """Start the real app on a free port with a fresh data folder."""

    def __init__(self, project: Path, port: int, env: dict | None = None, ready=lambda r: r.get("ready", True)):
        self.project, self.port = project, port
        self.data = Path(tempfile.mkdtemp(prefix="static_demo_"))
        self.env = {**os.environ, "DATA_DIR": str(self.data), "PORT": str(port), **(env or {})}
        self.ready = ready
        self.url = f"http://127.0.0.1:{port}"

    def __enter__(self):
        py = sys.executable
        self.proc = subprocess.Popen([py, "-m", "uvicorn", "app.main:app", "--port", str(self.port)], cwd=self.project, env=self.env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < 600:
            try:
                r = httpx.get(self.url + "/health", timeout=3).json()
                if self.ready(r):
                    return self
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError("app did not become ready")

    def __exit__(self, *a):
        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        self.proc.wait(timeout=30)
        shutil.rmtree(self.data, ignore_errors=True)


class Site:
    def __init__(self, project: Path, out: Path, repo: str, server: Server):
        self.project, self.out, self.base, self.srv = project, out, f"/{repo}", server
        self.client = httpx.Client(base_url=server.url, timeout=300, follow_redirects=True)
        self.get_map, self.post_map = {}, {}
        if out.exists():
            shutil.rmtree(out)
        (out / "demo-data").mkdir(parents=True)

    # ---------------------------------------------------------------- saving
    def _store(self, content: bytes, ctype: str) -> str:
        ext = {"application/json": ".json", "text/html": ".html", "text/csv": ".csv", "image/jpeg": ".jpg", "image/png": ".png",
               "application/pdf": ".pdf", "text/event-stream": ".txt"}.get(ctype.split(";")[0].strip(), ".bin")
        if ctype.startswith(("application/json", "text/html", "text/event-stream")):
            content = rewrite(content.decode("utf-8"), self.base).encode("utf-8")
        name = hashlib.sha1(content).hexdigest()[:20] + ext
        (self.out / "demo-data" / name).write_bytes(content)
        return name

    def get(self, url: str, required=True):
        """Capture a GET; returns parsed JSON when JSON."""
        key = norm_key(url)
        if key in self.get_map:
            return self.get_map[key].get("_json")
        r = self.client.get(url)
        if r.status_code != 200:
            if required:
                raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:200]}")
            return None
        ctype = r.headers.get("content-type", "application/octet-stream")
        entry = {"f": self._store(r.content, ctype), "t": ctype}
        disp = r.headers.get("content-disposition")
        if disp:
            entry["d"] = disp
        self.get_map[key] = entry
        if ctype.startswith("application/json"):
            entry["_json"] = r.json()
            return entry["_json"]
        return None

    def post(self, key: str, url: str, body=None, method="POST"):
        """Capture a POST answer under an explicit key the hooks know how to build."""
        r = self.client.request(method, url, json=body)
        ctype = r.headers.get("content-type", "application/json")
        self.post_map[key] = {"f": self._store(r.content, ctype), "t": ctype, "s": r.status_code}
        return r

    def put(self, key: str, obj, ctype="application/json"):
        content = obj if isinstance(obj, (bytes, str)) else json.dumps(obj)
        content = content.encode() if isinstance(content, str) else content
        self.post_map[key] = {"f": self._store(content, ctype), "t": ctype, "s": 200}

    def put_get(self, key: str, obj):
        """Store prepared JSON that the browser hooks read with ctx.getJSON(key)."""
        content = json.dumps(obj, separators=(",", ":"), default=str).encode()
        self.get_map[norm_key(key)] = {"f": self._store(content, "application/json"), "t": "application/json"}

    def raw_page(self, url: str, dest: str):
        """Save a server-rendered HTML page (e.g. a demo shop page) as a static file."""
        r = self.client.get(url)
        r.raise_for_status()
        (self.out / dest).parent.mkdir(parents=True, exist_ok=True)
        (self.out / dest).write_text(rewrite(r.text, self.base))
        return r.text

    def login_demo(self):
        r = self.client.post("/api/demo-login")
        r.raise_for_status()
        return r.json()

    # ---------------------------------------------------------------- site files
    def page(self, src: Path, dest: str, needs_api=False):
        """Copy an HTML page with paths rewritten (served by GitHub Pages directly).
        needs_api: the page itself calls the API, so it first makes sure the demo service worker is running."""
        text = rewrite(src.read_text(), self.base)
        if needs_api:
            text = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + ENSURE_SW.replace("__BASE__", self.base), text, count=1)
        (self.out / dest).parent.mkdir(parents=True, exist_ok=True)
        (self.out / dest).write_text(text)

    def finish(self, title: str, hooks_js: str, extra_static=None):
        out, base = self.out, self.base
        # static assets
        shutil.copytree(self.project / "static", out / "static", dirs_exist_ok=True)
        for f in (out / "static").rglob("*"):
            if f.suffix in (".js", ".css", ".html"):
                f.write_text(rewrite(f.read_text(), base))
        # app shell with service-worker boot loader
        index = (self.project / "static" / "index.html").read_text()
        index = rewrite(index, base)
        index = re.sub(r'\s*<script src="[^"]*/static/js/core\.js"></script>\s*<script src="[^"]*/static/js/app\.js"></script>',
                       "\n" + BOOT.replace("__BASE__", base) + "\n", index)
        (out / "index.html").write_text(index)
        (out / "404.html").write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={base}/"><title>{title}</title>')
        for name in ("landing.html", "privacy.html"):
            if (self.project / "static" / name).exists():
                self.page(self.project / "static" / name, name)
        if extra_static:
            for src, dest in extra_static:
                self.page(src, dest, needs_api=True)
        manifest = {"get": {k: {kk: vv for kk, vv in v.items() if kk != "_json"} for k, v in self.get_map.items()}, "post": self.post_map}
        (out / "demo-data" / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
        sw = (HERE / "sw.js").read_text().replace("__BASE__", base).replace("__VERSION__", str(int(time.time())))
        (out / "sw.js").write_text(sw)
        (out / "sw-hooks.js").write_text(hooks_js.replace("__BASE__", base))
        (out / ".nojekyll").write_text("")
        size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
        print(f"Static demo written to {out} ({len(self.get_map)} pages of data, {len(self.post_map)} prepared answers, {size / 1e6:.1f} MB)")


BOOT = """<script>
(function () {
  var B = "__BASE__";
  function load() {
    if (window.__demoLoaded) return; window.__demoLoaded = true;
    ["/static/js/core.js", "/static/js/app.js"].forEach(function (s) { var e = document.createElement("script"); e.src = B + s; e.async = false; document.body.appendChild(e); });
    var pill = document.createElement("div");
    pill.innerHTML = "Clickable demo &middot; sample data";
    pill.style.cssText = "position:fixed;right:12px;bottom:" + (innerWidth < 760 ? 78 : 12) + "px;z-index:9999;background:rgba(17,24,39,.78);color:#fff;font:600 11px/1.4 Inter,system-ui,sans-serif;padding:5px 10px;border-radius:999px;pointer-events:none";
    document.body.appendChild(pill);
  }
  if (!("serviceWorker" in navigator)) { document.getElementById("app").innerHTML = "<p style='padding:40px;text-align:center;font-family:sans-serif'>Please open this demo in Chrome, Edge, Safari or Firefox (not a private window).</p>"; return; }
  if (navigator.serviceWorker.controller) { load(); return; }
  navigator.serviceWorker.addEventListener("controllerchange", load);
  navigator.serviceWorker.register(B + "/sw.js", { scope: B + "/" }).then(function () { if (navigator.serviceWorker.controller) load(); });
})();
</script>"""


ENSURE_SW = """<script>
(function () {
  if (!("serviceWorker" in navigator) || navigator.serviceWorker.controller) return;
  document.documentElement.style.visibility = "hidden";
  navigator.serviceWorker.addEventListener("controllerchange", function () { location.reload(); });
  navigator.serviceWorker.register("__BASE__/sw.js", { scope: "__BASE__/" });
})();
</script>"""


def publish(out: Path, repo_dir: Path, message="Update static demo"):
    """Push the built site to the gh-pages branch of the project's GitHub repo."""
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=repo_dir, text=True).strip()
    work = Path(tempfile.mkdtemp(prefix="ghpages_"))
    shutil.copytree(out, work / "site")
    site = work / "site"
    run = lambda *a: subprocess.run(a, cwd=site, check=True, capture_output=True, text=True)  # noqa: E731
    run("git", "init", "-q", "-b", "gh-pages")
    run("git", "add", "-A")
    run("git", "-c", "user.name=" + subprocess.check_output(["git", "config", "user.name"], text=True).strip(),
        "-c", "user.email=" + subprocess.check_output(["git", "config", "user.email"], text=True).strip(), "commit", "-q", "-m", message)
    run("git", "push", "-q", "-f", remote, "gh-pages")
    shutil.rmtree(work, ignore_errors=True)
    print("Pushed to gh-pages")
