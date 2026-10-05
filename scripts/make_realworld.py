"""Held-out test set: 12 invoices in layouts the offline rules were NOT built around.

    python -m scripts.make_realworld     # writes sample_data/realworld/*.pdf|.jpg + ground_truth.json
    python -m scripts.evaluate --set realworld

Different label wording, column orders, number formats and table styles than sample_data/invoices.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "sample_data" / "realworld"


def money(v, style="comma"):
    if style == "plain":
        return f"{v:.2f}"
    if style == "int":
        return f"{v:,.0f}"
    if style == "rs":
        return f"Rs. {v:,.2f}"
    return f"{v:,.2f}"


def table(c, x, y, cols, widths, rows, aligns, header_fill=None, grid=False, size=9):
    h = 16
    if header_fill:
        c.setFillColor(header_fill); c.rect(x, y - 4, sum(widths), h, stroke=0, fill=1); c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", size)
    cx = x
    for col, w, a in zip(cols, widths, aligns):
        (c.drawRightString(cx + w - 4, y, col) if a == "r" else c.drawString(cx + 4, y, col)); cx += w
    c.setFillColor(colors.black); c.setFont("Helvetica", size)
    for r in rows:
        y -= h
        cx = x
        for v, w, a in zip(r, widths, aligns):
            (c.drawRightString(cx + w - 4, y, str(v)) if a == "r" else c.drawString(cx + 4, y, str(v))); cx += w
        if grid:
            c.setStrokeColor(colors.lightgrey); c.line(x, y - 4, x + sum(widths), y - 4); c.setStrokeColor(colors.black)
    return y - h


def items_of(spec):
    out = []
    for d, q, u in spec:
        out.append({"description": d, "quantity": q, "unit_price": u, "amount": round(q * u, 2)})
    return out


def doc(name, vendor, inv, date_iso, date_txt, tax_id, customer, items, tax_rate, currency="PKR", discount=0.0):
    sub = round(sum(i["amount"] for i in items), 2)
    tax = round((sub - discount) * tax_rate, 2)
    total = round(sub - discount + tax, 2)
    return {"file": name, "vendor": vendor, "invoice_no": inv, "date": date_iso, "date_txt": date_txt, "tax_id": tax_id,
            "customer": customer, "subtotal": sub, "discount": discount, "tax": tax if tax_rate else None,
            "total": total, "currency": currency, "line_items": items}


# ---------------------------------------------------------------- layouts
def layout_modern(t, path):
    """Right-aligned meta block, 'Invoice #', 'Issue Date', 'Bill To' block below, 'Amount Due'."""
    c = canvas.Canvas(str(path), pagesize=A4); W, H = A4
    c.setFont("Helvetica-Bold", 20); c.drawString(40, H - 60, t["vendor"])
    c.setFont("Helvetica", 9); c.drawString(40, H - 76, "Plot 14, Sector I-9/2, Islamabad  |  +92 51 444 1200")
    c.drawString(40, H - 88, f"NTN: {t['tax_id']}")
    c.setFont("Helvetica-Bold", 26); c.drawRightString(W - 40, H - 60, "INVOICE")
    c.setFont("Helvetica", 10)
    for i, (k, v) in enumerate([("Invoice #", t["invoice_no"]), ("Issue Date", t["date_txt"]), ("Due Date", "30 days")]):
        c.drawRightString(W - 130, H - 90 - i * 14, k); c.drawRightString(W - 40, H - 90 - i * 14, v)
    c.setFont("Helvetica-Bold", 10); c.drawString(40, H - 140, "BILL TO")
    c.setFont("Helvetica", 10); c.drawString(40, H - 154, t["customer"]); c.drawString(40, H - 166, "Blue Area, Islamabad")
    rows = [[i["description"], f"{i['quantity']:g}", money(i["unit_price"]), money(i["amount"])] for i in t["line_items"]]
    y = table(c, 40, H - 210, ["Description", "Qty", "Rate", "Amount"], [300, 60, 70, 85], rows, "lrrr", colors.HexColor("#1f2937"), grid=True)
    c.setFont("Helvetica", 10)
    for k, v in [("Subtotal", money(t["subtotal"])), ("Sales Tax 18%", money(t["tax"]))]:
        y -= 16; c.drawRightString(W - 130, y, k); c.drawRightString(W - 40, y, v)
    y -= 20; c.setFont("Helvetica-Bold", 12); c.drawRightString(W - 130, y, "Amount Due (PKR)"); c.drawRightString(W - 40, y, money(t["total"]))
    c.save()


def layout_sno(t, path):
    """Pakistani wholesale bill: 'Bill No.', 'Dated', S.No column first, Qty after Rate, 'Net Payable'."""
    t["tax"] = float(round(t["tax"])); t["total"] = t["subtotal"] + t["tax"]  # this bill prints whole rupees
    c = canvas.Canvas(str(path), pagesize=A4); W, H = A4
    c.setFont("Helvetica-Bold", 18); c.drawCentredString(W / 2, H - 50, t["vendor"])
    c.setFont("Helvetica", 9); c.drawCentredString(W / 2, H - 64, "Shop 7, Jodia Bazaar, Karachi. Ph: 021-32411880")
    c.drawCentredString(W / 2, H - 76, f"STRN: {t['tax_id']}")
    c.setFont("Helvetica-Bold", 12); c.drawCentredString(W / 2, H - 98, "SALES TAX INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 124, f"Bill No. {t['invoice_no']}"); c.drawRightString(W - 40, H - 124, f"Dated: {t['date_txt']}")
    c.drawString(40, H - 140, f"M/s: {t['customer']}")
    rows = [[str(n + 1), i["description"], money(i["unit_price"], "int"), f"{i['quantity']:g}", money(i["amount"], "int")] for n, i in enumerate(t["line_items"])]
    y = table(c, 40, H - 175, ["S.No", "Particulars", "Rate", "Qty", "Amount"], [40, 260, 75, 50, 90], rows, "llrrr", grid=True)
    c.setFont("Helvetica", 10)
    for k, v in [("Gross Amount", money(t["subtotal"], "int")), ("GST @ 17%", money(t["tax"], "int"))]:
        y -= 16; c.drawRightString(W - 135, y, k); c.drawRightString(W - 40, y, v)
    y -= 18; c.setFont("Helvetica-Bold", 11); c.drawRightString(W - 135, y, "Net Payable"); c.drawRightString(W - 40, y, money(t["total"], "int"))
    c.save()


def layout_usd(t, path):
    """US-style: logo text left, 'Invoice Number', 'Invoice Date' in a 2-col grid, unit price $ prefixed, 'TOTAL DUE'."""
    c = canvas.Canvas(str(path), pagesize=A4); W, H = A4
    c.setFillColor(colors.HexColor("#0e7490")); c.rect(0, H - 90, W, 90, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 22); c.drawString(40, H - 55, t["vendor"])
    c.setFont("Helvetica", 9); c.drawString(40, H - 72, "billing@" + t["vendor"].split()[0].lower() + ".com")
    c.setFillColor(colors.black); c.setFont("Helvetica", 10)
    grid = [("Invoice Number:", t["invoice_no"]), ("Invoice Date:", t["date_txt"]), ("Customer:", t["customer"]), ("Tax ID:", t["tax_id"])]
    for i, (k, v) in enumerate(grid):
        c.setFont("Helvetica-Bold", 10); c.drawString(40, H - 120 - i * 15, k); c.setFont("Helvetica", 10); c.drawString(140, H - 120 - i * 15, v)
    rows = [[i["description"], f"{i['quantity']:g}", "$" + money(i["unit_price"]), "$" + money(i["amount"])] for i in t["line_items"]]
    y = table(c, 40, H - 210, ["Item", "Quantity", "Unit Price", "Line Total"], [270, 70, 85, 90], rows, "lrrr", colors.HexColor("#0e7490"))
    c.setFont("Helvetica", 10)
    y -= 16; c.drawRightString(W - 140, y, "Subtotal"); c.drawRightString(W - 40, y, "$" + money(t["subtotal"]))
    y -= 16; c.drawRightString(W - 140, y, "Tax (8%)"); c.drawRightString(W - 40, y, "$" + money(t["tax"]))
    y -= 18; c.setFont("Helvetica-Bold", 12); c.drawRightString(W - 140, y, "TOTAL DUE"); c.drawRightString(W - 40, y, "$" + money(t["total"]))
    c.save()


def layout_service(t, path):
    """Services invoice: no qty column per se ('Hours'), 'Ref No', date like 'October 3, 2026', 'Total (incl. tax)'."""
    c = canvas.Canvas(str(path), pagesize=A4); W, H = A4
    c.setFont("Helvetica-Bold", 16); c.drawString(40, H - 50, t["vendor"])
    c.setFont("Helvetica", 9); c.drawString(40, H - 64, f"Tax Registration No: {t['tax_id']}")
    c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 100, "Invoice")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 120, f"Ref No: {t['invoice_no']}"); c.drawString(250, H - 120, f"Date: {t['date_txt']}")
    c.drawString(40, H - 136, f"Client: {t['customer']}")
    rows = [[i["description"], f"{i['quantity']:g}", money(i["unit_price"]), money(i["amount"])] for i in t["line_items"]]
    y = table(c, 40, H - 175, ["Service", "Hours", "Rate/hr", "Amount"], [280, 60, 80, 95], rows, "lrrr", colors.HexColor("#4b5563"), grid=True)
    c.setFont("Helvetica", 10)
    y -= 16; c.drawRightString(W - 140, y, "Sub-total"); c.drawRightString(W - 40, y, money(t["subtotal"]))
    y -= 16; c.drawRightString(W - 140, y, "Less: Discount"); c.drawRightString(W - 40, y, money(t["discount"]))
    y -= 16; c.drawRightString(W - 140, y, "Sales Tax on Services 16%"); c.drawRightString(W - 40, y, money(t["tax"]))
    y -= 18; c.setFont("Helvetica-Bold", 11); c.drawRightString(W - 140, y, "Total (incl. tax)"); c.drawRightString(W - 40, y, money(t["total"]))
    c.save()


def layout_receiptish(t, path):
    """Narrow A5 bill with Rs. prefixes, label/value on separate lines, 'Total Rs.'"""
    c = canvas.Canvas(str(path), pagesize=A5); W, H = A5
    c.setFont("Helvetica-Bold", 14); c.drawCentredString(W / 2, H - 40, t["vendor"])
    c.setFont("Helvetica", 8); c.drawCentredString(W / 2, H - 52, f"NTN {t['tax_id']}")
    c.setFont("Helvetica", 9)
    c.drawString(24, H - 76, "Invoice No"); c.drawString(24, H - 88, t["invoice_no"])
    c.drawString(160, H - 76, "Date"); c.drawString(160, H - 88, t["date_txt"])
    c.drawString(24, H - 106, f"Customer: {t['customer']}")
    rows = [[i["description"], f"{i['quantity']:g}", money(i["unit_price"]), money(i["amount"])] for i in t["line_items"]]
    y = table(c, 24, H - 135, ["Item", "Qty", "Price", "Total"], [180, 35, 75, 85], rows, "lrrr", size=8, grid=True)
    c.setFont("Helvetica", 9)
    y -= 14; c.drawString(200, y, "Subtotal"); c.drawRightString(W - 24, y, money(t["subtotal"], "rs"))
    y -= 14; c.drawString(200, y, "GST 18%"); c.drawRightString(W - 24, y, money(t["tax"], "rs"))
    y -= 16; c.setFont("Helvetica-Bold", 10); c.drawString(200, y, "Total"); c.drawRightString(W - 24, y, money(t["total"], "rs"))
    c.save()


def to_photo(pdf_path, jpg_path, seed):
    import pypdfium2 as pdfium
    pg = pdfium.PdfDocument(str(pdf_path))[0]
    img = pg.render(scale=2.2).to_pil().convert("RGB")
    rnd = random.Random(seed)
    img = img.rotate(rnd.uniform(-2.5, 2.5), expand=True, fillcolor=(235, 232, 225))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    bg = Image.new("RGB", (img.width + 120, img.height + 160), (90, 80, 70)); bg.paste(img, (60, 70))
    bg.save(jpg_path, quality=82)
    pdf_path.unlink()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        f.unlink()
    T = [
        (layout_modern, doc("rw01_skyline.pdf", "Skyline Digital Solutions", "SDS-2026-0412", "2026-09-18", "18 Sep 2026", "4417820-6", "Margalla Foods (Pvt) Ltd",
                            items_of([("Website maintenance (Sept)", 1, 45000), ("Cloud hosting - 3 servers", 3, 12500), ("SSL certificate renewal", 2, 6000)]), 0.18)),
        (layout_sno, doc("rw02_madina.pdf", "Madina Wholesale Traders", "1187", "2026-09-02", "02-09-2026", "32-77-8761-551-19", "Al-Habib General Store",
                         items_of([("Dalda Ghee 16kg tin", 5, 8450), ("Tapal Danedar 950g", 12, 1590), ("National Salt 800g", 48, 65), ("Shan Biryani Masala", 36, 140)]), 0.17)),
        (layout_usd, doc("rw03_brightpath.pdf", "BrightPath Software LLC", "BP-10293", "2026-08-30", "08/30/2026", "84-2290113", "Northwind Retail Inc",
                         items_of([("Annual license - Standard", 5, 240), ("Onboarding session", 2, 350), ("Priority support add-on", 1, 600)]), 0.08, currency="USD")),
        (layout_service, doc("rw04_hamdan.pdf", "Hamdan & Co. Chartered Accountants", "HC/INV/77", "2026-10-03", "October 3, 2026", "0712655-8", "Rehman Textile Mills",
                             items_of([("Statutory audit FY2025-26", 40, 3500), ("Tax return filing", 6, 4000)]), 0.16, discount=5000.0)),
        (layout_receiptish, doc("rw05_quickfix.pdf", "QuickFix Auto Workshop", "QF-5531", "2026-09-27", "27/09/2026", "3390124-1", "Bilal Ahmed",
                                items_of([("Engine oil 4L", 1, 6800), ("Oil filter", 1, 1200), ("Labour", 1, 1500)]), 0.18)),
        (layout_modern, doc("rw06_orbit.pdf", "Orbit Logistics", "OL-88213", "2026-09-05", "5 September 2026", "5521907-3", "Chenab Exports",
                            items_of([("Container haulage KHI-LHR", 2, 145000), ("Loading / unloading", 2, 9000), ("Insurance", 1, 7400), ("Toll charges", 2, 2350)]), 0.18)),
        (layout_sno, doc("rw07_punjab.pdf", "Punjab Seed Corporation", "PSC-0091", "2026-09-11", "11.09.2026", "12-34-5678-901-23", "Kissan Agri Store",
                         items_of([("Wheat seed Akbar-19 50kg", 20, 7600), ("Cotton seed FH-142", 10, 4100)]), 0.17)),
        (layout_usd, doc("rw08_gulfstar.pdf", "GulfStar Trading FZE", "GS-2201", "2026-09-22", "09/22/2026", "100234567800003", "Karachi Electronics Mart",
                         items_of([("LED panel 24in", 10, 85), ("HDMI cable 2m", 50, 3.5), ("Wall mount bracket", 10, 12)]), 0.05, currency="USD")),
    ]
    truth = {}
    for fn, t in T:
        path = OUT / t["file"]
        fn(t, path)
        truth[t["file"]] = t
    # phone photos of four of them
    for src, seed in (("rw02_madina.pdf", 1), ("rw05_quickfix.pdf", 2), ("rw06_orbit.pdf", 3), ("rw03_brightpath.pdf", 4)):
        jpg = "photo_" + src.replace(".pdf", ".jpg")
        p = OUT / ("tmp_" + src); fn = next(f for f, t in T if t["file"] == src); fn(truth[src], p)
        to_photo(p, OUT / jpg, seed)
        truth[jpg] = dict(truth[src], file=jpg)
    clean = {}
    for k, t in truth.items():
        t = {kk: vv for kk, vv in t.items() if kk not in ("file", "date_txt")}
        if not t.get("discount"):
            t.pop("discount", None)
        t["notes"] = []
        clean[k] = t
    (OUT / "ground_truth.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False))
    print(f"wrote {len(clean)} documents to {OUT}")


if __name__ == "__main__":
    main()
