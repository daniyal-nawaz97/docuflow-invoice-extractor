"""Generate the demo set of fake invoices plus a ground-truth file.

All vendors, customers, tax IDs and amounts are invented. Output:
    sample_data/invoices/*.pdf|*.jpg
    sample_data/ground_truth.json   (used by scripts/evaluate.py)

Run:  python -m scripts.make_samples
"""
from __future__ import annotations

import io
import json
import random
import shutil
import sys
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "sample_data" / "invoices"
GT_PATH = BASE / "sample_data" / "ground_truth.json"

W, H = A4
rng = random.Random(42)

URDU_FONT = None
for cand in ["/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
             "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"]:
    if Path(cand).exists():
        pdfmetrics.registerFont(TTFont("Urdu", cand))
        URDU_FONT = "Urdu"
        break


def urdu(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def money(v: float, cur: str = "PKR") -> str:
    return f"{v:,.2f}"


def fmt_date(d: date, style: str) -> str:
    if style == "dmy_slash":
        return d.strftime("%d/%m/%Y")
    if style == "d_mon_y":
        return d.strftime("%d %b %Y")
    if style == "mon_d_y":
        return d.strftime("%B %d, %Y")
    return d.isoformat()


def make_items(catalog, n, price_scale=1.0):
    picks = rng.sample(catalog, min(n, len(catalog))) if n <= len(catalog) else [rng.choice(catalog) for _ in range(n)]
    items = []
    for name, price in picks:
        qty = rng.choice([1, 2, 3, 4, 5, 6, 10, 12, 20, 24, 50])
        unit = round(price * price_scale, 2)
        items.append({"description": name, "quantity": qty, "unit_price": unit, "amount": round(qty * unit, 2)})
    return items


def totals(items, tax_rate, discount=0.0):
    sub = round(sum(i["amount"] for i in items), 2)
    tax = round((sub - discount) * tax_rate, 2)
    return sub, tax, round(sub - discount + tax, 2)


# --------------------------------------------------------------------------- catalogs
GROCERY = [("Basmati Rice 5kg bag", 1850), ("Cooking Oil 5L tin", 2750), ("Sugar 50kg sack", 7200),
           ("Red Chilli Powder 1kg", 980), ("Tea Leaves 900g", 1420), ("Wheat Flour 20kg", 2600),
           ("Lentils (Daal Masoor) 1kg", 360), ("Chickpeas 1kg", 320), ("Salt 800g", 70)]
PACKAGING = [("Corrugated Box 12x10x8", 85), ("Corrugated Box 18x12x12", 140), ("Bubble Wrap Roll 50m", 1950),
             ("Packing Tape 2in (36 rolls)", 2880), ("Poly Mailer Bags 10x14 (100)", 1150),
             ("Fragile Stickers (500)", 650), ("Stretch Film 18in", 1700), ("Kraft Paper Roll", 1350),
             ("Thermal Labels 4x6 (500)", 1450), ("Void Fill Paper Pack", 900)]
OFFICE = [("A4 Paper Ream 80gsm", 1650), ("Ball Pens Blue (box of 50)", 750), ("Stapler Heavy Duty", 1250),
          ("Box File Lever Arch", 420), ("Printer Toner 85A", 6800), ("Whiteboard Marker Set", 540),
          ("Sticky Notes 3x3 (12 pads)", 780), ("Desk Organizer", 1150)]
ELECTRONICS = [("USB-C Fast Charger 25W", 1499), ("Wireless Earbuds Pro", 4850), ("HDMI Cable 2m", 650),
               ("Power Bank 20000mAh", 5200), ("Bluetooth Speaker Mini", 3350), ("Smart Watch Band", 950),
               ("USB-C to Lightning Cable", 1100), ("Phone Holder Car Mount", 850)]
TEXTILE = [("Cotton Lawn Fabric (meter)", 520), ("Khaddar Fabric (meter)", 610), ("Polyester Thread Cone", 240),
           ("Dyeing Charges per kg", 180), ("Printed Cambric (meter)", 450)]
IMPORT = [("Industrial Sewing Needles (1000)", 38.5), ("Laser Label Printer", 412.0),
          ("Barcode Scanner Handheld", 96.0), ("Spare Printhead 203dpi", 145.0)]

CUSTOMERS = [("Zara Fashion Hub", "Shop 14, Liberty Market, Lahore"),
             ("Bright Mart Superstore", "Plot 22, Gulshan-e-Iqbal, Karachi"),
             ("NovaCart Online Store", "Office 5, Blue Area, Islamabad"),
             ("Green Valley Distributors", "Main GT Road, Gujranwala")]


# --------------------------------------------------------------------------- templates
def header_block(c, x, y, rows, label_font="Helvetica-Bold", val_font="Helvetica", size=9.5, gap=14, label_w=70):
    for label, val in rows:
        c.setFont(label_font, size); c.drawString(x, y, label)
        c.setFont(val_font, size); c.drawString(x + label_w, y, val)
        y -= gap
    return y


def table(c, x, y, items, widths, cur, head_fill, head_text=colors.white, row_h=18, zebra=True, max_y=110):
    """Draw line-item table. Returns (y, remaining_items)."""
    cols = ["Description", "Qty", "Unit Price", "Amount"]
    c.setFillColor(head_fill); c.rect(x, y - 5, sum(widths), row_h, stroke=0, fill=1)
    c.setFillColor(head_text); c.setFont("Helvetica-Bold", 9.5)
    cx = x + 6
    for i, col in enumerate(cols):
        if i == 0:
            c.drawString(cx, y, col)
        else:
            c.drawRightString(cx + widths[i] - 12, y, col)
        cx += widths[i]
    y -= row_h
    c.setFillColor(colors.black); c.setFont("Helvetica", 9.5)
    for n, it in enumerate(items):
        if y < max_y:
            return y, items[n:]
        if zebra and n % 2 == 1:
            c.setFillColor(colors.Color(0.96, 0.96, 0.97)); c.rect(x, y - 5, sum(widths), row_h, stroke=0, fill=1)
            c.setFillColor(colors.black)
        cx = x + 6
        vals = [it["description"], str(it["quantity"]), money(it["unit_price"]), money(it["amount"])]
        for i, v in enumerate(vals):
            if i == 0:
                c.drawString(cx, y, v)
            else:
                c.drawRightString(cx + widths[i] - 12, y, v)
            cx += widths[i]
        y -= row_h
    return y, []


def totals_block(c, xr, y, rows, bold_last=True):
    for i, (label, val) in enumerate(rows):
        last = bold_last and i == len(rows) - 1
        c.setFont("Helvetica-Bold" if last else "Helvetica", 11 if last else 10)
        c.drawRightString(xr - 110, y, label)
        c.drawRightString(xr, y, val)
        y -= 17 if not last else 20
    return y


def tpl_classic(path, d):
    """Al-Noor style: vendor name top-left, INVOICE top-right."""
    c = canvas.Canvas(str(path), pagesize=A4)
    acc = colors.HexColor(d.get("color", "#14532d"))
    c.setFillColor(acc); c.circle(52, H - 58, 16, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 14); c.drawCentredString(52, H - 63, d["vendor"][0])
    c.setFillColor(acc); c.setFont("Helvetica-Bold", 20); c.drawString(76, H - 64, d["vendor"])
    c.setFillColor(colors.black); c.setFont("Helvetica", 9)
    c.drawString(76, H - 80, d["vendor_address"]); c.drawString(76, H - 92, f"Phone: {d['phone']}")
    c.setFont("Helvetica-Bold", 22); c.setFillColor(colors.HexColor("#333333")); c.drawRightString(W - 40, H - 64, "INVOICE")
    c.setFillColor(colors.black)
    header_block(c, W - 230, H - 100, [("Invoice No:", d["invoice_no"]), ("Date:", d["date_str"]), ("NTN:", d["tax_id"])])
    c.setFont("Helvetica-Bold", 10); c.drawString(40, H - 150, "Bill To:")
    c.setFont("Helvetica", 10); c.drawString(40, H - 164, d["customer"]); c.drawString(40, H - 177, d["customer_address"])
    y, rest = table(c, 40, H - 215, d["line_items"], [280, 50, 95, 90], d["currency"], acc)
    y -= 12
    rows = [("Subtotal", money(d["subtotal"])), (f"Sales Tax {int(d['tax_rate']*100)}%", money(d["tax"])),
            ("Grand Total", f"{d['currency']} {money(d['printed_total'])}")]
    totals_block(c, W - 45, y, rows)
    c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(colors.grey)
    c.drawString(40, 60, "Payment within 30 days. Thank you for your business.")
    c.drawString(40, 48, "SAMPLE DOCUMENT - fictitious company and figures for demonstration only.")
    c.save()


def tpl_band(path, d):
    """Crescent style: coloured header band, TAX INVOICE, may span multiple pages."""
    c = canvas.Canvas(str(path), pagesize=A4)
    acc = colors.HexColor(d.get("color", "#1e3a8a"))
    items = d["line_items"]
    page = 1
    while True:
        c.setFillColor(acc); c.rect(0, H - 95, W, 95, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 21); c.drawString(40, H - 50, d["vendor"])
        c.setFont("Helvetica", 9); c.drawString(40, H - 66, d["vendor_address"])
        c.drawString(40, H - 78, f"STRN / Tax ID: {d['tax_id']}")
        c.setFont("Helvetica-Bold", 16); c.drawRightString(W - 40, H - 50, "TAX INVOICE")
        c.setFont("Helvetica", 9); c.drawRightString(W - 40, H - 66, f"Page {page}")
        c.setFillColor(colors.black)
        if page == 1:
            header_block(c, 40, H - 125, [("Invoice #:", d["invoice_no"]), ("Invoice Date:", d["date_str"]),
                                          ("Due Date:", d.get("due_str", ""))], label_w=80)
            c.setFont("Helvetica-Bold", 10); c.drawString(320, H - 125, "Customer")
            c.setFont("Helvetica", 10); c.drawString(320, H - 139, d["customer"]); c.drawString(320, H - 152, d["customer_address"])
            top = H - 195
        else:
            top = H - 125
        y, items = table(c, 40, top, items, [285, 45, 95, 90], d["currency"], acc, max_y=150)
        if items:
            c.setFont("Helvetica-Oblique", 9); c.drawRightString(W - 45, 120, "Continued on next page...")
            c.showPage(); page += 1
            continue
        y -= 14
        rows = [("Sub Total", money(d["subtotal"]))]
        if d.get("discount"):
            rows.append(("Discount", money(d["discount"])))
        rows += [(f"GST @ {int(d['tax_rate']*100)}%", money(d["tax"])), ("Total Amount", f"{d['currency']} {money(d['printed_total'])}")]
        totals_block(c, W - 45, y, rows)
        c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(colors.grey)
        c.drawString(40, 48, "SAMPLE DOCUMENT - fictitious company and figures for demonstration only.")
        c.save()
        return


def tpl_minimal(path, d):
    """Swift Courier style: plain statement."""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 18); c.drawString(40, H - 60, d["vendor"])
    c.setFont("Helvetica", 9); c.drawString(40, H - 75, d["vendor_address"])
    c.setStrokeColor(colors.black); c.line(40, H - 88, W - 40, H - 88)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, H - 110, "Bill of Services")
    header_block(c, 40, H - 135, [("Bill No", d["invoice_no"]), ("Dated", d["date_str"]), ("Tax ID", d["tax_id"]),
                                  ("Customer", d["customer"])], label_font="Helvetica", label_w=70)
    y, _ = table(c, 40, H - 215, d["line_items"], [285, 45, 95, 90], d["currency"], colors.HexColor("#444444"), zebra=False)
    y -= 12
    rows = [("Subtotal", money(d["subtotal"])), (f"Sales Tax {int(d['tax_rate']*100)}%", money(d["tax"])),
            ("Amount Due", f"{d['currency']} {money(d['printed_total'])}")]
    totals_block(c, W - 45, y, rows)
    c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(colors.grey)
    c.drawString(40, 48, "SAMPLE DOCUMENT - fictitious company and figures for demonstration only.")
    c.save()


