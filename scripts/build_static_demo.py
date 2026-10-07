"""Build the clickable demo (static site for GitHub Pages) from the real app and its demo data.

    python -m scripts.build_static_demo            # writes site/
    python -m scripts.build_static_demo --publish  # also pushes it to the gh-pages branch

The 19 sample invoices are processed once by the real app; every screen is saved. "Try with sample invoices"
replays that batch with live progress, and approving / flagging / editing documents is remembered in the
visitor's browser. Uploading your own files needs the live version.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "static_demo"))
from static_demo import Server, Site, publish  # noqa: E402

REPO = "docuflow-invoice-extractor"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()

    # offline extraction, the same engine the measured results use
    with Server(ROOT, a.port, {"GROQ_API_KEY": ""}) as srv:
        s = Site(ROOT, Path(a.out), REPO, srv)
        login = s.login_demo()
        bid = login["sample_batch"]
        for _ in range(300):
            if s.client.get(f"/api/batches/{bid}").json()["batch"]["status"] == "done":
                break
            time.sleep(2)
        else:
            raise RuntimeError("sample batch did not finish")
        s.post("POST /api/demo-login", "/api/demo-login")
        for u in ("/api/app-info", "/api/me", "/api/settings", "/api/presets", "/api/team", "/api/batches"):
            s.get(u)
        s.put_get("/api/_demo/sample", {"id": bid})
        for b in s.get("/api/batches"):
            batch = s.get(f"/api/batches/{b['id']}")
            for fmt in ("xlsx", "csv"):
                s.get(f"/api/batches/{b['id']}/export?format={fmt}")
            s.get(f"/api/batches/{b['id']}/export?format=csv&sheet=line_items")
            for d in batch["documents"]:
                doc = s.get(f"/api/documents/{d['id']}")
                s.get(f"/api/documents/{d['id']}/original", required=False)
                for p in doc["pages"]:
                    s.get(f"/api/documents/{d['id']}/pages/{p['n']}", required=False)
        hooks = (Path(__file__).resolve().parent / "static_demo" / "hooks.js").read_text()
        s.finish("DocuFlow demo", hooks)
    if a.publish:
        publish(Path(a.out), ROOT)


if __name__ == "__main__":
    main()
