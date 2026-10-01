"""Field definitions per document type and reusable presets."""
import json

from . import db

# key, default column label, kind
FIELDS = {
    "invoice": [
        ("invoice_no", "Invoice No", "text"), ("date", "Date", "date"), ("vendor", "Vendor", "text"),
        ("tax_id", "Tax ID", "text"), ("customer", "Customer", "text"), ("subtotal", "Subtotal", "money"),
        ("discount", "Discount", "money"), ("tax", "Tax", "money"), ("total", "Total", "money"),
        ("currency", "Currency", "text"),
    ],
    "receipt": [
        ("invoice_no", "Receipt No", "text"), ("date", "Date", "date"), ("vendor", "Merchant", "text"),
        ("tax_id", "Tax ID", "text"), ("subtotal", "Subtotal", "money"), ("tax", "Tax", "money"),
        ("total", "Total", "money"), ("currency", "Currency", "text"),
    ],
    "purchase_order": [
        ("invoice_no", "PO Number", "text"), ("date", "PO Date", "date"), ("vendor", "Supplier", "text"),
        ("customer", "Buyer", "text"), ("tax_id", "Tax ID", "text"), ("subtotal", "Subtotal", "money"),
        ("tax", "Tax", "money"), ("total", "Total", "money"), ("currency", "Currency", "text"),
    ],
    "form": [],  # forms are key/value, fields discovered per document
}

REQUIRED = {"invoice": ["invoice_no", "date", "vendor", "total"], "receipt": ["date", "vendor", "total"],
            "purchase_order": ["invoice_no", "date", "vendor", "total"], "form": []}

DOC_TYPE_LABELS = {"invoice": "Invoice", "receipt": "Receipt", "purchase_order": "Purchase order", "form": "Form"}


def default_config(doc_type: str) -> dict:
    return {
        "fields": [{"key": k, "label": label, "enabled": k != "discount" or doc_type == "invoice"}
                   for k, label, _ in FIELDS.get(doc_type, [])],
        "include_line_items": doc_type != "form",
        "date_format": "DD/MM/YYYY",
    }


def seed_presets():
    if db.one("SELECT id FROM presets LIMIT 1"):
        return
    for name, dt, tweak in [
        ("Supplier invoices", "invoice", None),
        ("Courier statements", "invoice", {"vendor": "Courier", "invoice_no": "Statement No", "customer": "Shipper"}),
        ("Purchase orders", "purchase_order", None),
        ("Shop receipts", "receipt", None),
    ]:
        cfg = default_config(dt)
        if tweak:
            for f in cfg["fields"]:
                if f["key"] in tweak:
                    f["label"] = tweak[f["key"]]
                if f["key"] in ("discount", "tax_id") and name == "Courier statements":
                    f["enabled"] = f["key"] == "tax_id"
        db.execute("INSERT INTO presets(name, doc_type, config_json, created_at) VALUES(?,?,?,?)",
                   (name, dt, json.dumps(cfg), db.now()))


def get_preset(preset_id):
    p = db.one("SELECT * FROM presets WHERE id=?", (preset_id,)) if preset_id else None
    if not p:
        return None
    p["config"] = json.loads(p.pop("config_json"))
    return p


def list_presets():
    out = []
    for p in db.query("SELECT * FROM presets ORDER BY id"):
        p["config"] = json.loads(p.pop("config_json"))
        out.append(p)
    return out