def tpl_boxed(path, d):
    """Margalla style: boxed header grid."""
    c = canvas.Canvas(str(path), pagesize=A4)
    acc = colors.HexColor(d.get("color", "#7c2d12"))
    c.setStrokeColor(acc); c.setLineWidth(2); c.rect(30, 30, W - 60, H - 60)
    c.setFillColor(acc); c.setFont("Helvetica-Bold", 22); c.drawString(45, H - 75, d["vendor"])
    c.setFillColor(colors.black); c.setFont("Helvetica", 9); c.drawString(45, H - 90, d["vendor_address"])
    c.setFont("Helvetica-Bold", 13); c.drawRightString(W - 45, H - 75, "SALES INVOICE")
    c.setLineWidth(0.8); c.rect(45, H - 175, W - 90, 70)
    header_block(c, 55, H - 125, [("Invoice Number:", d["invoice_no"]), ("Invoice Date:", d["date_str"])], label_w=95)
    header_block(c, 320, H - 125, [("Tax ID:", d["tax_id"]), ("Sold To:", d["customer"])], label_w=55)
    y, _ = table(c, 45, H - 205, d["line_items"], [280, 45, 95, 85], d["currency"], acc)
    y -= 12
    rows = [("Subtotal", money(d["subtotal"])), (f"VAT {int(d['tax_rate']*100)}%" if d["currency"] == "USD" else f"GST {int(d['tax_rate']*100)}%", money(d["tax"])),
            ("Total", f"{d['currency']} {money(d['printed_total'])}")]
    totals_block(c, W - 50, y, rows)
    c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(colors.grey)
    c.drawString(45, 45, "SAMPLE DOCUMENT - fictitious company and figures for demonstration only.")
    c.save()


