"""Find every quantity in a transcript, deterministically.

Speech recognition gets roughly one Pidgin word in seven wrong, and a wrong
digit in "twelve feet" costs the artisan real money. So Kwota never trusts a
number it cannot point at: this module pulls each number (digits, English
number words, common Yoruba / Hausa / Igbo counting words) and the unit spoken
next to it, with the exact words it came from. The confirmation screen shows
these, and any line item whose quantity is not among them gets flagged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "a": 1, "an": 1,  # "a bag", "an hour" (only counted when a unit follows)
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}

# Single-word counting in Nigerian languages, as NaijaVox usually spells them.
LOCAL = {
    # Yoruba (counting form and the "how many" form)
    "ookan": 1, "okan": 1, "eeji": 2, "meji": 2, "eeta": 3, "meta": 3,
    "eerin": 4, "merin": 4, "aarun": 5, "marun": 5, "eefa": 6, "mefa": 6,
    "eeje": 7, "meje": 7, "eejo": 8, "mejo": 8, "eesan": 9, "mesan": 9,
    "eewa": 10, "mewa": 10, "ogun": 20, "ogbon": 30,
    # Hausa
    "daya": 1, "biyu": 2, "uku": 3, "hudu": 4, "biyar": 5, "shida": 6,
    "bakwai": 7, "takwas": 8, "tara": 9, "goma": 10, "ashirin": 20,
    "talatin": 30, "dari": 100, "dubu": 1000,
    # Igbo
    "otu": 1, "abuo": 2, "ato": 3, "ano": 4, "isii": 6, "asaa": 7,
    "asato": 8, "itoolu": 9, "iri": 10,
    # (Igbo "ise", five, is left out: in Yoruba speech "ise" is "work".)
}

# spoken unit -> canonical unit
UNITS = {
    "ft": "ft", "feet": "ft", "foot": "ft", "fit": "ft",
    "yard": "yd", "yards": "yd", "yad": "yd", "yds": "yd",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m", "mita": "m",
    "sqm": "sqm", "sqft": "sqft",
    "bag": "bag", "bags": "bag", "bagi": "bag",
    "length": "length", "lengths": "length", "lent": "length",
    "litre": "L", "litres": "L", "liter": "L", "liters": "L",
    "gallon": "gal", "gallons": "gal", "galon": "gal", "galan": "gal",
    "bucket": "bucket", "buckets": "bucket", "tin": "bucket", "tins": "bucket",
    "carton": "carton", "cartons": "carton", "katon": "carton",
    "piece": "pc", "pieces": "pc", "pcs": "pc", "pc": "pc",
    "point": "point", "points": "point",
    "room": "room", "rooms": "room",
    "coat": "coat", "coats": "coat",
    "day": "day", "days": "day",
    "hour": "hour", "hours": "hour",
    "trip": "trip", "trips": "trip",
    "tap": "pc", "taps": "pc",
}
SQUARE = {"square", "sq", "squared"}
FILLER = {"of", "the", "dem", "for", "na", "like"}

_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?k?|[a-zA-Z]+|[,.;!?]")


@dataclass
class Quantity:
    value: float
    unit: str          # canonical unit, "" when none was spoken
    words: str         # the exact words it came from, for the confirm screen
    pos: int           # token index, so line items can be matched by distance

    def label(self) -> str:
        v = int(self.value) if float(self.value).is_integer() else self.value
        return f"{v} {self.unit}".strip()


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("-", " "))


def _digits(tok: str) -> float | None:
    if not tok[0].isdigit():
        return None
    mult = 1000 if tok.endswith("k") else 1
    try:
        return float(tok.rstrip("k").replace(",", "")) * mult
    except ValueError:
        return None


def _word_number(toks: list[str], i: int) -> tuple[float, int] | None:
    """Parse an English number phrase starting at toks[i]; return (value, tokens used)."""
    total, current, j, seen, last = 0.0, 0.0, i, False, ""
    while j < len(toks):
        t = toks[j]
        if t in ONES and t not in ("a", "an"):
            # "two three" or "thirty thirteen" are two numbers, not one
            if last == "ones" or (last == "tens" and ONES[t] >= 10):
                break
            current += ONES[t]
            last = "ones"
        elif t in TENS:
            if last in ("ones", "tens"):
                break
            current += TENS[t]
            last = "tens"
        elif t in SCALES and (seen or j > i):
            current = (current or 1) * SCALES[t]
            last = "scale"
            if SCALES[t] >= 1000:
                total, current = total + current, 0.0
        elif t == "and" and seen and j + 1 < len(toks) and toks[j + 1] not in ("a", "an") and (
                toks[j + 1] in ONES or toks[j + 1] in TENS):
            last = "and"  # "one hundred and twenty"
        else:
            break
        seen = True
        j += 1
    if not seen:
        return None
    value = total + current
    # decimals: "twelve point five"
    if j + 1 < len(toks) and toks[j] == "point":
        nxt = toks[j + 1]
        if nxt in ONES and nxt not in ("a", "an") and ONES[nxt] < 10:
            value += ONES[nxt] / 10
            j += 2
        elif nxt.isdigit():
            value = float(f"{int(value)}.{nxt}")
            j += 2
    # "and a half"
    if j + 2 < len(toks) and toks[j] == "and" and toks[j + 1] in ("a", "half") and "half" in toks[j + 1:j + 3]:
        value += 0.5
        j += 3 if toks[j + 1] == "a" else 2
    return value, j - i


def _unit_after(toks: list[str], j: int) -> tuple[str, int]:
    """Look up to two filler words ahead for a unit; return (unit, tokens used)."""
    k, skipped = j, 0
    while k < len(toks) and toks[k] in FILLER and skipped < 2:
        k, skipped = k + 1, skipped + 1
    if k >= len(toks):
        return "", 0
    if toks[k] in SQUARE and k + 1 < len(toks):
        nxt = UNITS.get(toks[k + 1], "")
        if nxt in ("m", "ft"):
            return "sq" + nxt, k + 2 - j
    if toks[k] in UNITS:
        # "by" after a unit is a dimension ("12 by 10 feet") - keep simple
        return UNITS[toks[k]], k + 1 - j
    return "", 0


def find_quantities(text: str) -> list[Quantity]:
    toks = tokens(text)
    out: list[Quantity] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        parsed: tuple[float, int] | None = None
        d = _digits(t)
        if d is not None:
            used = 1
            if i + 2 < len(toks) and toks[i + 1] == "point" and toks[i + 2].isdigit():
                d, used = float(f"{t.replace(',', '')}.{toks[i + 2]}"), 3
            parsed = (d, used)
        elif t in LOCAL:
            parsed = (float(LOCAL[t]), 1)
        elif t in ("a", "an", "half"):
            if t == "half" and i + 1 < len(toks) and toks[i + 1] in ("inch", "inches"):
                i += 2
                continue
            unit, u = _unit_after(toks, i + 1)
            if unit:  # "a bag of cement", "half bag"
                val = 0.5 if t == "half" else 1.0
                out.append(Quantity(val, unit, " ".join(toks[i:i + 1 + u]), i))
                i += 1 + u
                continue
        else:
            parsed = _word_number(toks, i)
        if parsed is None:
            i += 1
            continue
        value, used = parsed
        # "half inch pipe", "one inch" are sizes, not amounts
        if i + used < len(toks) and toks[i + used] in ("inch", "inches"):
            i += used + 1
            continue
        # dimensions: "twelve by ten feet" -> 120 sq ft
        if i + used + 1 < len(toks) and toks[i + used] == "by":
            k = i + used + 1
            second = (_digits(toks[k]), 1) if _digits(toks[k]) is not None else (
                (float(LOCAL[toks[k]]), 1) if toks[k] in LOCAL else _word_number(toks, k))
            if second and second[0] is not None:
                unit, u = _unit_after(toks, k + second[1])
                area_unit = {"ft": "sqft", "m": "sqm"}.get(unit, unit)
                end = k + second[1] + u
                out.append(Quantity(value * second[0], area_unit, " ".join(toks[i:end]), i))
                i = end
                continue
        unit, u = _unit_after(toks, i + used)
        out.append(Quantity(value, unit, " ".join(toks[i:i + used + u]), i))
        i += used + u
    return out


def heard_summary(qs: list[Quantity]) -> str:
    if not qs:
        return "No numbers heard. Type the quantities in the table."
    return " · ".join(f'{q.label()}  ("{q.words}")' for q in qs)
