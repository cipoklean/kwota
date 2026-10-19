"""Turn a walk-through voice note into priced line items.

Two paths, one rulebook:
  * Gemma reads the transcript (and an optional description of the photos)
    and picks items from the artisan's price list with quantities.
  * A rule-based matcher does the same with aliases and nearby numbers. It is
    the fallback when no model is available, and it is how Gemma's answer is
    checked.

Whichever path runs, prices only ever come from the artisan's own list, and a
quantity that cannot be traced to a number actually heard in the voice note
is flagged on the confirmation screen.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from .numbers import Quantity, find_quantities, tokens

SQFT_TO_SQM = 0.092903
COUNT_UNITS = {"job", "pc", "point", "room"}  # one is a fair default when no number is said

OK = "✓ heard"
CHECK_QTY = "⚠ check qty"
NO_NUMBER = "⚠ no number heard"
CONVERTED = "⚠ converted"
NEW_ITEM = "⚠ not on price list"
SPOKEN_PRICE = "⚠ price you said"
MONEY_MIN = 1000  # a bare "fifteen thousand" is naira, never fifteen thousand call-outs


def _is_money(q: Quantity) -> bool:
    return q.unit == "" and q.value >= MONEY_MIN


@dataclass
class PriceItem:
    id: str
    item: str
    unit: str
    price: float
    aliases: list[str] = field(default_factory=list)


@dataclass
class Line:
    id: str
    item: str
    qty: float
    unit: str
    price: float
    check: str
    heard: str = ""

    @property
    def total(self) -> float:
        return round(self.qty * self.price, 2)


# ---------------------------------------------------------------- price lists

PRICELISTS = Path(__file__).resolve().parent.parent / "pricelists"


def trades() -> list[str]:
    return sorted(p.stem for p in PRICELISTS.glob("*.csv"))


def load_pricelist(trade_or_csv: str) -> list[PriceItem]:
    """Load a bundled trade ('plumber') or CSV text the artisan pasted/edited."""
    path = PRICELISTS / f"{trade_or_csv}.csv"
    text = path.read_text() if path.exists() else trade_or_csv
    items = []
    for row in csv.DictReader(io.StringIO(text.strip())):
        if not row.get("item"):
            continue
        items.append(PriceItem(
            id=(row.get("id") or re.sub(r"\W+", "_", row["item"].lower())).strip(),
            item=row["item"].strip(),
            unit=(row.get("unit") or "pc").strip(),
            price=float(str(row.get("price") or 0).replace(",", "") or 0),
            aliases=[a.strip().lower() for a in (row.get("aliases") or "").split("|") if a.strip()]
            or [row["item"].strip().lower()],
        ))
    return items


def pricelist_csv(items: list[PriceItem]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "item", "unit", "price", "aliases"])
    for p in items:
        w.writerow([p.id, p.item, p.unit, int(p.price) if p.price.is_integer() else p.price,
                    "|".join(p.aliases)])
    return buf.getvalue()


# ---------------------------------------------------------- quantity matching

def _fit(q: Quantity, unit: str) -> tuple[float, str] | None:
    """Can quantity q fill an item sold per `unit`? Returns (qty, check)."""
    if q.unit == unit:
        return q.value, OK
    if q.unit == "sqft" and unit == "sqm":
        return round(q.value * SQFT_TO_SQM, 1), CONVERTED
    if q.unit == "sqm" and unit == "sqft":
        return round(q.value / SQFT_TO_SQM, 1), CONVERTED
    if _is_money(q):
        return None
    if q.unit == "" and unit not in ("sqm", "sqft"):
        return q.value, CHECK_QTY
    if unit in ("bucket", "gal", "carton", "bag", "length", "pc") and q.unit == "pc":
        return q.value, CHECK_QTY
    return None


def _alias_hits(toks: list[str], alias: str) -> list[int]:
    a = alias.split()
    hits = []
    for i in range(len(toks) - len(a) + 1):
        window = toks[i:i + len(a)]
        if window == a:
            hits.append(i)
        elif len(alias) >= 5 and fuzz.ratio(" ".join(window), alias) >= 85:
            hits.append(i)  # NaijaVox spelling drift: "cistan", "emulshon"
    return hits


def rule_lines(transcript: str, prices: list[PriceItem]) -> list[Line]:
    toks = tokens(transcript)
    qs = find_quantities(transcript)
    used_tokens: set[int] = set()
    used_qs: set[int] = set()
    lines: list[Line] = []
    # longest aliases first, so "half inch pipe" wins over "pipe"
    candidates = sorted(((len(a.split()), a, p) for p in prices for a in p.aliases),
                        key=lambda c: -c[0])
    found: dict[str, int] = {}
    for n, alias, p in candidates:
        if p.id in found:
            continue
        for h in _alias_hits(toks, alias):
            span = set(range(h, h + n))
            if span & used_tokens:
                continue
            used_tokens |= span
            found[p.id] = h
            break
    for p in sorted(prices, key=lambda p: found.get(p.id, 10**9)):
        if p.id not in found:
            continue
        pos = found[p.id]
        if p.unit == "job":
            # "workmanship na fifty thousand": the artisan is naming his price for the job
            money = [(qi, q) for qi, q in enumerate(qs)
                     if qi not in used_qs and _is_money(q) and 0 <= q.pos - pos <= 6]
            if money:
                qi, q = money[0]
                used_qs.add(qi)
                lines.append(Line(p.id, p.item, 1, p.unit, q.value, SPOKEN_PRICE, q.words))
                continue
        best = None
        for qi, q in enumerate(qs):
            if qi in used_qs:
                continue
            dist = abs(q.pos - pos)
            if dist > 10:
                continue
            fit = _fit(q, p.unit)
            if fit is None:
                continue
            score = dist + (0 if fit[1] == OK else 3) + (0 if q.pos <= pos else 1)
            if best is None or score < best[0]:
                best = (score, qi, fit, q)
        if best:
            _, qi, (qty, check), q = best
            if check == CHECK_QTY and q.unit == "" and 0 <= pos - (q.pos + len(q.words.split())) <= 2:
                check = OK  # "four elbows": the number sits right before the item
            used_qs.add(qi)
            heard = q.words
            if check == CONVERTED:
                heard = f"{q.words} = {qty} {p.unit}"
            lines.append(Line(p.id, p.item, qty, p.unit, p.price, check, heard))
        elif p.unit in COUNT_UNITS:
            lines.append(Line(p.id, p.item, 1, p.unit, p.price, NO_NUMBER))
        else:
            lines.append(Line(p.id, p.item, 0, p.unit, p.price, NO_NUMBER))
    return lines


# ------------------------------------------------------------------ Gemma path

SYSTEM = (
    "You are Kwota, an estimator that turns a Nigerian artisan's walk-through voice note "
    "into quote line items. The voice note may be in Nigerian Pidgin, English, Yoruba, Hausa "
    "or Igbo, and the transcript may contain recognition mistakes. "
    "Use ONLY items from the price list, by their id. Never invent prices. "
    "Use ONLY quantities the artisan actually said; if no quantity was said for an item, use null. "
    "Reply with JSON only, no prose."
)


def build_prompt(transcript: str, prices: list[PriceItem], photo_notes: str = "") -> str:
    plist = [{"id": p.id, "item": p.item, "unit": p.unit, "aliases": p.aliases[:4]} for p in prices]
    parts = [
        "Price list (sold per unit):",
        json.dumps(plist, ensure_ascii=False),
        f'Voice note transcript: "{transcript.strip()}"',
    ]
    if photo_notes.strip():
        parts.append(f"What the photos show (scope only, never quantities): {photo_notes.strip()}")
    parts.append(
        'Return {"scope": "<one plain-English sentence describing the job>", '
        '"items": [{"id": "<price list id>", "qty": <number or null>, '
        '"said": "<the exact words from the transcript that gave this item and quantity>"}], '
        '"not_on_list": ["<work the artisan mentioned that has no price list item>"]}'
    )
    return "\n".join(parts)


def parse_model_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("model returned no JSON")
    return json.loads(m.group(0))


def validate(model_out: dict, transcript: str, prices: list[PriceItem]) -> tuple[list[Line], str]:
    """Keep Gemma honest: list prices only, and flag any quantity nobody said."""
    by_id = {p.id: p for p in prices}
    heard = find_quantities(transcript)
    lines: list[Line] = []
    seen: set[str] = set()
    for it in model_out.get("items", []):
        p = by_id.get(str(it.get("id", "")))
        if p is None or p.id in seen:
            continue
        seen.add(p.id)
        qty = it.get("qty")
        said = str(it.get("said") or "")[:80]
        if qty in (None, "", 0):
            lines.append(Line(p.id, p.item, 1 if p.unit in COUNT_UNITS else 0, p.unit, p.price,
                              NO_NUMBER, said))
            continue
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            lines.append(Line(p.id, p.item, 0, p.unit, p.price, NO_NUMBER, said))
            continue
        if qty >= MONEY_MIN and p.unit in COUNT_UNITS:
            # Gemma read a naira amount as a quantity; keep the amount as the job price
            lines.append(Line(p.id, p.item, 1, p.unit, qty, SPOKEN_PRICE, said))
            continue
        check = CHECK_QTY
        for q in heard:
            fit = _fit(q, p.unit)
            if fit and abs(fit[0] - qty) <= max(0.05 * qty, 0.11):
                check = OK if fit[1] == OK else fit[1]
                said = said or q.words
                break
        lines.append(Line(p.id, p.item, qty, p.unit, p.price, check, said))
    for extra in model_out.get("not_on_list", [])[:5]:
        if str(extra).strip():
            lines.append(Line("", str(extra).strip()[:60], 1, "job", 0, NEW_ITEM))
    return lines, str(model_out.get("scope", "")).strip()


def draft(transcript: str, prices: list[PriceItem], photo_notes: str = "",
          generate=None) -> tuple[list[Line], str, str]:
    """Return (lines, scope sentence, which engine ran)."""
    why = "no model configured"
    if generate is not None:
        try:
            out = parse_model_json(generate(SYSTEM, build_prompt(transcript, prices, photo_notes)))
            lines, scope = validate(out, transcript, prices)
            if lines:
                return lines, scope, "gemma"
            why = "Gemma matched no price-list items"
        except Exception as e:  # fall through to the rules
            why = f"{type(e).__name__}: {str(e)[:160]}"
            print(f"Gemma draft failed, using rules: {why}", flush=True)
    return rule_lines(transcript, prices), "", f"rules ({why})"


# ---------------------------------------------------------------- table glue

COLUMNS = ["Item", "Qty", "Unit", "Unit price (₦)", "Amount (₦)", "Check", "Heard as"]


def to_rows(lines: list[Line]) -> list[list]:
    return [[l.item, l.qty, l.unit, l.price, l.total, l.check, l.heard] for l in lines]


def from_rows(rows) -> list[Line]:
    """Read the (possibly edited) confirmation table back, recomputing amounts."""
    out = []
    for r in rows:
        r = list(r) + [""] * (7 - len(r))
        if not str(r[0]).strip():
            continue
        try:
            qty = float(str(r[1]).replace(",", "") or 0)
            price = float(str(r[3]).replace(",", "").replace("₦", "") or 0)
        except ValueError:
            continue
        if qty <= 0:
            continue
        out.append(Line("", str(r[0]).strip(), qty, str(r[2]).strip(), price, str(r[5]), str(r[6])))
    return out


def needs_attention(lines: list[Line]) -> list[str]:
    return [f"{l.item}: {l.check.lstrip('⚠ ')}" for l in lines if l.check.startswith("⚠")]
