"""Processing pipeline: read -> extract -> locate -> check -> save."""
from __future__ import annotations

import json
import logging
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db, extract_ai, extract_rules
from .config import WORKERS, ai_enabled
from .presets import FIELDS, REQUIRED
from .reader import UnreadableDocument, group_lines, read_document

log = logging.getLogger("docuflow.pipeline")
executor = ThreadPoolExecutor(max_workers=WORKERS)

MONEY_KEYS = {"subtotal", "discount", "tax", "total"}
BLURRY_THRESHOLD = 60.0
LOW_CONF = 0.85


# --------------------------------------------------------------------------- locating values on the page
def _norm_map(line):
    chars, owners = [], []
    for i, s in enumerate(line.segments):
        for ch in s.text.lower():
            if ch.isalnum():
                chars.append(ch); owners.append(i)
    return "".join(chars), owners


def _union(segs):
    return [round(min(s.box[0] for s in segs), 1), round(min(s.box[1] for s in segs), 1),
            round(max(s.box[2] for s in segs), 1), round(max(s.box[3] for s in segs), 1)]


def _numbers_in(text):
    return [extract_rules.to_number(m) for m in re.findall(r"\d[\d,]*(?:\.\d{1,2})?", text)]


def locate(lines, key, value, hint_line=None, prefer_last=False):
    """Find where a value is printed. Returns (page, box, conf) or None."""
    if value in (None, ""):
        return None
    ordered = ([hint_line] if hint_line is not None else []) + (list(reversed(lines)) if prefer_last else lines)
    if key in MONEY_KEYS or isinstance(value, (int, float)):
        target = round(float(value), 2)
        for ln in ordered:
            for s in reversed(ln.segments) if prefer_last else ln.segments:
                if target in _numbers_in(s.text.replace(" ", "")):
                    return ln.page, _union([s]), s.conf
        return None
    if key == "date":
        for ln in ordered:
            for m in extract_rules.DATE_RE.finditer(ln.text):
                if extract_rules.parse_date(m.group(0)) == value:
                    return ln.page, _span_box(ln, m.start(), m.end()), ln.conf
        needle = re.sub(r"[^a-z0-9]", "", str(value).lower())
    else:
        needle = re.sub(r"[^a-z0-9]", "", str(value).lower())
    if len(needle) < 2:
        return None
    for ln in ordered:
        hay, owners = _norm_map(ln)
        i = hay.find(needle)
        if i >= 0:
            segs = [ln.segments[j] for j in sorted(set(owners[i:i + len(needle)]))]
            return ln.page, _union(segs), min(s.conf for s in segs)
    return None


def _span_box(line, start, end):
    pos, segs = 0, []
    for s in line.segments:
        a, b = pos, pos + len(s.text)
        if b > start and a < end:
            segs.append(s)
        pos = b + 1
    return _union(segs or line.segments)


# --------------------------------------------------------------------------- checks
def fmt_money(v):
    return f"{v:,.2f}"


def run_checks(doc_type, fields, items, loc, read_info):
    """Return (checks per field, item checks, document warnings)."""
    checks, warnings = {}, []
    keys = [k for k, _, _ in FIELDS.get(doc_type, [])] or list(fields.keys())
    required = REQUIRED.get(doc_type, [])
    for k in keys:
        v = fields.get(k)
        c = {"status": "ok", "reason": ""}
        if k in loc and loc[k]:
            c["page"], c["box"], conf = loc[k]
        else:
            conf = None
        if v in (None, ""):
            if k in ("discount",):
                c = {"status": "empty", "reason": ""}
            elif k in required:
                c = {"status": "error", "reason": "Not found. Please type it in."}
            else:
                c = {"status": "warn", "reason": "Not found on the document."}
        elif k == "currency":
            pass
        elif conf is None:
            c.update(status="warn", reason="Couldn't confirm this on the page. Please check.")
        elif conf < LOW_CONF:
            c.update(status="warn", reason="Hard to read. Please check.")
        if k == "date" and v:
            try:
                d = date.fromisoformat(str(v))
                if d > date.today() + timedelta(days=60) or d.year < 2000:
                    c.update(status="warn", reason="Unusual date. Please check.")
            except ValueError:
                c.update(status="warn", reason="Date format not recognised.")
        checks[k] = c

    item_checks = []
    for it in items:
        ic = {"status": "ok", "reason": ""}
        q, u, a = it.get("quantity"), it.get("unit_price"), it.get("amount")
        if a is None:
            ic = {"status": "warn", "reason": "Amount missing"}
        elif q is not None and u is not None and abs(q * u - a) > max(0.05, 0.005 * a):
            ic = {"status": "warn", "reason": f"{q:g} × {fmt_money(u)} = {fmt_money(q * u)}, not {fmt_money(a)}"}
        elif it.get("_conf", 1) < LOW_CONF:
            ic = {"status": "warn", "reason": "Hard to read. Please check."}
        item_checks.append(ic)

    sub, disc, tax, tot = (fields.get(k) for k in ("subtotal", "discount", "tax", "total"))
    amounts = [it["amount"] for it in items if it.get("amount") is not None]
    if amounts and sub is not None and abs(sum(amounts) - sub) > 1:
        checks.setdefault("subtotal", {}).update(status="error", reason=f"Line items add up to {fmt_money(sum(amounts))}, not {fmt_money(sub)}")
        warnings.append({"type": "mismatch", "text": f"Line items add up to {fmt_money(sum(amounts))} but the subtotal says {fmt_money(sub)}."})
    base = sub if sub is not None else (sum(amounts) if amounts else None)
    if base is not None and tot is not None:
        expected = round(base - (disc or 0) + (tax or 0), 2)
        if abs(expected - tot) > 1:
            checks.setdefault("total", {}).update(status="error", reason=f"Subtotal + tax = {fmt_money(expected)}, but total says {fmt_money(tot)}")
            warnings.append({"type": "mismatch", "text": f"Totals do not add up: expected {fmt_money(expected)}, printed {fmt_money(tot)}."})

    if read_info.get("blurry"):
        warnings.append({"type": "quality", "text": "This photo is blurry, so some values may be wrong. Try a clearer picture if you can."})
    if read_info.get("unreadable"):
        warnings.append({"type": "quality", "text": "We could hardly read this document. Please type the values, or upload a clearer copy."})
    if read_info.get("fallback"):
        warnings.append({"type": "info", "text": "AI reading was unavailable, so the basic reader was used. Please check values."})
    return checks, item_checks, warnings


