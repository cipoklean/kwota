"""Kwota web app: walk the job, talk, confirm the numbers, send the quote.

1. The artisan records a voice note while inspecting the job (Pidgin, English,
   Yoruba, Hausa or Igbo) and snaps a few photos.
2. NaijaVox-2.0 transcribes it; Gemma maps it onto the artisan's own price list.
3. Every number is shown with the words it came from, so a misheard "twelve"
   is caught before the customer ever sees it.
4. One tap makes a PDF and opens WhatsApp with the quote typed out.
"""
from __future__ import annotations

import os

import gradio as gr
import pandas as pd

from kwota import asr, document, llm, quote
from kwota.numbers import find_quantities, heard_summary

if os.getenv("SPACE_ID") and os.getenv("KWOTA_PRELOAD", "1") == "1":
    # On a ZeroGPU Space, download and place the models once at startup so an
    # artisan standing in a customer's kitchen never waits on a download.
    _, asr_model = asr._asr()
    asr_model.to("cuda")
    if llm.backend() == "local":
        _, lm = llm._local()
        lm.to("cuda")

LANGS = [("Pidgin", "pcm"), ("English", "en"), ("Yorùbá", "yo"), ("Hausa", "ha"), ("Igbo", "ig")]
PRICE_COLS = ["id", "item", "unit", "price", "aliases"]


def pricelist_frame(trade: str) -> pd.DataFrame:
    items = quote.load_pricelist(trade)
    return pd.DataFrame([[p.id, p.item, p.unit, p.price, "|".join(p.aliases)] for p in items],
                        columns=PRICE_COLS)


def frame_to_items(df: pd.DataFrame) -> list[quote.PriceItem]:
    return quote.load_pricelist(df.to_csv(index=False))


def _images(files) -> list:
    from PIL import Image
    out = []
    for f in files or []:
        try:
            out.append(Image.open(f if isinstance(f, str) else f.name))
        except Exception:
            pass
    return out


def listen(voice_path, lang):
    if not voice_path:
        return ""
    sr, audio = asr.load_file(voice_path)
    return asr.transcribe(sr, audio, lang)


def draft(voice_path, lang, typed, photos, prices_df):
    """Voice note + photos -> transcript, numbers heard, draft line items."""
    transcript = (typed or "").strip()
    if voice_path:
        try:
            heard = listen(voice_path, lang)
            transcript = f"{heard} {transcript}".strip()
        except Exception as e:
            gr.Warning(f"Could not hear the voice note ({e}). Type the job instead.")
    if not transcript:
        raise gr.Error("Record a voice note or type what the job needs.")
    return redraft(transcript, photos, prices_df)


def redraft(transcript, photos, prices_df):
    prices = frame_to_items(prices_df)
    if not prices:
        raise gr.Error("Your price list is empty. Add your items first.")
    photo_notes = llm.describe_photos(_images(photos))
    gen = (lambda s, p: llm.generate(s, p)) if llm.available() else None
    lines, scope, engine = quote.draft(transcript, prices, photo_notes, generate=gen)
    scope = scope or photo_notes
    rows = pd.DataFrame(quote.to_rows(lines), columns=quote.COLUMNS)
    todo = quote.needs_attention(lines)
    notes = ("**Check these before sending:** " + "; ".join(todo)) if todo else "All quantities were heard clearly."
    who = "Gemma" if engine == "gemma" else f"the backup matcher; Gemma was unavailable: {engine[7:-1]}"
    numbers = f"**Numbers I heard:** {heard_summary(find_quantities(transcript))}"
    return (transcript, numbers, rows, f"{notes}\n\n_Drafted by {who}._", scope,
            gr.update(visible=True))


def finish(rows_df, biz_name, biz_phone, trade, customer, customer_phone, scope, discount):
    lines = quote.from_rows(rows_df.values.tolist())
    if not lines:
        raise gr.Error("The quote has no items with a quantity. Fill in the table first.")
    unpriced = [l.item for l in lines if l.price <= 0]
    if unpriced:
        raise gr.Error("Add a price for: " + ", ".join(unpriced))
    biz = document.Business(biz_name or "My Business", biz_phone or "", trade or "")
    number = document.quote_number()
    disc = float(discount or 0)
    pdf = document.make_pdf(lines, biz, customer or "", scope or "", disc, number=number)
    text = document.whatsapp_text(lines, biz, customer or "", scope or "", disc, number)
    link = document.whatsapp_link(text, customer_phone or "")
    total = document.subtotal(lines) - disc
    button = (f'<a href="{link}" target="_blank" style="display:block;text-align:center;'
              f'padding:14px;border-radius:10px;background:#25D366;color:white;font-weight:700;'
              f'text-decoration:none;font-size:1.1em">Send on WhatsApp · {document.naira(total)}</a>')
    return pdf, button, text


