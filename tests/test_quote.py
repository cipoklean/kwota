import json

from kwota import document, quote


PLUMBER = quote.load_pricelist("plumber")


def by_id(lines):
    return {l.id: l for l in lines}


def test_rules_match_items_and_quantities():
    t = ("Oga, the kitchen sink dey leak, two points. I go change three lengths of half inch pipe, "
         "four elbows, plus one new mixer tap.")
    got = by_id(quote.rule_lines(t, PLUMBER))
    assert got["leak"].qty == 2 and got["leak"].check == quote.OK
    assert got["pipe_half"].qty == 3 and got["pipe_half"].check == quote.OK
    assert got["elbow"].qty == 4
    assert got["mixer"].qty == 1


def test_square_feet_converted_for_sqm_items():
    lines = quote.rule_lines("painting, the room na twelve by ten feet", quote.load_pricelist("painter"))
    lab = by_id(lines)["labour"]
    assert lab.qty == 11.1 and lab.check == quote.CONVERTED


def test_gemma_cannot_invent_prices_or_quantities():
    t = "change three lengths of half inch pipe and fix the toilet"
    model = {"scope": "Replace pipe, fix WC", "items": [
        {"id": "pipe_half", "qty": 3, "said": "three lengths of half inch pipe", "price": 1},
        {"id": "elbow", "qty": 6, "said": ""},          # nobody said six
        {"id": "made_up", "qty": 1},                     # not on the list
        {"id": "wc_fix", "qty": None, "said": "fix the toilet"},
    ], "not_on_list": ["paint the bathroom door"]}
    lines, scope = quote.validate(model, t, PLUMBER)
    got = by_id(lines)
    assert got["pipe_half"].price == 3800 and got["pipe_half"].check == quote.OK
    assert got["elbow"].check == quote.CHECK_QTY
    assert "made_up" not in got
    assert got["wc_fix"].qty == 1 and got["wc_fix"].check == quote.NO_NUMBER
    assert any(l.check == quote.NEW_ITEM and l.price == 0 for l in lines)
    assert scope == "Replace pipe, fix WC"


def test_draft_falls_back_to_rules_when_model_breaks():
    lines, _, engine = quote.draft("four elbows", PLUMBER, generate=lambda s, p: "not json")
    assert engine.startswith("rules") and by_id(lines)["elbow"].qty == 4
    out = json.dumps({"items": [{"id": "elbow", "qty": 4, "said": "four elbows"}]})
    lines, _, engine = quote.draft("four elbows", PLUMBER, generate=lambda s, p: out)
    assert engine == "gemma"


def test_table_round_trip_recomputes_amounts():
    rows = [["Elbow", "5", "pc", "700", "999", "✓ heard", ""], ["", "", "", "", "", "", ""],
            ["Zero qty", 0, "pc", 100, 0, "", ""]]
    lines = quote.from_rows(rows)
    assert len(lines) == 1 and lines[0].total == 3500


def test_pdf_and_whatsapp(tmp_path):
    lines = [quote.Line("elbow", "Elbow / bend fitting", 4, "pc", 700, quote.OK)]
    biz = document.Business("Emeka Plumbing", "08030000000", "plumber")
    path = document.make_pdf(lines, biz, "Mrs Adebayo", "Fix kitchen leak", path=str(tmp_path / "q.pdf"))
    assert open(path, "rb").read(4) == b"%PDF"
    text = document.whatsapp_text(lines, biz, "Mrs Adebayo")
    assert "₦2,800" in text
    link = document.whatsapp_link(text, "0805 123 4567")
    assert link.startswith("https://wa.me/2348051234567?text=")


def test_spoken_naira_amount_is_a_price_not_a_quantity():
    prices = quote.load_pricelist("plumber")
    lines = quote.rule_lines("Workmanship na fifteen thousand, and four elbows.", prices)
    work = next(l for l in lines if l.id == "workmanship")
    assert work.qty == 1 and work.price == 15000 and work.check == quote.SPOKEN_PRICE
    elbow = next(l for l in lines if l.id == "elbow")
    assert elbow.qty == 4


def test_gemma_naira_quantity_becomes_price():
    prices = quote.load_pricelist("plumber")
    out = {"items": [{"id": "workmanship", "qty": 15000, "said": "fifteen thousand"}]}
    lines, _ = quote.validate(out, "workmanship na fifteen thousand", prices)
    assert lines[0].qty == 1 and lines[0].price == 15000