def doc_status(checks, item_checks, warnings):
    bad = any(c.get("status") in ("warn", "error") for c in checks.values()) or \
        any(c["status"] != "ok" for c in item_checks) or any(w["type"] in ("mismatch", "quality", "duplicate") for w in warnings)
    return "needs_review" if bad else "done"


# --------------------------------------------------------------------------- processing
def _set_doc(doc_id, **cols):
    sets = ", ".join(f"{k}=?" for k in cols)
    db.execute(f"UPDATE documents SET {sets} WHERE id=?", (*cols.values(), doc_id))


def process_document(doc: dict, doc_type: str, default_currency: str):
    t0 = time.time()
    doc_id = doc["id"]
    try:
        _set_doc(doc_id, status="processing", stage="reading")
        rr = read_document(Path(doc["stored_path"]), doc_id)
        lines = group_lines(rr.pages)
        _set_doc(doc_id, stage="extracting", kind=rr.kind)

        engine, fallback = "rules", False
        rules_out = extract_rules.extract(lines, doc_type, default_currency)
        out = rules_out
        if ai_enabled():
            try:
                out = extract_ai.extract(rr, lines, doc_type)
                engine = "ai"
                # AI rarely misses values the rules found with certainty; fill gaps from the rules
                for k, v in rules_out["fields"].items():
                    out["fields"].setdefault(k, v)
            except extract_ai.AIError:
                fallback = True

        fields, items = out["fields"], out["items"]
        text_chars = sum(len(s.text) for p in rr.pages for s in p.segments)
        read_info = {
            "blurry": rr.sharpness is not None and rr.sharpness < BLURRY_THRESHOLD,
            "unreadable": out.get("unreadable") or text_chars < 40 or (len(fields) <= 2 and not items),
            "fallback": fallback,
        }

        # locate every value on the page (for the highlight boxes) using rules' hint lines when they agree
        loc = {}
        for k, v in fields.items():
            if k == "currency":
                continue
            prefer_last = k in ("total", "tax", "subtotal", "discount")
            loc[k] = locate(lines, k, v, prefer_last=prefer_last)
        for it in items:
            if "_box" in it:
                it["page"], it["box"] = it.pop("_page"), [round(x, 1) for x in it.pop("_box")]
            else:
                hit = locate(lines, "description", it["description"])
                if hit:
                    it["page"], it["box"], it["_conf"] = hit

        checks, item_checks, warnings = run_checks(doc_type, fields, items, loc, read_info)
        for it, ic in zip(items, item_checks):
            it["check"] = ic
            for k in [k for k in it if k.startswith("_")]:
                it.pop(k)
        pages = [{"n": p.n, "w": p.width, "h": p.height, "source": p.source} for p in rr.pages]
        status = doc_status(checks, item_checks, warnings)
        _set_doc(doc_id, status=status, stage="done", engine=engine, pages_json=json.dumps(pages),
                 fields_json=json.dumps(fields), items_json=json.dumps(items), checks_json=json.dumps(checks),
                 warnings_json=json.dumps(warnings), error=None, processing_ms=int((time.time() - t0) * 1000))
    except UnreadableDocument as e:
        _set_doc(doc_id, status="failed", stage="done", error=str(e), processing_ms=int((time.time() - t0) * 1000),
                 fields_json="{}", items_json="[]", checks_json="{}", warnings_json="[]", pages_json="[]")
    except Exception:
        log.error("Processing failed for %s\n%s", doc["filename"], traceback.format_exc())
        _set_doc(doc_id, status="failed", stage="done", error="Something went wrong reading this file. Please try uploading it again.",
                 processing_ms=int((time.time() - t0) * 1000), fields_json="{}", items_json="[]", checks_json="{}",
                 warnings_json="[]", pages_json="[]")