def tpl_bilingual(path, d):
    """Urdu-English mixed labels (karyana store bill)."""
    c = canvas.Canvas(str(path), pagesize=A4)
    acc = colors.HexColor("#065f46")
    c.setFillColor(acc); c.setFont("Helvetica-Bold", 20); c.drawString(40, H - 60, d["vendor"])
    if URDU_FONT:
        c.setFont(URDU_FONT, 18); c.drawRightString(W - 40, H - 60, urdu("برکت کریانہ اسٹور"))
    c.setFillColor(colors.black); c.setFont("Helvetica", 9); c.drawString(40, H - 76, d["vendor_address"])
    c.setFont("Helvetica-Bold", 14); c.drawString(40, H - 105, "Bill")
    if URDU_FONT:
        c.setFont(URDU_FONT, 14); c.drawString(75, H - 105, urdu("بل"))
    rows = [("Bill No:", d["invoice_no"], "بل نمبر"), ("Date:", d["date_str"], "تاریخ"), ("NTN:", d["tax_id"], "این ٹی این"),
            ("Customer:", d["customer"], "گاہک")]
    y = H - 130
    for label, val, ur in rows:
        c.setFont("Helvetica-Bold", 9.5); c.drawString(40, y, label)
        c.setFont("Helvetica", 9.5); c.drawString(110, y, val)
        if URDU_FONT:
            c.setFont(URDU_FONT, 10); c.drawRightString(W - 40, y, urdu(ur))
        y -= 15
    y, _ = table(c, 40, H - 215, d["line_items"], [285, 45, 95, 90], d["currency"], acc)
    y -= 12
    rows = [("Subtotal", money(d["subtotal"])), (f"Sales Tax {int(d['tax_rate']*100)}%", money(d["tax"])),
            ("Grand Total", f"Rs. {money(d['printed_total'])}")]
    y2 = totals_block(c, W - 45, y, rows)
    if URDU_FONT:
        c.setFont(URDU_FONT, 11); c.drawString(40, y2 - 10, urdu("شکریہ! دوبارہ تشریف لائیں"))
    c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(colors.grey)
    c.drawString(40, 48, "SAMPLE DOCUMENT - fictitious company and figures for demonstration only.")
    c.save()


