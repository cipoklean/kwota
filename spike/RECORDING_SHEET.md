# Spike: what does the speech model do to numbers?

Record each line as a separate WhatsApp voice note (or phone recording), the way an artisan
would really say it: natural speed, background noise is fine. Save them as `01.ogg` ... `10.ogg`
in `spike/recordings/` (or upload them on the Space's "Test the ear" tab).

| # | Say this (or your own version) | Expected numbers |
|---|---|---|
| 01 | "Madam, the kitchen tap dey leak for two points. I go change three lengths of half inch pipe." | 2 point, 3 length |
| 02 | "Give me twelve lengths pipe, eight elbows and four tee." | 12 length, 8, 4 |
| 03 | "The parlour na twelve by fifteen feet. Two buckets emulsion, one bucket primer." | 180 sqft, 2 bucket, 1 bucket |
| 04 | "We need fifteen cartons of tiles, three bag cement and one trip of sand." | 15 carton, 3 bag, 1 trip |
| 05 | "Floor na twenty-five square metres, tiling go be twenty-five square metres." | 25 sqm, 25 sqm |
| 06 | "Bring eeji bag cement and eeta carton tiles." (Yoruba counting) | 2 bag, 3 carton |
| 07 | "Buhu biyu na siminti, da biyar carton." (Hausa counting) | 2, 5 carton |
| 08 | "Two and a half bags of putty, and paint for six rooms." | 2.5 bag, 6 room |
| 09 | "E go take three days, workmanship na fifty thousand." | 3 day, 50000 |
| 10 | "Change the WC, plus thirteen lengths. No be thirty, thirteen." | 13 length, 30, 13 |

Line 10 is a trap on purpose: "thirteen" vs "thirty" is the classic misheard number.

Then run:

```
python spike/run_spike.py --lang pcm
```

It writes `spike/report.md`: transcript, numbers found, expected, and a match score per note.
