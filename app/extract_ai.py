"""AI extraction with Groq (free tier). Used only when GROQ_API_KEY is set.

Text PDFs  -> text model gets the page text (with layout hints).
Photos / scans -> vision model gets the image plus the OCR text as a hint.
Any failure raises AIError so the caller can fall back to the offline reader.
"""
from __future__ import annotations

import base64
import io
import json
import logging

from .config import GROQ_API_KEY, GROQ_TEXT_MODEL, GROQ_VISION_MODEL
from .extract_rules import parse_date, to_number

log = logging.getLogger("docuflow.ai")

_client = None


class AIError(Exception):
    pass


def _groq():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY, timeout=60, max_retries=2)
    return _client


SYSTEM = """You extract data from business documents (invoices, bills, receipts, purchase orders) for accountants.
Return ONLY a JSON object with exactly these keys:
{
  "vendor": string|null,          // the business that ISSUED the document (seller / supplier)
  "invoice_no": string|null,      // invoice / bill / receipt / PO number exactly as printed
  "date": string|null,            // issue date as YYYY-MM-DD (not the due date)
  "tax_id": string|null,          // seller's NTN / STRN / VAT / tax registration number
  "customer": string|null,        // bill-to / sold-to / buyer name only (no address)
  "subtotal": number|null,
  "discount": number|null,
  "tax": number|null,             // total tax amount (GST / VAT / sales tax)
  "total": number|null,           // the final payable total AS PRINTED, even if it looks wrong
  "currency": string|null,        // ISO code: PKR, USD, AED, EUR... ("Rs" means PKR)
  "line_items": [{"description": string, "quantity": number|null, "unit_price": number|null, "amount": number|null}],
  "unreadable": boolean            // true if the document is too blurry/damaged to read reliably
}
Rules:
- Copy values exactly as printed. Never invent or calculate values that are not printed; use null instead.
- Numbers are plain numbers without commas or currency symbols.
- Text may be in English, Urdu or a mix. Keep names in the script they are printed in.
- Include every line item row from every page, in order."""

FORM_SYSTEM = """You extract data from a filled-in form (registration, admission, application, etc.).
Return ONLY a JSON object: {"fields": {"<field label as printed>": "<value as written>", ...}, "unreadable": boolean}
Copy values exactly; use "" for blank fields. Keep the order of the form."""


def _image_url(img, max_side=1600) -> str:
    im = img.copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _call(model: str, system: str, content) -> dict:
    try:
        resp = _groq().chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:  # network, rate limit, bad JSON...
        log.warning("Groq call failed: %s", e)
        raise AIError(str(e)) from e


def extract(read_result, lines, doc_type: str) -> dict:
    """Returns the same shape as extract_rules.extract: {'fields', 'items', 'conf'}."""
    text = "\n".join(f"[p{ln.page}] " + " | ".join(" ".join(s.text for s in c) for c in ln.cells()) for ln in lines)
    use_vision = read_result.kind in ("photo", "scan")
    system = FORM_SYSTEM if doc_type == "form" else SYSTEM

    if use_vision:
        content = [{"type": "text", "text": "Extract the data from this document. OCR text (may contain errors, use the image as the source of truth):\n" + text[:6000]}]
        content += [{"type": "image_url", "image_url": {"url": _image_url(img)}} for img in read_result.images[:4]]
        data = _call(GROQ_VISION_MODEL, system, content)
    else:
        data = _call(GROQ_TEXT_MODEL, system, "Document text (cells separated by |, page marked [pN]):\n\n" + text[:24000])

    if doc_type == "form":
        f = data.get("fields") or {}
        return {"fields": {str(k): str(v) for k, v in f.items()}, "items": [], "conf": {}, "unreadable": bool(data.get("unreadable"))}

    fields = {}
    for k in ("vendor", "invoice_no", "tax_id", "customer", "currency"):
        v = data.get(k)
        if v not in (None, ""):
            fields[k] = str(v).strip()
    if data.get("date"):
        fields["date"] = parse_date(str(data["date"])) or str(data["date"])
    for k in ("subtotal", "discount", "tax", "total"):
        n = to_number(data.get(k))
        if n is not None:
            fields[k] = n
    if fields.get("currency"):
        fields["currency"] = {"RS": "PKR", "RS.": "PKR", "$": "USD"}.get(fields["currency"].upper(), fields["currency"].upper())
    items = []
    for it in data.get("line_items") or []:
        if not isinstance(it, dict) or not str(it.get("description", "")).strip():
            continue
        items.append({"description": str(it.get("description")).strip(), "quantity": to_number(it.get("quantity")),
                      "unit_price": to_number(it.get("unit_price")), "amount": to_number(it.get("amount"))})
    return {"fields": fields, "items": items, "conf": {}, "unreadable": bool(data.get("unreadable"))}