def spike(files, lang, expected):
    """Batch-test the ear: how does NaijaVox treat the numbers in real voice notes?"""
    exp = [e.strip() for e in (expected or "").splitlines()]
    out = []
    for i, f in enumerate(files or []):
        path = f if isinstance(f, str) else f.name
        try:
            text = listen(path, lang)
        except Exception as e:
            text = f"(failed: {e})"
        qs = find_quantities(text)
        got = ", ".join(q.label() for q in qs) or "-"
        want = exp[i] if i < len(exp) else ""
        verdict = ""
        if want:
            wanted = {w.strip().lower() for w in want.split(",") if w.strip()}
            have = {q.label().lower() for q in qs}
            verdict = f"{len(wanted & have)}/{len(wanted)}"
        out.append([os.path.basename(path), text, got, want, verdict])
    return pd.DataFrame(out, columns=["File", "Transcript", "Numbers found", "Expected", "Match"])


with gr.Blocks(title="Kwota: talk your quote") as demo:
    saved = gr.BrowserState({"name": "", "phone": "", "trade": "plumber", "prices": ""}, storage_key="kwota-biz")
    gr.Markdown("# 🧾 Kwota\n**Walk the job. Talk. Send a clean quote on WhatsApp before you leave the gate.**")

    with gr.Tab("Quote"):
        with gr.Accordion("Your business and price list", open=False):
            with gr.Row():
                biz_name = gr.Textbox(label="Business name", placeholder="Emeka Plumbing Works")
                biz_phone = gr.Textbox(label="Your phone", placeholder="0803 000 0000")
                trade = gr.Dropdown(quote.trades(), value="plumber", label="Trade (sample price list)")
            prices = gr.Dataframe(pricelist_frame("plumber"), headers=PRICE_COLS, interactive=True,
                                  label="Your prices (₦). Edit freely; 'aliases' are words you say for the item, split by |",
                                  wrap=True)

        lang = gr.Radio(LANGS, value="pcm", label="Language you'll speak")
        voice = gr.Audio(sources=["microphone", "upload"], type="filepath",
                         label="🎤 Talk through the job: what needs doing, and how many")
        photos = gr.File(file_types=["image"], file_count="multiple", label="📷 Photos of the job (optional)")
        typed = gr.Textbox(label="...or type it", lines=2,
                           placeholder="Kitchen tap dey leak, two points. Change three lengths of half inch pipe, four elbows.")
        go = gr.Button("Draft my quote", variant="primary", size="lg")

        with gr.Column(visible=False) as review:
            gr.Markdown("### Confirm the numbers")
            transcript = gr.Textbox(label="What Kwota heard (fix any wrong word, then Re-draft)", lines=3)
            numbers = gr.Markdown()
            rows = gr.Dataframe(headers=quote.COLUMNS, interactive=True, wrap=True,
                                label="Line items: edit any quantity or price. Amounts are recalculated.")
            attention = gr.Markdown()
            redo = gr.Button("Re-draft from the text")
            scope = gr.Textbox(label="Job description on the quote", lines=2)
            with gr.Row():
                customer = gr.Textbox(label="Customer name", placeholder="Mrs Adebayo")
                customer_phone = gr.Textbox(label="Customer WhatsApp (optional)", placeholder="0805 000 0000")
                discount = gr.Number(label="Discount (₦)", value=0)
            make = gr.Button("Make the quote", variant="primary", size="lg")
            pdf = gr.File(label="Quote PDF")
            send = gr.HTML()
            message = gr.Textbox(label="WhatsApp message", lines=8, buttons=["copy"])

    with gr.Tab("Test the ear"):
        gr.Markdown("Upload a batch of voice notes and, optionally, the numbers each one *should* contain "
                    "(one line per file, like `3 length, 4, 2 point`). Shows exactly what the speech model "
                    "does to numbers.")
        s_files = gr.File(file_count="multiple", file_types=["audio"], label="Voice notes (.ogg/.opus/.m4a/.wav/.mp3)")
        s_lang = gr.Radio(LANGS, value="pcm", label="Language")
        s_expected = gr.Textbox(label="Expected numbers, one line per file (optional)", lines=5)
        s_go = gr.Button("Run", variant="primary")
        s_out = gr.Dataframe(wrap=True)
        s_go.click(spike, [s_files, s_lang, s_expected], s_out)

    gr.Markdown("Open models only: **NaijaVox-2.0** listens, **Gemma 3** drafts the quote and reads the "
                "photos. Prices always come from your own list, never from the model.")

    trade.input(pricelist_frame, trade, prices)
    go.click(draft, [voice, lang, typed, photos, prices],
             [transcript, numbers, rows, attention, scope, review])
    redo.click(redraft, [transcript, photos, prices],
               [transcript, numbers, rows, attention, scope, review])
    make.click(finish, [rows, biz_name, biz_phone, trade, customer, customer_phone, scope, discount],
               [pdf, send, message])

    # remember the artisan's details and prices on their own phone
    # (browser storage: no account, nothing kept on a server)
    def restore(s):
        df = pricelist_frame(s.get("trade") or "plumber")
        if s.get("prices"):
            try:
                df = pricelist_frame(s["prices"])
            except Exception:
                pass
        return s.get("name", ""), s.get("phone", ""), s.get("trade") or "plumber", df

    def remember(n, p, t, df):
        return {"name": n, "phone": p, "trade": t, "prices": df.to_csv(index=False)}

    demo.load(restore, saved, [biz_name, biz_phone, trade, prices])
    for c in (biz_name, biz_phone, trade, prices):
        c.change(remember, [biz_name, biz_phone, trade, prices], saved)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="green"))
