"""Run NaijaVox over real voice notes and report what happens to the numbers.

    python spike/run_spike.py --lang pcm [--dir spike/recordings] [--expected spike/expected.txt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kwota import asr  # noqa: E402
from kwota.numbers import find_quantities  # noqa: E402

AUDIO = {".ogg", ".opus", ".m4a", ".mp3", ".wav", ".aac", ".webm"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="spike/recordings")
    ap.add_argument("--expected", default="spike/expected.txt")
    ap.add_argument("--lang", default="pcm")
    a = ap.parse_args()

    files = sorted(p for p in Path(a.dir).iterdir() if p.suffix.lower() in AUDIO)
    exp_path = Path(a.expected)
    expected = exp_path.read_text().splitlines() if exp_path.exists() else []
    rows, hit, want_total = [], 0, 0
    for i, f in enumerate(files):
        sr, audio = asr.load_file(str(f))
        text = asr.transcribe(sr, audio, a.lang)
        got = [q.label().lower() for q in find_quantities(text)]
        want = [w.strip().lower() for w in (expected[i] if i < len(expected) else "").split(",") if w.strip()]
        matched = sum(1 for w in want if w in got)
        hit, want_total = hit + matched, want_total + len(want)
        rows.append(f"| {f.name} | {text} | {', '.join(got) or '-'} | {', '.join(want)} | {matched}/{len(want)} |")
        print(f.name, "|", text, "|", got, flush=True)
    report = ["# Spike report", "",
              f"Numbers recovered: **{hit}/{want_total}** across {len(files)} voice notes ({a.lang}).", "",
              "| File | Transcript | Numbers found | Expected | Match |", "|---|---|---|---|---|", *rows]
    Path("spike/report.md").write_text("\n".join(report) + "\n")
    print(f"\n{hit}/{want_total} numbers recovered. Report: spike/report.md")


if __name__ == "__main__":
    main()
