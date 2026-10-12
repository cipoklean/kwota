"""The finished quote: a one-page PDF and a WhatsApp message to send with it."""
from __future__ import annotations

import datetime as dt
import random
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote as urlquote

from fpdf import FPDF

from .quote import Line

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@dataclass
class Business:
    name: str = "My Business"
    phone: str = ""
    trade: str = ""


def naira(x: float) -> str:
    sign, x = ("-" if x < 0 else ""), abs(x)
    return sign + (f"₦{x:,.0f}" if float(x).is_integer() else f"₦{x:,.2f}")


def qty_text(q: float) -> str:
    return f"{int(q)}" if float(q).is_integer() else f"{q:g}"


def quote_number(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return f"Q{today:%y%m%d}-{random.randint(100, 999)}"


def subtotal(lines: list[Line]) -> float:
    return round(sum(l.total for l in lines), 2)


def make_pdf(lines: list[Line], biz: Business, customer: str = "", scope: str = "",
             discount: float = 0.0, valid_days: int = 7, number: str | None = None,
             path: str | None = None) -> str:
    number = number or quote_number()
    today = dt.date.today()
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_font("DejaVu", "", str(ASSETS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(ASSETS / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    w = pdf.epw

    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(w * 0.6, 9, biz.name or "Quote", new_x="RIGHT", new_y="TOP")
    pdf.set_font("DejaVu", "B", 18)
    pdf.cell(w * 0.4, 9, "QUOTE", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    sub = " · ".join(x for x in [biz.trade.title() if biz.trade else "", biz.phone] if x)
    pdf.cell(w * 0.6, 6, sub, new_x="RIGHT", new_y="TOP")
    pdf.cell(w * 0.4, 6, f"No. {number}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(w * 0.6, 6, f"For: {customer}" if customer else "", new_x="RIGHT", new_y="TOP")
    pdf.cell(w * 0.4, 6, f"Date: {today:%d %b %Y}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    if scope:
        pdf.set_font("DejaVu", "", 10)
        pdf.multi_cell(w, 5.5, f"Job: {scope}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    cols = [("Item", 0.46, "L"), ("Qty", 0.12, "R"), ("Unit price", 0.2, "R"), ("Amount", 0.22, "R")]
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(235, 242, 235)
    for name, frac, al in cols:
        pdf.cell(w * frac, 8, name, border="B", align=al, fill=True)
    pdf.ln()
    pdf.set_font("DejaVu", "", 10)
    for l in lines:
        pdf.cell(w * 0.46, 7.5, l.item[:48], border="B")
        pdf.cell(w * 0.12, 7.5, f"{qty_text(l.qty)} {l.unit}", border="B", align="R")
        pdf.cell(w * 0.2, 7.5, naira(l.price), border="B", align="R")
        pdf.cell(w * 0.22, 7.5, naira(l.total), border="B", align="R")
        pdf.ln()

    sub_t = subtotal(lines)
    rows = [("Subtotal", sub_t)]
    if discount:
        rows.append(("Discount", -discount))
    rows.append(("TOTAL", sub_t - discount))
    pdf.ln(2)
    for label, val in rows:
        bold = label == "TOTAL"
        pdf.set_font("DejaVu", "B" if bold else "", 12 if bold else 10)
        pdf.cell(w * 0.78, 8, label, align="R")
        pdf.cell(w * 0.22, 8, naira(val), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(90, 90, 90)
    until = today + dt.timedelta(days=valid_days)
    pdf.multi_cell(w, 5, f"This quote is valid until {until:%d %b %Y}. Material prices can change "
                         "after that. Reply 'YES' on WhatsApp to accept and book the job.")
    pdf.ln(2)
    pdf.multi_cell(w, 5, "Prepared with Kwota, open-source quoting for Nigerian artisans.")

    path = path or tempfile.NamedTemporaryFile(suffix=f"-{number}.pdf", delete=False).name
    pdf.output(path)
    return path


def whatsapp_text(lines: list[Line], biz: Business, customer: str = "", scope: str = "",
                  discount: float = 0.0, number: str = "") -> str:
    hello = f"Good day {customer}," if customer else "Good day,"
    body = [hello, f"here is my quote{f' ({number})' if number else ''} for the job."]
    if scope:
        body.append(f"Job: {scope}")
    body.append("")
    for l in lines:
        body.append(f"• {l.item}: {qty_text(l.qty)} {l.unit} × {naira(l.price)} = {naira(l.total)}")
    total = subtotal(lines) - discount
    if discount:
        body.append(f"Discount: -{naira(discount)}")
    body += ["", f"*TOTAL: {naira(total)}*", "", "Reply YES to accept and I go start.",
             f"{biz.name}{' · ' + biz.phone if biz.phone else ''}"]
    return "\n".join(body)


def whatsapp_link(text: str, phone: str = "") -> str:
    """wa.me link that opens WhatsApp with the quote typed out.

    No Business API needed: the artisan taps it, picks the chat (or it opens the
    customer's chat when a number is given) and presses send. Nigerian numbers
    like 0803... are converted to 234803...
    """
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    base = f"https://wa.me/{digits}" if digits else "https://wa.me/"
    return f"{base}?text={urlquote(text)}"
