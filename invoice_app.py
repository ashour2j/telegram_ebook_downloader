#!/usr/bin/env python3
"""
Local invoice website for the ebook library.

Run:
    python build_database.py   # once, to create books_data.json
    python invoice_app.py      # then start the site (opens in your browser)

Features:
  - Browse/search the book catalog and build an order (books x quantities).
  - Printable invoice page (A4, RTL) - print from the browser or download a PDF.
  - PDFs are named like: INV-0001_<customer>_<date>.pdf (for clients/history).
  - Full order history kept in ./orders and listed on the site.

Edit shop_config.json to set your shop name, address, phone, and PDF engine.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from config import DownloaderConfig
from namer import sanitize_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "books_data.json"
ORDERS_DIR = BASE_DIR / "orders"
PDFS_DIR = ORDERS_DIR / "pdfs"
CONFIG_FILE = BASE_DIR / "shop_config.json"

DEFAULT_CONFIG = {
    "shop_name": "مكتبة الخال",
    "shop_address": "السيوف",
    "shop_phone": "YOUR_PHONE_NUMBER",
    "shop_footer": "شكراً لتعاملكم معنا",
    "pdf_engine": "chrome",  # chrome = best quality (uses installed Chrome/Edge)
}

for folder in (ORDERS_DIR, PDFS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

if not CONFIG_FILE.exists():
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[i] Created {CONFIG_FILE} - edit it to set your shop details.")

with open(CONFIG_FILE, encoding="utf-8") as f:
    SHOP = json.load(f)


def load_books():
    if not DATA_FILE.exists():
        print(f"[!] {DATA_FILE} not found. Run: python build_database.py")
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


BOOKS = load_books()
BOOKS_BY_ID = {b["id"]: b for b in BOOKS}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Invoice number / order storage
# ---------------------------------------------------------------------------

def next_invoice_number():
    highest = 0
    for p in ORDERS_DIR.glob("inv_*.json"):
        m = re.match(r"inv_(\d+)\.json", p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def save_order(order):
    num = int(order["number"].replace("INV-", ""))
    path = ORDERS_DIR / f"inv_{num:04d}.json"
    path.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_order(number):
    num = int(number.replace("INV-", ""))
    path = ORDERS_DIR / f"inv_{num:04d}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_orders():
    orders = []
    for p in sorted(ORDERS_DIR.glob("inv_*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        data["_file"] = p.name
        orders.append(data)
    return sorted(orders, key=lambda o: o.get("number", ""), reverse=True)


def book_display(book):
    parts = []
    if book.get("type") and book.get("type") != "كتاب":
        parts.append(book["type"])
    if book.get("series"):
        parts.append(book["series"])
    if book.get("subject"):
        parts.append(book["subject"])
    if book.get("grade_arabic"):
        parts.append(book["grade_arabic"])
    if book.get("term_arabic"):
        parts.append(book["term_arabic"])
    if book.get("year"):
        parts.append(str(book["year"]))
    if book.get("publisher"):
        parts.append(book["publisher"])
    if parts:
        return " - ".join(parts)
    return book.get("title", "").rsplit(".", 1)[0]


def _group_key(book):
    return (
        book.get("series"),
        book.get("subject"),
        book.get("grade"),
        book.get("term"),
        book.get("year"),
    )


def group_books(books):
    """Returns display groups: main book first, its companions nested underneath."""
    comps_by_key = {}
    for b in books:
        if b.get("type") and b.get("type") != "كتاب":
            comps_by_key.setdefault(_group_key(b), []).append(b)

    main_by_key = {}
    for b in books:
        if b.get("type") == "كتاب":
            main_by_key.setdefault(_group_key(b), b)

    groups = []
    seen = set()
    for b in books:
        if b.get("type") == "كتاب":
            key = _group_key(b)
            if main_by_key.get(key) is not b:
                groups.append({"main": b, "companions": []})
                continue
            comps = comps_by_key.get(key, [])
            for c in comps:
                seen.add(id(c))
            groups.append({"main": b, "companions": comps})

    for b in books:
        if b.get("type") and b.get("type") != "كتاب" and id(b) not in seen:
            groups.append({"main": None, "companions": [b]})
    return groups


# ---------------------------------------------------------------------------
# PDF generation (Chrome/Edge headless print)
# ---------------------------------------------------------------------------

def _find_browser():
    candidates = [
        os.environ.get("PDF_BROWSER"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return shutil.which("chrome") or shutil.which("msedge") or shutil.which("chromium")


def render_pdf(order):
    """Renders an order to PDF via a headless browser. Returns the saved path."""
    html = render_template("invoice.html", shop=SHOP, order=order, pdf=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False)
    tmp.write(html)
    tmp.close()

    safe_customer = sanitize_filename(order["customer"]) or "unknown"
    out_name = f"{order['number']}_{safe_customer}_{order['date']}.pdf"
    out_path = PDFS_DIR / out_name

    browser = _find_browser()
    if not browser:
        os.unlink(tmp.name)
        return None

    url = Path(tmp.name).as_uri()
    attempts = [
        [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={out_path}", url],
        [browser, "--headless", "--disable-gpu", "--print-to-pdf-no-header",
         f"--print-to-pdf={out_path}", url],
    ]
    for cmd in attempts:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                break
        except Exception:
            continue

    os.unlink(tmp.name)
    return out_path if out_path.exists() and out_path.stat().st_size > 0 else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", shop=SHOP, books=BOOKS, groups=group_books(BOOKS))


@app.route("/reindex", methods=["POST"])
def reindex():
    """Rebuilds the Excel DB / JSON feed from the library and reloads the catalog."""
    global BOOKS, BOOKS_BY_ID
    try:
        from build_database import build

        books = build(
            DownloaderConfig().output_dir,
            BASE_DIR / "books_database.xlsx",
            DATA_FILE,
            BASE_DIR / "books.csv",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if not books:
        return jsonify({"error": "لا توجد كتب في المكتبة"}), 400
    BOOKS = books
    BOOKS_BY_ID = {b["id"]: b for b in BOOKS}
    return jsonify({"ok": True, "count": len(BOOKS)})


@app.route("/orders")
def orders():
    return render_template("orders.html", shop=SHOP, orders=list_orders())


@app.route("/create", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    customer = (data.get("customer") or "").strip()
    phone = (data.get("phone") or "").strip()
    notes = (data.get("notes") or "").strip()
    try:
        delivery = round(float(data.get("delivery") or 0), 2)
    except (TypeError, ValueError):
        delivery = 0.0

    if not customer:
        return jsonify({"error": "اسم العميل مطلوب"}), 400

    items = []
    for row in data.get("items") or []:
        book = BOOKS_BY_ID.get(row.get("id"))
        try:
            qty = max(1, int(row.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        if not book:
            continue
        no_cover = str(row.get("no_cover") or "").lower() in ("1", "true", "yes", "on")
        if no_cover:
            unit_price = round(float(book.get("no_cover_price") or 0), 2)
        else:
            unit_price = round(float(book.get("unit_price") or 0), 2)
        title = book_display(book)
        if no_cover:
            title = f"{title} (بدون غلاف)"
        items.append({
            "id": book["id"],
            "title": title,
            "grade": book.get("grade"),
            "term": book.get("term"),
            "qty": qty,
            "no_cover": no_cover,
            "unit_price": unit_price,
        })

    if not items:
        return jsonify({"error": "اختر كتاباً واحداً على الأقل"}), 400

    for it in items:
        it["line_total"] = round(it["unit_price"] * it["qty"], 2)
    subtotal = round(sum(it["line_total"] for it in items), 2)
    total = round(subtotal + delivery, 2)

    number = f"INV-{next_invoice_number():04d}"
    order = {
        "number": number,
        "date": date.today().isoformat(),
        "customer": customer,
        "phone": phone,
        "notes": notes,
        "delivery": delivery,
        "line_items": items,
        "subtotal": subtotal,
        "total": total,
    }
    save_order(order)
    return jsonify({"redirect": url_for("invoice", inv=number)})


@app.route("/invoice/<inv>")
def invoice(inv):
    order = load_order(inv)
    if not order:
        abort(404)
    return render_template("invoice.html", shop=SHOP, order=order)


@app.route("/invoice/<inv>/pdf")
def invoice_pdf(inv):
    order = load_order(inv)
    if not order:
        abort(404)

    safe_customer = sanitize_filename(order["customer"]) or "unknown"
    saved = PDFS_DIR / f"{order['number']}_{safe_customer}_{order['date']}.pdf"
    if not saved.exists():
        saved = render_pdf(order)
    if not saved or not saved.exists():
        return "PDF generation failed (no browser found). Print from the invoice page instead.", 500
    return send_file(saved, as_attachment=True,
                     download_name=f"{order['number']}_{safe_customer}_{order['date']}.pdf",
                     mimetype="application/pdf")


@app.route("/orders/<inv>/delete", methods=["POST"])
def delete_order(inv):
    num = int(re.sub(r"[^0-9]", "", inv))
    json_path = ORDERS_DIR / f"inv_{num:04d}.json"
    if not json_path.exists():
        return jsonify({"error": "الفاتورة غير موجودة"}), 404
    prefix = f"INV-{num:04d}_"
    removed_pdfs = 0
    for pdf in PDFS_DIR.glob(f"{prefix}*.pdf"):
        for _ in range(5):
            try:
                pdf.unlink()
                removed_pdfs += 1
                break
            except PermissionError:
                time.sleep(0.3)
        else:
            print(f"[!] Could not remove PDF (still in use): {pdf}")
    json_path.unlink(missing_ok=True)
    return jsonify({"ok": True, "pdfs": removed_pdfs})


if __name__ == "__main__":
    port = 5000
    webbrowser.open(f"http://127.0.0.1:{port}/")
    app.run(host="127.0.0.1", port=port, debug=False)
