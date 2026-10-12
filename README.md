---
title: Kwota
emoji: 🧾
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
short_description: Talk a job through in Pidgin, send a quote on WhatsApp
---

# 🧾 Kwota: talk your quote

Kwota turns a Nigerian artisan's walk-through voice note into a clean, priced quote
they can send on WhatsApp before leaving the customer's gate.

A plumber, painter or tiler inspects the job, takes a few photos and talks:
*"Madam, the kitchen tap dey leak for two points. I go change three lengths of half inch pipe, four elbows."*
Kwota hears it, maps it onto **the artisan's own price list**, shows every number it heard
for a quick check, then makes a PDF and opens WhatsApp with the quote typed out.

## Why

Quoting is unpaid evening work. Slow quotes lose jobs, and handwritten ones look less
trustworthy than they should. Most artisans already run their business on WhatsApp voice notes,
so Kwota starts there.

## How it works

```
voice note ──► NaijaVox-2.0 (open ASR: Pidgin, Yoruba, Hausa, Igbo, Nigerian English)
                    │
photos ──► Gemma 3 (open, multimodal) ──► one-line job scope (never sizes or prices)
                    │
transcript ──► Gemma 3 ──► line items picked from YOUR price list (JSON)
                    │
            numbers.py ──► every quantity actually heard, with the words it came from
                    │
         confirm screen: unheard quantities flagged, everything editable
                    │
            PDF quote + wa.me link with the quote typed out
```

### Designed around recognition errors

NaijaVox gets roughly one Pidgin word in seven wrong on its benchmark, and a misheard
"thirteen" costs real money. So:

* **Prices only come from the artisan's list.** Gemma picks item ids; it never writes a price.
* **Quantities must be traceable.** `kwota/numbers.py` deterministically extracts every number
  (digits, English number words, Yoruba / Hausa / Igbo counting words, units like *lengths*,
  *bags*, *cartons*, *buckets*, *12 by 10 feet*) with the exact words it came from. Any line
  whose quantity isn't among them is flagged `⚠ check qty`.
* **Sizes aren't amounts.** "half inch pipe" is a spec, not 0.5 of anything.
* **Nothing sends itself.** The artisan reviews the table, then taps Send.
* If Gemma is unavailable or returns junk, a rule-based matcher drafts the quote instead.

## Run it

On a Hugging Face ZeroGPU Space it runs as-is. Locally:

```bash
pip install -r requirements.txt gradio
# fully offline with Ollama:
ollama pull gemma3:4b && KWOTA_LLM=ollama python app.py
```

`KWOTA_LLM=local|ollama|hf|aistudio` picks the Gemma backend.
Price lists are plain CSV (`pricelists/*.csv`) and are edited in the app; your details and
prices are remembered in your own browser, not on a server.

### Test the speech model on your own voice notes

`spike/RECORDING_SHEET.md` has ten lines that stress numbers (Yoruba and Hausa counting,
"thirty" vs "thirteen", dimensions). Record them, then:

```bash
python spike/run_spike.py --lang pcm
```

or use the **Test the ear** tab in the app.

```bash
pytest   # numbers, matching, Gemma validation, PDF and WhatsApp link
```

## Open models

* [Axiveri/NaijaVox-2.0](https://huggingface.co/Axiveri/NaijaVox-2.0), Apache-2.0
* [Gemma 3 12B IT](https://huggingface.co/google/gemma-3-12b-it) (ungated mirror `unsloth/gemma-3-12b-it`)

MIT licensed. Sample prices are illustrative; every artisan sets their own.
