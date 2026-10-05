"""Per-field diff against a labelled set.  python -m scripts.diag [samples|realworld] [--ai]"""
import json, os, sys, tempfile, time
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
USE_AI = "--ai" in sys.argv
if not USE_AI:
    os.environ["GROQ_API_KEY"] = ""
else:
    from dotenv import load_dotenv; load_dotenv()
from pathlib import Path
from app import extract_ai, extract_rules
from app.reader import group_lines, read_document
from scripts.evaluate import same, items_ok
BASE = Path(__file__).resolve().parent.parent
which = next((a for a in sys.argv[1:] if not a.startswith("-")), "realworld")
folder = BASE / "sample_data" / ("invoices" if which == "samples" else "realworld")
gt = json.loads(((BASE / "sample_data" / "ground_truth.json") if which == "samples" else folder / "ground_truth.json").read_text())
F = ["vendor", "invoice_no", "date", "tax_id", "customer", "subtotal", "discount", "tax", "total", "currency"]
hit = tot = docs_ok = items_good = 0
for fn, t in gt.items():
    rr = read_document(folder / fn, "diag"); lines = group_lines(rr.pages)
    out = extract_rules.extract(lines, "invoice")
    engine = "offline"
    if USE_AI:
        t0 = time.time()
        try:
            out, engine = extract_ai.merge(extract_ai.extract(rr, lines, "invoice"), out), f"ai {time.time() - t0:.1f}s"
        except extract_ai.AIError as e:
            engine = f"offline (AI failed: {str(e)[:80]})"
    bad = []
    for k in F:
        if k not in t and k != "discount": continue
        want = t.get(k); got = out["fields"].get(k)
        if k == "discount" and not want: continue
        tot += 1
        if same(k, got, want): hit += 1
        else: bad.append(f"{k}: got {got!r} want {want!r}")
    iok = items_ok(out["items"], t["line_items"]); items_good += iok
    if not iok: bad.append(f"items: got {len(out['items'])} {[ (i['description'],i['quantity'],i['amount']) for i in out['items']][:5]} want {len(t['line_items'])}")
    docs_ok += not bad
    print(("OK  " if not bad else "BAD ") + fn + "  [" + engine + "]"); [print("     ", b) for b in bad]
print(f"\nfields {hit}/{tot} = {100*hit/tot:.1f}%   docs fully right {docs_ok}/{len(gt)}   line items right {items_good}/{len(gt)}")