TEMPLATES = {"classic": tpl_classic, "band": tpl_band, "minimal": tpl_minimal, "boxed": tpl_boxed, "bilingual": tpl_bilingual}


# --------------------------------------------------------------------------- photo / scan effects
def render_pdf_page(pdf_path, scale=2.0) -> Image.Image:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    img = pdf[0].render(scale=scale).to_pil().convert("RGB")
    pdf.close()
    return img


def phone_photo(page: Image.Image, blur=0.6, angle=1.2, seed=0) -> Image.Image:
    r = random.Random(seed)
    w, h = page.size
    bg = Image.new("RGB", (int(w * 1.12), int(h * 1.08)), (92, 74, 58))  # wooden desk tone
    shadow = Image.new("RGB", page.size, (40, 32, 25))
    ox, oy = int(w * 0.06), int(h * 0.04)
    bg.paste(shadow, (ox + 12, oy + 14))
    bg = bg.filter(ImageFilter.GaussianBlur(10))
    bg.paste(page, (ox, oy))
    img = bg.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(92, 74, 58))
    # uneven lighting
    arr = np.asarray(img).astype(np.float32)
    gx = np.linspace(0.82 + r.random() * 0.05, 1.04, arr.shape[1])[None, :, None]
    gy = np.linspace(1.02, 0.88, arr.shape[0])[:, None, None]
    arr = arr * gx * gy
    arr += np.random.default_rng(seed).normal(0, 5, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(blur))
    img.thumbnail((1600, 1600))
    return img


