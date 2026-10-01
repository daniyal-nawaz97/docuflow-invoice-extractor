"""Measure real accuracy and speed on the labelled sample set.

    python -m scripts.evaluate            # uses AI if GROQ_API_KEY is set, else the offline reader
    python -m scripts.evaluate --offline  # force the offline reader

Writes docs/results.md and docs/results.json. Only report numbers produced by this script.
Tip: add your own labelled invoices to sample_data/ground_truth.json to test on more documents.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import os  # noqa: E402

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="docuflow_eval_"))
if "--offline" in sys.argv:
    os.environ["GROQ_API_KEY"] = ""

from app import config  # noqa: E402

if "--offline" in sys.argv:
    config.GROQ_API_KEY = ""
from app import extract_ai, extract_rules, pipeline  # noqa: E402
from app.reader import group_lines, read_document  # noqa: E402

FIELDS = ["vendor", "invoice_no", "date", "tax_id", "customer", "subtotal", "tax", "total", "currency"]


def same(key, got, want):
    if want is None:
        return got in (None, "")
    if got in (None, ""):
        return False
    if isinstance(want, (int, float)):
        try:
            return abs(float(got) - float(want)) < 0.011
        except (TypeError, ValueError):
            return False
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())  # noqa: E731
    return norm(got) == norm(want)


def items_ok(got, want):
    if len(got) != len(want):
        return False
    return all(abs((g.get("amount") or 0) - w["amount"]) < 0.011 and abs((g.get("quantity") or 0) - w["quantity"]) < 0.011 for g, w in zip(got, want))


def main():
    gt = json.loads((BASE / "sample_data" / "ground_truth.json").read_text())
    use_ai = config.ai_enabled()
    rows, field_hits, field_total, t_all = [], 0, 0, 0.0
    per_field = {f: [0, 0] for f in FIELDS}
    caught = {"mismatch": [0, 0], "blurry": [0, 0]}
    for fname, truth in gt.items():
        path = BASE / "sample_data" / "invoices" / fname
        t0 = time.time()
        rr = read_document(path, "eval")
        lines = group_lines(rr.pages)
        out = extract_rules.extract(lines, "invoice")
        engine = "offline"
        if use_ai:
            try:
                ai = extract_ai.extract(rr, lines, "invoice")
                for k, v in out["fields"].items():
                    ai["fields"].setdefault(k, v)
                out, engine = ai, "ai"
            except extract_ai.AIError as e:
                engine = f"offline (AI failed: {str(e)[:40]})"
        dt = time.time() - t0
        t_all += dt
        fields = out["fields"]
        hits = [f for f in FIELDS if same(f, fields.get(f), truth.get(f))]
        for f in FIELDS:
            per_field[f][1] += 1
            per_field[f][0] += f in hits
        field_hits += len(hits); field_total += len(FIELDS)
        # checks that should fire
        loc = {k: pipeline.locate(lines, k, v) for k, v in fields.items() if k != "currency"}
        text_chars = sum(len(s.text) for p in rr.pages for s in p.segments)
        info = {"blurry": rr.sharpness is not None and rr.sharpness < pipeline.BLURRY_THRESHOLD,
                "unreadable": text_chars < 40 or (len(fields) <= 2 and not out["items"])}
        _, _, warnings = pipeline.run_checks("invoice", fields, out["items"], loc, info)
        if "totals_wrong" in fname:
            caught["mismatch"][1] += 1
            caught["mismatch"][0] += any(w["type"] == "mismatch" for w in warnings)
        if "blurry" in fname:
            caught["blurry"][1] += 1
            caught["blurry"][0] += any(w["type"] == "quality" for w in warnings)
        rows.append({"file": fname, "kind": rr.kind, "engine": engine, "fields_correct": len(hits), "fields_total": len(FIELDS),
                     "missed": [f for f in FIELDS if f not in hits], "items_correct": items_ok(out["items"], truth["line_items"]),
                     "items": f"{len(out['items'])}/{len(truth['line_items'])}", "seconds": round(dt, 2)})

    n = len(rows)
    # the deliberately blurry photo is expected to fail extraction; report accuracy with and without it
    readable = [r for r in rows if "blurry" not in r["file"]]
    fully = sum(r["fields_correct"] == r["fields_total"] and r["items_correct"] for r in rows)
    fully_readable = sum(r["fields_correct"] == r["fields_total"] and r["items_correct"] for r in readable)
    acc_readable = sum(r["fields_correct"] for r in readable) / max(1, sum(r["fields_total"] for r in readable))
    summary = {
        "date": date.today().isoformat(), "engine": "AI (Groq) + offline fallback" if use_ai else "Offline reader (no AI)",
        "documents": n, "field_accuracy_all": round(field_hits / field_total * 100, 1),
        "field_accuracy_readable": round(acc_readable * 100, 1),
        "documents_fully_correct": fully, "documents_fully_correct_readable": f"{fully_readable}/{len(readable)}",
        "line_items_correct_docs": sum(r["items_correct"] for r in rows),
        "avg_seconds_per_doc": round(t_all / n, 2), "total_seconds": round(t_all, 1),
        "manual_minutes_estimate": n * config.MANUAL_MINUTES_PER_DOC,
        "totals_mismatch_caught": f"{caught['mismatch'][0]}/{caught['mismatch'][1]}",
        "blurry_photo_flagged": f"{caught['blurry'][0]}/{caught['blurry'][1]}",
        "per_field_accuracy": {f: round(a / t * 100, 1) for f, (a, t) in per_field.items()},
        "cost_per_invoice": "0 (offline)" if not use_ai else "0 on Groq free tier (paid tier: fractions of a cent)",
    }
    payload = json.dumps({"summary": summary, "documents": rows}, indent=2)
    (BASE / "docs" / "results.json").write_text(payload)
    (BASE / "static" / "results.json").write_text(payload)  # shown on the landing page

    md = [f"# Measured results ({summary['date']})", "",
          f"Engine: **{summary['engine']}**. Test set: {n} fictitious sample documents in `sample_data/` "
          "(clean PDFs, a multi-page invoice, an Urdu-English bill, phone photos, a scanned PDF, a blurry photo, "
          "an invoice with wrong totals and a duplicate).", "",
          "| Metric | Result |", "|---|---|",
          f"| Field accuracy (all {n} documents) | **{summary['field_accuracy_all']}%** |",
          f"| Field accuracy (excluding the deliberately blurry photo) | **{summary['field_accuracy_readable']}%** |",
          f"| Documents 100% correct with no edits | {fully}/{n} |",
          f"| Line items fully correct | {summary['line_items_correct_docs']}/{n} documents |",
          f"| Average processing time | {summary['avg_seconds_per_doc']} s per document |",
          f"| Whole set | {summary['total_seconds']} s (vs about {summary['manual_minutes_estimate']:.0f} min typing by hand at {config.MANUAL_MINUTES_PER_DOC:g} min each) |",
          f"| Wrong totals caught | {summary['totals_mismatch_caught']} |",
          f"| Blurry photo flagged for review | {summary['blurry_photo_flagged']} |",
          "| Duplicate detected | checked in the app on batch level (see summary screen) |",
          f"| Cost per invoice | {summary['cost_per_invoice']} |", "",
          "## Per-field accuracy", "", "| Field | Accuracy |", "|---|---|"]
    md += [f"| {f} | {a}% |" for f, a in summary["per_field_accuracy"].items()]
    md += ["", "## Per document", "", "| File | Type | Fields correct | Line items | Missed | Seconds |", "|---|---|---|---|---|---|"]
    md += [f"| {r['file']} | {r['kind']} | {r['fields_correct']}/{r['fields_total']} | {r['items']} {'✓' if r['items_correct'] else '✗'} | {', '.join(r['missed']) or '-'} | {r['seconds']} |" for r in rows]
    md += ["", "_Honest note: this is a small, synthetic test set. Before quoting numbers to a client, run the same script on "
           "20-50 of their real documents (add them with correct answers to `ground_truth.json`)._"]
    (BASE / "docs" / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:18]))


if __name__ == "__main__":
    main()
