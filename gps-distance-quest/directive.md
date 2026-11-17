# Final directive.md: how I used AI, written so someone else can repeat it

**Tool used:** Claude (Anthropic), in an agentic workspace with a Python shell. Python 3.13, pandas, numpy, pytest. There was no network, so no package installs were possible.

**Ground rules I gave the AI, and that anyone repeating this should give it:**

* Use synthetic data only, labelled as such, and place it somewhere that cannot be a real location. No real people, no API keys.
* Reuse a library wherever one exists. Write code only for the gap, and say which is which.
* Never trust a generated number until a second, independent method agrees with it.
* Write the acceptance numbers **before** writing the fix, and commit them, so the order is provable from git.
* Keep the scope to one problem. Measure the others, don't fix them.

## The directives, in order

Each step lists the instruction, then what I checked or corrected.

### 1. Dataset

> "Write a seeded Python generator for a SYNTHETIC GPS dataset: 5 drivers, 3 local days (UTC+9), one ping every 10 s on a 1 km road grid placed in open sea (34.0 N, 128.5 E). Some shifts must cross 09:00 local (UTC midnight) and some 00:00 local. Inject ~3 % noise (60 % thrown 110–600 m off road, 40 % on-road jumps implying more than 150 km/h, never in the first 3 pings, never adjacent), ~2 % duplicates (same driver and timestamp, received later) and ~2 % late pings. Label every row with its fault and the car's true position in `synthetic_` columns. Write the file in arrival order."

**Checked/corrected:**
* The first draft of the car simulation had tangled intersection logic that I couldn't verify by reading. I had it rewritten as "find the next grid line ahead, step or snap" before the first run.
* I verified the labels obey the rules (script output): true positions are at most 0.004 m from the road; clean pings at most 15.0 m off road; true speed at most 54.6 km/h; noise_offroad at least 113 m off road; noise_speed at least 553 km/h (later at least 162 km/h).
* The first on-road jumps were at least 1,500 m, which gave +67.5 % noise. That is unrealistic, so I changed them to 450–1,200 m (+36 %).

### 2. Original calculation (the "before")

> "Write the naive reference calculation a team would plausibly have shipped: sort by driver and timestamp, drop (driver, timestamp) duplicates, join consecutive pings into segments (break at gaps > 120 s), count a segment if its start ping is in the zone, bucket by UTC date, sum haversine. Do NOT apply the noise rule. Expose `daily_km` and `counted_segments`."

**Checked:** I read the code against the rules line by line and listed every deviation (noise not applied, UTC day cut, start-ping zone test). Those deviations became the candidate problems.

### 3. Measure and rank the problems

> "For each candidate problem, change exactly one behaviour of v0 and report the km difference, on the dataset with labelled noise removed where needed. Also verify that duplicates and late pings change nothing."

**Checked:** I built the ranking (noise +65.6 km > day cut 19.1 km moved > zone edge about 0.6 km net) from this output, not from intuition. Duplicates and late pings measured 0.000 km, so I reported them as "checked, not a problem today" rather than inventing a problem.

### 4. Freeze the acceptance numbers, then commit

> "Expected km per driver per report day = v0 on the dataset with labelled noise removed. Save it to `evidence/acceptance_expected.csv`. Write `intent.md` with numeric targets A1–A7."

**Checked:** Committed as `ec72016` before any fix code existed.

### 5. QA tool

> "Build one CLI, `qa/noise_check.py --calc v0|v1`, that works on UNLABELLED pings. It applies the noise rule independently of the calculation under test, asks the calculation which segments it billed, and reports: per driver-day km reported vs km without noise; per noise ping its location, reason (off-road metres, implied km/h) and the metres it put into the bill. If labels exist, print a caught/false-positive check. Exit 1 if any noise km is billed."

**Checked/corrected:**
* The "noise pings billed" column was wrong: `set(a) | set(b) & ids` is parsed as `a | (b & ids)`. I noticed because the column summed to more than the pings billed, and fixed it with parentheses.
* The tool crashed on v1 when there was nothing to bill: an empty pandas groupby returns a DataFrame, not a Series. I rewrote that part without `groupby.apply`.
* 75 vs 74 billed pings: I investigated rather than ignored it. One ping (P01714) straddles UTC midnight, so it is billed into two days. This is legitimate.

### 6. Regression check

> "pytest with an `--impl=v0|v1` option. Dataset tests against the frozen numbers (A1–A6), plus tiny hand-built tracks for edge cases: 99 m kept, 101 m dropped, on-road speed spike dropped, the good ping after a spike kept, 140 km/h kept, a duplicate of a noise ping counted once. Add an xfail for the known first-ping-teleport limitation. It must FAIL on v0 and PASS on v1."

**Checked/corrected:** The xfail test unexpectedly passed on v0 because its teleport point was outside the zone, so it tested nothing. I moved it inside the zone. I committed the tests (`b7419be`) and confirmed they fail on v0 (8 failed) **before** writing the fix.

### 7. Fix

> "calc_v1 = v0 plus `classify_noise` applied before building segments. Change nothing else. Speed is measured from the last ACCEPTED ping."

**Checked:** Tests: 13 passed, 1 xfail. QA tool: 0.000 km, exit 0. 17/17 driver-days equal the frozen numbers.

### 8. Independent cross-checks

> "Compare v1 against the distance from the car's TRUE positions; compare haversine against a projected distance."

**Result:** Against true positions, v0 is +37.3 % and v1 is +0.9 % (GPS jitter). Haversine and the projected distance agree within 0.15 %.

### 9. One command

> "`run.sh` regenerates the data, checks the SHA-256 against the committed copy, runs every step, and asserts the expected exit code of each (QA v0 = 1, QA v1 = 0, pytest v0 fails, pytest v1 passes)."

**Checked:** `ALL EXPECTATIONS MET` from a fresh clone (see evidence.md).

## What I would tell the next person

* `shapely` and `pyproj` were unavailable here. If you have them, swap them into `distance/geo.py` (each function names its equivalent) and rerun `./run.sh`. The numbers should move by at most about 0.3 %.
* AI drafts compiled and ran at the first attempt, but four of them were *wrong* (noise scale, count bug, crash, a test that tested nothing). Every one was found by running something and comparing numbers, not by reading code.