def _dup_key(fields):
    vendor = re.sub(r"[^a-z0-9]", "", str(fields.get("vendor", "")).lower())
    inv = re.sub(r"[^a-z0-9]", "", str(fields.get("invoice_no", "")).lower())
    return (vendor, inv) if vendor and inv else None


def find_duplicates(batch_id):
    """Flag documents whose vendor + invoice number match an earlier document (this batch or earlier batches)."""
    docs = db.query("SELECT d.id, d.filename, d.fields_json, d.warnings_json, d.status, d.batch_id, b.name AS batch_name, b.created_at, d.position "
                    "FROM documents d JOIN batches b ON b.id=d.batch_id WHERE d.status!='failed' "
                    "AND (d.batch_id=? OR (b.is_sample=0 AND (SELECT is_sample FROM batches WHERE id=?)=0)) "
                    "ORDER BY b.created_at, d.position", (batch_id, batch_id))
    seen = {}
    for d in docs:
        key = _dup_key(json.loads(d["fields_json"] or "{}"))
        if not key:
            continue
        if key in seen and d["batch_id"] == batch_id:
            first = seen[key]
            where = "in this batch" if first["batch_id"] == batch_id else f"in batch “{first['batch_name']}”"
            warnings = [w for w in json.loads(d["warnings_json"] or "[]") if w["type"] != "duplicate"]
            warnings.insert(0, {"type": "duplicate", "text": f"Possible duplicate of {first['filename']} ({where}).", "of": first["id"]})
            status = d["status"] if d["status"] in ("approved", "skipped", "flagged") else "needs_review"
            db.execute("UPDATE documents SET warnings_json=?, status=? WHERE id=?", (json.dumps(warnings), status, d["id"]))
        else:
            seen.setdefault(key, d)


def process_batch(batch_id: str):
    t0 = time.time()
    batch = db.one("SELECT * FROM batches WHERE id=?", (batch_id,))
    settings = db.get_settings()
    docs = db.query("SELECT * FROM documents WHERE batch_id=? ORDER BY position", (batch_id,))
    db.execute("UPDATE batches SET status='processing' WHERE id=?", (batch_id,))
    futures = [executor.submit(process_document, d, batch["doc_type"], settings.get("default_currency", "PKR")) for d in docs]
    for f in futures:
        f.result()
    find_duplicates(batch_id)
    db.execute("UPDATE batches SET status='done', finished_at=?, processing_ms=? WHERE id=?",
               (db.now(), int((time.time() - t0) * 1000), batch_id))


def start_batch(batch_id: str):
    import threading
    threading.Thread(target=process_batch, args=(batch_id,), daemon=True).start()


def recheck_document(doc_id: str):
    """Re-run the checks after a person edits values (boxes are kept)."""
    d = db.one("SELECT d.*, b.doc_type FROM documents d JOIN batches b ON b.id=d.batch_id WHERE d.id=?", (doc_id,))
    fields = json.loads(d["fields_json"] or "{}")
    items = json.loads(d["items_json"] or "[]")
    old = json.loads(d["checks_json"] or "{}")
    loc = {k: (c.get("page"), c.get("box"), 1.0) if c.get("box") else None for k, c in old.items()}
    # values a person typed are trusted: mark them located
    edited = set(json.loads(d["checks_json"] or "{}").get("_edited", {}).get("keys", []))
    for k in edited:
        loc[k] = loc.get(k) or (None, None, 1.0)
    warnings = [w for w in json.loads(d["warnings_json"] or "[]") if w["type"] in ("duplicate", "quality", "info")]
    checks, item_checks, new_w = run_checks(d["doc_type"], fields, items, loc, {})
    for k in edited:
        if checks.get(k, {}).get("status") == "warn":
            checks[k] = {**checks[k], "status": "ok", "reason": "Edited by reviewer"}
    for it, ic in zip(items, item_checks):
        it["check"] = ic
    checks["_edited"] = {"keys": sorted(edited)}
    return fields, items, checks, warnings + new_w


def apply_retention():
    """Delete stored files older than the privacy setting."""
    from .config import PAGES_DIR
    ret = db.get_settings().get("retention", "30d")
    days = {"immediate": 0, "7d": 7, "30d": 30}.get(ret, 30)
    if days == 0:
        return  # 'immediate' deletes files right after export (see the export route)
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    for b in db.query("SELECT id, created_at, finished_at FROM batches WHERE status='done' AND is_sample=0"):
        if datetime.fromisoformat(b["finished_at"] or b["created_at"]) < cutoff:
            delete_batch_files(b["id"])


def delete_batch_files(batch_id: str):
    """Remove the original files and page images; extracted data stays for the history."""
    from .config import PAGES_DIR
    for d in db.query("SELECT id, stored_path FROM documents WHERE batch_id=? AND stored_path IS NOT NULL", (batch_id,)):
        Path(d["stored_path"]).unlink(missing_ok=True)
        for p in PAGES_DIR.glob(f"{d['id']}_*.jpg"):
            p.unlink(missing_ok=True)
        db.execute("UPDATE documents SET stored_path=NULL WHERE id=?", (d["id"],))