def scanned(page: Image.Image) -> Image.Image:
    g = page.convert("L").rotate(-0.6, resample=Image.BICUBIC, fillcolor=255)
    arr = np.asarray(g).astype(np.float32)
    arr = arr * 0.93 + 12 + np.random.default_rng(3).normal(0, 7, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.4))


# --------------------------------------------------------------------------- dataset
def build_doc(tpl, vendor, addr, phone, inv_no, d, date_style, catalog, n_items, tax_rate=0.18,
              currency="PKR", color=None, customer=None, discount=0.0, total_error=0.0, price_scale=1.0):
    items = make_items(catalog, n_items, price_scale)
    sub, tax, tot = totals(items, tax_rate, discount)
    cust = customer or rng.choice(CUSTOMERS)
    tax_id = f"{rng.randint(1000000, 9999999)}-{rng.randint(0, 9)}"
    doc = {
        "template": tpl, "vendor": vendor, "vendor_address": addr, "phone": phone,
        "invoice_no": inv_no, "date": d.isoformat(), "date_str": fmt_date(d, date_style),
        "due_str": fmt_date(date.fromordinal(d.toordinal() + 30), date_style),
        "tax_id": tax_id, "customer": cust[0], "customer_address": cust[1],
        "line_items": items, "subtotal": sub, "discount": discount, "tax": tax, "tax_rate": tax_rate,
        "total": round(tot + total_error, 2), "printed_total": round(tot + total_error, 2), "currency": currency,
    }
    if color:
        doc["color"] = color
    return doc


