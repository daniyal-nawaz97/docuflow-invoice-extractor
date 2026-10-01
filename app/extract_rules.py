"""Offline, rule-based extraction (works with no internet and no API key).

Finds header fields by their labels ("Invoice No", "Date", "NTN", "Grand Total"...)
and reads line items from rows that look like: description  qty  unit price  amount.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .reader import Line

AMOUNT = r"(?:PKR|Rs\.?|USD|US\$|\$|AED|EUR|€|£)?\s*(-?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?)"
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
DATE_PATTERNS = [
    r"\d{4}-\d{1,2}-\d{1,2}",
    r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}",
    rf"\d{{1,2}}\s*(?:{MONTHS})[a-z]*\.?,?\s*\d{{4}}",
    rf"(?:{MONTHS})[a-z]*\.?\s*\d{{1,2}},?\s*\d{{4}}",
]
DATE_RE = re.compile("|".join(f"(?:{p})" for p in DATE_PATTERNS), re.I)

LABELS = {
    "invoice_no": r"(?:tax\s*)?invoice\s*(?:no\.?|number|num|#)|inv\.?\s*(?:no\.?|#)|bill\s*(?:no\.?|number|#)|receipt\s*(?:no\.?|#|number)|"
                  r"p\.?o\.?\s*(?:no\.?|number|#)|purchase\s*order\s*(?:no\.?|#)|order\s*(?:no\.?|#)|challan\s*(?:no\.?|#)|statement\s*no\.?|ref(?:erence)?\s*no\.?",
    "date": r"(?:invoice|bill|receipt|po|order)?\s*date|dated|date\s*of\s*issue",
    "tax_id": r"ntn|strn(?:\s*/\s*tax\s*id)?|tax\s*id|gst\s*no\.?|vat\s*(?:no\.?|reg(?:istration)?)|trn|tax\s*reg(?:istration)?\s*no\.?",
    "customer": r"bill\s*to|billed\s*to|sold\s*to|customer|buyer|ship\s*to|client",
    "subtotal": r"sub\s*-?\s*total|total\s*before\s*tax|amount\s*before\s*tax|net\s*amount|taxable\s*amount",
    "discount": r"discount|less\s*discount",
    "tax": r"(?:sales\s*tax|gst|vat|tax)\s*(?:@\s*)?(?:\d{1,2}(?:\.\d+)?\s*%)?",
    "total": r"grand\s*total|total\s*amount|amount\s*due|total\s*due|net\s*payable|balance\s*due|amount\s*payable|total",
}
NOT_VENDOR = re.compile(r"^(tax\s*)?(invoice|bill|receipt|sales\s*invoice|purchase\s*order|statement|bill\s*of\s*services|page\s*\d+)$", re.I)


def respace(text: str) -> str:
    """Put back spaces OCR sometimes drops: 'GreenValley' -> 'Green Valley', 'Sugar50kg' -> 'Sugar 50kg'."""
    if not text:
        return text
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    t = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z]{2,})", " ", t)
    t = re.sub(r"(?<=[A-Za-z]{3})(?=\d)", " ", t)
    t = re.sub(r"(?<=\d)(?=[A-Z][a-z]{2,})", " ", t)
    t = re.sub(r"(?<=[,:;])(?=\S)", " ", t)
    t = re.sub(r"\(\s*", "(", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def to_number(s) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    t = re.sub(r"(?i)pkr|rs\.?|usd|us\$|aed|eur|[$€£]", "", t).strip()
    t = t.replace("O", "0").replace("o", "0") if re.fullmatch(r"[\dOo,.\s-]+", t) else t
    t = re.sub(r"(?<=\d)[\s,](?=\d{3}\b)", "", t)
    t = t.replace(",", "")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def parse_date(s: str) -> str | None:
    if not s:
        return None
    t = re.sub(r"\s+", " ", s.strip().replace(",", ", ")).strip()
    t = re.sub(r"(?i)(\d)([a-z])", r"\1 \2", t)
    t = re.sub(r"(?i)([a-z])(\d)", r"\1 \2", t)
    t = re.sub(r"\s+,", ",", t).replace("Sept ", "Sep ")
    fmts = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y",
            "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%d %b, %Y", "%d %B, %Y"]
    for f in fmts:
        try:
            d = datetime.strptime(t, f).date()
            if 1990 <= d.year <= 2100:
                return d.isoformat()
        except ValueError:
            continue
    return None


def _cells_text(line: Line) -> list[str]:
    return [" ".join(s.text for s in c) for c in line.cells()]


def _find_labeled(lines: list[Line], label_re: str, value_re: str, look_below=True):
    """Return (value, line) for the first 'Label: value' match, also checking the cell to the right and the line below."""
    lab = re.compile(rf"(?i)(?<![a-z])(?:{label_re})\s*[:#.\-]?\s*")
    val = re.compile(value_re, re.I)
    for i, ln in enumerate(lines):
        cell_segs = ln.cells()
        cells = [" ".join(s.text for s in c) for c in cell_segs]
        for ci, cell in enumerate(cells):
            m = lab.search(cell)
            if not m or m.start() > 2:
                continue
            rest = cell[m.end():].strip()
            v = val.search(rest) if rest else None
            if v and v.start() <= 2:
                return v.group(0).strip(), ln
            if ci + 1 < len(cells) and not rest:
                v = val.match(cells[ci + 1].strip())
                if v:
                    return v.group(0).strip(), ln
            if look_below and not rest and i + 1 < len(lines) and lines[i + 1].page == ln.page:
                nxt = lines[i + 1]
                lx0 = cell_segs[ci][0].box[0]
                lx1 = cell_segs[ci][-1].box[2]
                # value directly below, horizontally overlapping the label cell
                below = [c for c in nxt.cells() if c[0].box[0] < lx1 + 20 and c[-1].box[2] > lx0 - 20]
                if below:
                    v = val.match(" ".join(s.text for s in below[0]).strip())
                    if v:
                        return v.group(0).strip(), nxt
    return None, None


def _amount_on_line(lines, label_re, exclude_re=None, last=False):
    lab = re.compile(rf"(?i)^\s*(?:{label_re})(?![a-z])")
    amt = re.compile(AMOUNT + r"\s*$")
    found = None
    for ln in lines:
        for ci, cell in enumerate(_cells_text(ln)):
            if not lab.search(cell) or (exclude_re and re.search(exclude_re, cell, re.I)):
                continue
            tail = " ".join(_cells_text(ln)[ci:])
            label_m = lab.search(tail)
            m = amt.search(tail[label_m.end():]) if label_m else None
            if m:
                found = (to_number(m.group(1)), ln)
                if not last:
                    return found
    return found or (None, None)


def _vendor(lines: list[Line]):
    first_page = [ln for ln in lines if ln.page == 1]
    if not first_page:
        return None, None
    top = first_page[0].box[1]
    page_h = max(ln.box[3] for ln in first_page) - top + 1
    candidates = []
    for ln in first_page:
        if ln.box[1] - top > page_h * 0.3:
            break
        for cell in ln.cells():
            big = max(s.size for s in cell)
            cell = [s for s in cell if not (len(s.text) == 1 and s.size < big * 0.8)] or cell  # drop logo letters
            text = " ".join(s.text for s in cell).strip()
            if len(text) < 3 or NOT_VENDOR.match(text) or re.search(r"\d{3,}|phone|tel|@|www\.", text, re.I):
                continue
            if len(text) == 1 or re.fullmatch(r"[A-Z]", text):
                continue
            size = max(s.size for s in cell)
            candidates.append((size, -ln.box[1], text, ln))
    from_label, ln = _find_labeled(lines, r"from|supplier|vendor|seller", r".{3,60}")
    if from_label:
        return respace(from_label), ln
    if not candidates:
        return None, None
    best = max(candidates, key=lambda c: (round(c[0]), c[1]))
    return respace(best[2]), best[3]


ITEM_RE = re.compile(
    r"^(?P<desc>.*?[A-Za-z].*?)\s+(?P<qty>\d+(?:\.\d+)?)\s+" + r"(?:PKR|Rs\.?|\$)?\s*(?P<unit>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s+"
    + r"(?:PKR|Rs\.?|\$)?\s*(?P<amt>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*$")
HEADER_RE = re.compile(r"(?i)description|item|particulars|product")
STOP_RE = re.compile(r"(?i)^\s*(sub\s*-?\s*total|total|grand|discount|gst|vat|sales\s*tax|tax\b|amount\s*due|net\s*payable)")


def _line_items(lines: list[Line]):
    items, in_table = [], False
    for ln in lines:
        text = ln.text
        if HEADER_RE.search(text) and re.search(r"(?i)qty|quantity", text):
            in_table = True
            continue
        if STOP_RE.search(text):
            in_table = False
            continue
        m = ITEM_RE.match(text)
        if not m:
            continue
        qty, unit, amt = to_number(m["qty"]), to_number(m["unit"]), to_number(m["amt"])
        consistent = qty is not None and unit is not None and amt is not None and abs(qty * unit - amt) < 0.02 * max(1, amt)
        if not (in_table or consistent):
            continue
        items.append({"description": respace(m["desc"].strip(" -|:")), "quantity": qty, "unit_price": unit, "amount": amt,
                      "_conf": ln.conf, "_page": ln.page, "_box": ln.box, "_math_ok": consistent})
    return items


def detect_currency(text: str, default: str) -> str:
    if re.search(r"\bUSD\b|US\$", text):
        return "USD"
    if re.search(r"\bAED\b", text):
        return "AED"
    if re.search(r"\bEUR\b|€", text):
        return "EUR"
    if re.search(r"\bPKR\b|\bRs\.?\s*\d", text):
        return "PKR"
    if "$" in text:
        return "USD"
    return default


def extract_key_values(lines: list[Line]):
    """For free-form documents (forms): every 'Label: value' pair."""
    out = {}
    for ln in lines:
        cells = _cells_text(ln)
        for i, cell in enumerate(cells):
            m = re.match(r"^([A-Za-z][A-Za-z /().#-]{1,40}?)\s*:\s*(.+)$", cell)
            if m:
                out.setdefault(respace(m[1]).strip(), (respace(m[2].strip()), ln))
            elif cell.endswith(":") and i + 1 < len(cells):
                out.setdefault(respace(cell[:-1]).strip(), (respace(cells[i + 1].strip()), ln))
    return out


def extract(lines: list[Line], doc_type: str, default_currency: str = "PKR") -> dict:
    """Returns {'fields': {key: value}, 'items': [...], 'conf': {key: 0..1}}."""
    fields, conf = {}, {}
    all_text = "\n".join(ln.text for ln in lines)

    if doc_type == "form":
        kv = extract_key_values(lines)
        return {"fields": {k: v for k, (v, _) in kv.items()}, "items": [],
                "conf": {k: ln.conf for k, (_, ln) in kv.items()}}

    v, ln = _find_labeled(lines, LABELS["invoice_no"], r"[A-Z0-9][A-Z0-9\-/_.]{2,24}")
    if v and not DATE_RE.fullmatch(v):
        fields["invoice_no"], conf["invoice_no"] = v.rstrip("."), ln.conf

    v, ln = _find_labeled(lines, r"(?:invoice|bill|receipt|po|order)\s*date|date\s*of\s*issue", DATE_RE.pattern)
    if not v:
        v, ln = _find_labeled(lines, r"(?<!due\s)(?<!due)(?:dated|date)", DATE_RE.pattern)
    if v:
        iso = parse_date(v)
        fields["date"] = iso or v
        conf["date"] = ln.conf if iso else 0.5

    v, ln = _vendor(lines)
    if v:
        fields["vendor"], conf["vendor"] = v, ln.conf

    v, ln = _find_labeled(lines, LABELS["tax_id"], r"[A-Z0-9][A-Z0-9\-]{4,20}")
    if v:
        fields["tax_id"], conf["tax_id"] = v, ln.conf

    v, ln = _find_labeled(lines, LABELS["customer"], r"[A-Za-z][A-Za-z0-9&.,'()\- ]{2,60}")
    if v and not re.match(r"(?i)^(name|address|details)$", v):
        fields["customer"], conf["customer"] = respace(v), ln.conf

    for key, excl in (("subtotal", None), ("discount", None),
                      ("tax", r"(?i)tax\s*(id|no|reg)|ntn|strn|before\s*tax"),
                      ("total", r"(?i)sub\s*-?\s*total|total\s*before|qty")):
        val, ln = _amount_on_line(lines, LABELS[key], excl, last=(key == "total"))
        if key == "total":
            # prefer the strongest total label when several exist
            for strong in (r"grand\s*total", r"total\s*amount|amount\s*due|net\s*payable|total\s*due|balance\s*due"):
                sv, sln = _amount_on_line(lines, strong, excl, last=True)
                if sv is not None:
                    val, ln = sv, sln
                    break
        if val is not None:
            fields[key], conf[key] = val, ln.conf

    fields["currency"] = detect_currency(all_text, default_currency)
    conf["currency"] = 0.95 if re.search(r"PKR|Rs|USD|\$|AED|EUR", all_text) else 0.6

    items = _line_items(lines)
    return {"fields": fields, "items": items, "conf": conf}


def today_iso() -> str:
    return date.today().isoformat()