def main():
    if "--if-missing" in sys.argv and GT_PATH.exists():
        print("Samples already exist."); return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    tmp = OUT / "_tmp"; tmp.mkdir()

    alnoor = ("Al-Noor Traders", "12-B Shah Alam Market, Lahore", "042-3765 1122")
    crescent = ("Crescent Packaging (Pvt) Ltd", "Plot 44, Sector 7-A, Korangi Industrial Area, Karachi", "021-3505 8890")
    swift = ("Swift Courier Services", "Suite 3, Jinnah Avenue, Islamabad", "051-2870 4411")
    margalla = ("Margalla Electronics", "Shop 9, Hall Road, Lahore", "042-3723 9001")
    indus = ("Indus Office Supplies", "56 Saddar Road, Rawalpindi", "051-5566 7788")
    ravi = ("Ravi Textiles", "Faisalabad Road, Satiana, Faisalabad", "041-8877 2233")
    globalimp = ("Global Tech Imports FZE", "Warehouse 12, JAFZA South, Dubai, UAE", "+971 4 880 1200")
    barkat = ("Barkat Karyana Store", "Main Bazaar, Model Town, Gujranwala", "055-3844 1020")

    specs = [
        # file, template, kwargs, variant
        ("alnoor_INV-2041.pdf", "classic", dict(v=alnoor, inv="INV-2041", d=date(2026, 9, 12), ds="d_mon_y", cat=GROCERY, n=4)),
        ("alnoor_INV-2057.pdf", "classic", dict(v=alnoor, inv="INV-2057", d=date(2026, 9, 18), ds="d_mon_y", cat=GROCERY, n=6)),
        ("crescent_CP-26-0187.pdf", "band", dict(v=crescent, inv="CP/26/0187", d=date(2026, 9, 3), ds="dmy_slash", cat=PACKAGING, n=5)),
        ("crescent_CP-26-0203.pdf", "band", dict(v=crescent, inv="CP/26/0203", d=date(2026, 9, 21), ds="dmy_slash", cat=PACKAGING, n=3, disc=500.0)),
        ("swift_courier_SC-88213.pdf", "minimal", dict(v=swift, inv="SC-88213", d=date(2026, 9, 30), ds="iso", n=3, tax=0.16,
                                                        cat=[("COD Deliveries Lahore (per parcel)", 180), ("COD Deliveries Karachi (per parcel)", 210),
                                                             ("Return Handling Charges", 95), ("Fuel Surcharge", 1200), ("Packaging Service", 60)])),
        ("margalla_ME-5521.pdf", "boxed", dict(v=margalla, inv="ME-5521", d=date(2026, 9, 9), ds="mon_d_y", cat=ELECTRONICS, n=5)),
        ("indus_office_IOS-1190.pdf", "classic", dict(v=indus, inv="IOS-1190", d=date(2026, 9, 15), ds="d_mon_y", cat=OFFICE, n=5, color="#1d4ed8")),
        ("ravi_textiles_RT-3302.pdf", "band", dict(v=ravi, inv="RT-3302", d=date(2026, 9, 11), ds="dmy_slash", cat=TEXTILE, n=4, tax=0.17, color="#9d174d")),
        ("global_imports_GTI-7781.pdf", "boxed", dict(v=globalimp, inv="GTI-7781", d=date(2026, 9, 5), ds="mon_d_y", cat=IMPORT, n=3, tax=0.05, cur="USD", color="#334155")),
        ("crescent_CP-26-0211_multipage.pdf", "band", dict(v=crescent, inv="CP/26/0211", d=date(2026, 9, 25), ds="dmy_slash", cat=PACKAGING, n=32)),
        ("barkat_karyana_BK-0415_urdu.pdf", "bilingual", dict(v=barkat, inv="BK-0415", d=date(2026, 9, 20), ds="dmy_slash", cat=GROCERY, n=5, tax=0.0)),
        ("swift_courier_SC-88240.pdf", "minimal", dict(v=swift, inv="SC-88240", d=date(2026, 9, 16), ds="iso", n=4, tax=0.16,
                                                        cat=[("COD Deliveries Lahore (per parcel)", 180), ("COD Deliveries Karachi (per parcel)", 210),
                                                             ("Return Handling Charges", 95), ("Fuel Surcharge", 1200), ("Same-day Delivery", 450)])),
        # tricky ones
        ("indus_office_IOS-1204_totals_wrong.pdf", "classic", dict(v=indus, inv="IOS-1204", d=date(2026, 9, 22), ds="d_mon_y", cat=OFFICE, n=4, color="#1d4ed8", err=1000.0)),
        # photos / scans generated from PDFs below
        ("photo_alnoor_INV-2063.jpg", "classic", dict(v=alnoor, inv="INV-2063", d=date(2026, 9, 26), ds="d_mon_y", cat=GROCERY, n=4)),
        ("photo_swift_courier_SC-88257.jpg", "minimal", dict(v=swift, inv="SC-88257", d=date(2026, 9, 27), ds="iso", n=3, tax=0.16,
                                                              cat=[("COD Deliveries Lahore (per parcel)", 180), ("Return Handling Charges", 95), ("Fuel Surcharge", 1200)])),
        ("photo_ravi_textiles_RT-3318.jpg", "band", dict(v=ravi, inv="RT-3318", d=date(2026, 9, 28), ds="dmy_slash", cat=TEXTILE, n=3, tax=0.17, color="#9d174d")),
        ("scan_margalla_ME-5544.pdf", "boxed", dict(v=margalla, inv="ME-5544", d=date(2026, 9, 24), ds="mon_d_y", cat=ELECTRONICS, n=3)),
        ("photo_blurry_margalla_ME-5560.jpg", "boxed", dict(v=margalla, inv="ME-5560", d=date(2026, 9, 29), ds="mon_d_y", cat=ELECTRONICS, n=3)),
    ]

    gt = {}
    for i, (fname, tpl, k) in enumerate(specs):
        v = k["v"]
        doc = build_doc(tpl, v[0], v[1], v[2], k["inv"], k["d"], k["ds"], k["cat"], k["n"], tax_rate=k.get("tax", 0.18),
                        currency=k.get("cur", "PKR"), color=k.get("color"), discount=k.get("disc", 0.0),
                        total_error=k.get("err", 0.0))
        target = OUT / fname
        if fname.endswith(".jpg") or fname.startswith("scan_"):
            src = tmp / (Path(fname).stem + ".pdf")
            TEMPLATES[tpl](src, doc)
            page = render_pdf_page(src)
            if fname.startswith("scan_"):
                img = scanned(page)
                img.save(target, "PDF", resolution=144)  # image-only PDF, no text layer
            elif "blurry" in fname:
                phone_photo(page, blur=3.2, angle=-1.6, seed=i).save(target, "JPEG", quality=70)
            else:
                phone_photo(page, blur=0.6, angle=[1.1, -0.9, 0.7][i % 3], seed=i).save(target, "JPEG", quality=82)
        else:
            TEMPLATES[tpl](target, doc)
        truth = {key: doc[key] for key in ["vendor", "invoice_no", "date", "tax_id", "customer", "subtotal", "tax", "total", "currency", "line_items"]}
        if doc.get("discount"):
            truth["discount"] = doc["discount"]
        truth["notes"] = []
        if "totals_wrong" in fname:
            truth["notes"].append("printed total is 1,000 higher than subtotal + tax (should be flagged)")
        if "blurry" in fname:
            truth["notes"].append("deliberately blurry photo (should be flagged for review)")
        gt[fname] = truth

    # a duplicate: same invoice received twice under a different file name
    shutil.copy(OUT / "crescent_CP-26-0187.pdf", OUT / "crescent_invoice_copy_from_email.pdf")
    gt["crescent_invoice_copy_from_email.pdf"] = dict(gt["crescent_CP-26-0187.pdf"], notes=["duplicate of crescent_CP-26-0187.pdf (should be flagged)"])

    shutil.rmtree(tmp)
    GT_PATH.write_text(json.dumps(gt, indent=2))
    print(f"Wrote {len(gt)} sample documents to {OUT}")


if __name__ == "__main__":
    main()
