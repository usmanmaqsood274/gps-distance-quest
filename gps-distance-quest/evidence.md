# evidence.md: GPS noise removed from km per driver per day

> Synthetic data only (`data/pings_SYNTHETIC.csv`, 4,411 pings, seed 20261117). Every number below is produced by `./run.sh` and stored in `evidence/`.

## Result in one paragraph

The original calculation (v0) billed **247.176 km**. **65.565 km (26.5 % of the bill, 36 % on top of the real distance)** of that came from **GPS-noise pings**: points thrown more than 100 m off the road, or jumps faster than 150 km/h. The fixed calculation (v1) bills **181.611 km**. Every one of the 17 driver-day rows now matches the acceptance number frozen before the fix, to the metre. The QA tool and the regression check both fail on v0 and pass on v1.

## Before and after, per driver per day

The report day is still the UTC date, exactly as v0 cuts it. Fixing the day cut is problem #2, which is out of scope here; see "Still not solved".

| driver | report day | before (v0) km | after (v1) km | expected (frozen) | change | after − expected |
|---|---|---:|---:|---:|---:|---:|
| D01 | 2026-11-01 | 8.818 | 5.966 | 5.966 | −32.3 % | 0.000 |
| D01 | 2026-11-02 | 18.567 | 13.246 | 13.246 | −28.7 % | 0.000 |
| D01 | 2026-11-03 | 15.031 | 11.649 | 11.649 | −22.5 % | 0.000 |
| D01 | 2026-11-04 | 13.865 | 8.084 | 8.084 | −41.7 % | 0.000 |
| D02 | 2026-11-02 | 16.470 | 12.055 | 12.055 | −26.8 % | 0.000 |
| D02 | 2026-11-03 | 22.412 | 13.943 | 13.943 | −37.8 % | 0.000 |
| D02 | 2026-11-04 | 14.293 | 12.155 | 12.155 | −15.0 % | 0.000 |
| D03 | 2026-11-02 | 19.580 | 13.593 | 13.593 | −30.6 % | 0.000 |
| D03 | 2026-11-03 | 17.199 | 15.385 | 15.385 | −10.5 % | 0.000 |
| D03 | 2026-11-04 | 12.943 | 10.680 | 10.680 | −17.5 % | 0.000 |
| D04 | 2026-11-01 | 5.568 | 4.602 | 4.602 | −17.3 % | 0.000 |
| D04 | 2026-11-02 | 11.829 | 8.488 | 8.488 | −28.2 % | 0.000 |
| D04 | 2026-11-03 | 8.136 | 6.927 | 6.927 | −14.9 % | 0.000 |
| D04 | 2026-11-04 | 9.998 | 6.537 | 6.537 | −34.6 % | 0.000 |
| D05 | 2026-11-02 | 13.497 | 10.399 | 10.399 | −23.0 % | 0.000 |
| D05 | 2026-11-03 | 18.009 | 13.452 | 13.452 | −25.3 % | 0.000 |
| D05 | 2026-11-04 | 20.961 | 14.450 | 14.450 | −31.1 % | 0.000 |

Per driver:

| driver | before km | after km | change |
|---|---:|---:|---:|
| D01 | 56.281 | 38.945 | −30.8 % |
| D02 | 53.175 | 38.153 | −28.3 % |
| D03 | 49.722 | 39.658 | −20.2 % |
| D04 | 35.531 | 26.554 | −25.3 % |
| D05 | 52.467 | 38.301 | −27.0 % |
| **Total** | **247.176** | **181.611** | **−26.5 %** |

The noise share varies by driver because noise pings only cost money when they land next to an in-zone segment. 74 of the 129 noise pings were billed; the rest fell on legs outside the zone.

## Acceptance test vs. result

These criteria were set in `intent.md` and committed **before** the fix existed. Commit `ec72016` holds the frozen numbers, `b7419be` the tool and tests, and the following commit the fix.

| ID | Target | Result |
|---|---|---|
| A1 | 129/129 labelled noise pings removed | **129/129** (QA tool label check plus test `A1_A2`) |
| A2 | 0 clean pings removed | **0** of 4,206 clean and late pings |
| A3 | 17/17 driver-days within ±0.001 km of expected | **17/17**, max difference 0.000 km |
| A4 | Total 181.611 km | **181.611 km** |
| A5 | 0 duplicates counted | **0** (the 76 duplicates change nothing; also true in v0) |
| A6 | Late pings placed by timestamp | result identical after shuffling arrival order |
| A7 | Regression check fails on v0, passes on v1 | **v0: 8 failed, 5 passed. v1: 13 passed, 1 xfail** |

An independent sanity check that does not use the acceptance numbers: running v0's logic on the car's **true** positions (`synthetic_true_lat/lon`) gives **179.979 km**. Against that, v0 reads **+37.3 %** and v1 reads **+0.9 %**. The remaining 0.9 % is ordinary GPS jitter (σ = 5 m on clean pings) that the rules intentionally keep.

## How to reproduce

```bash
pip install -r requirements.txt
./run.sh                                  # ends with "ALL EXPECTATIONS MET", exit 0
```

Or step by step:

```bash
python -m qa.noise_check --calc v0       # FAIL: 65.565 km of noise billed, lists every noise ping and why
python -m qa.noise_check --calc v1       # PASS: 0.000 km
python -m pytest --impl=v0               # 8 failed
python -m pytest                         # 13 passed, 1 xfailed
python analysis/before_after.py          # the tables above
```

The dataset is regenerated from its seed on every run and checked against `data/SHA256SUMS`, so a reviewer is testing exactly the data I tested.

## Root cause

v0 joins **every** de-duplicated ping to the next one and adds up the lengths. It never applies the rule that a ping more than 100 m off the road, or one implying more than 150 km/h, must be ignored.

Here is what one noise ping does. If the car drives A → B → C and B is thrown 300 m off the road, v0 bills A→B′ plus B′→C, about 600 m of detour, instead of A→C. On-road "teleports" are worse: the worst single ping, `P00873` (D03, 2026-11-02 14:03:40 local), implied 396 km/h and alone added **2.31 km** to that day.

The fix (`distance/calc_v1.py`) applies `rules.classify_noise` before building segments. One detail matters here. **Speed is measured from the last accepted ping, not the previous raw ping.** If it were measured from the raw ping, the good ping right after a spike would also look too fast and be thrown away, and the driver would lose real distance. The test `test_ping_after_spike_is_kept` pins this down.

## Regression check: fails on old, passes on new

`tests/test_noise_regression.py` runs against either calculation (`--impl=v0|v1`). Full logs are in `evidence/regression_v0.txt` and `evidence/regression_v1.txt`.

| Test | v0 | v1 | What it guards |
|---|---|---|---|
| frozen acceptance numbers still match dataset | pass | pass | the dataset has not drifted since the numbers were frozen |
| A3 km per driver per day | **FAIL** | pass | all 17 rows within 1 m |
| A4 campaign total | **FAIL** | pass | 181.611 km |
| A1/A2 no noise billed, no clean ping dropped | **FAIL** | pass | the counted segments equal the expected set exactly |
| A5 duplicates counted once | pass | pass | v0 already handled this; kept so it cannot break |
| A6 late pings by own timestamp | pass | pass | as above |
| off-road 99 m kept | pass | pass | threshold edge: not over-filtering |
| off-road 101 m dropped | **FAIL** | pass | threshold edge |
| off-road 300 m dropped | **FAIL** | pass | |
| on-road speed spike dropped | **FAIL** | pass | the speed rule on its own (on road, so off-road alone would miss it) |
| ping after spike kept | **FAIL** | pass | measures speed from the last *good* ping |
| 140 km/h legal movement kept | pass | pass | not over-filtering |
| duplicate of a noise ping not counted | **FAIL** | pass | duplicates and noise together |
| first ping is a teleport | xfail | xfail | **known limitation**, see below |

The 5 tests that pass on v0 do so on purpose: they guard behaviour v0 already got right, so the fix must not break it. CI (`.github/workflows/regression.yml`) runs the v1 tests and the QA tool on every push. I wrote the workflow but could not run it in my build environment.

## What I reused vs. what I built

| Need | Reused | Built (the gap) |
|---|---|---|
| Time zone, UTC+9 | Python `zoneinfo` (`Asia/Seoul`) | n/a |
| Tables, grouping, sorting, de-duplication | `pandas` | n/a |
| Test framework | `pytest` (one `--impl` option added) | n/a |
| Distance, distance to road, point in zone | I wanted `pyproj` + `shapely`, but **neither was installed and package installs were blocked** in my build environment | about 60 lines in `distance/geo.py`: haversine, a local projection, point-to-segment and point-in-polygon. Cross-checked: haversine and the projected distance agree within 0.15 %. Each function names its shapely/pyproj equivalent so it can be swapped. |
| **The noise rule itself** | nothing existing encodes "100 m off road or 150 km/h from the last good ping" | `distance/rules.py::classify_noise` |
| **The QA tool** | n/a | `qa/noise_check.py`: works on unlabelled data and attributes noise km per driver-day and per ping |

## Where AI helped and where I corrected it

AI (Claude) wrote the first drafts of the generator, the calculations, the QA tool and the tests. These are the corrections I made after checking its output; `directive.md` has the full list.

1. **Unrealistic noise.** The first generator made on-road jumps of at least 1,500 m, which produced +67.5 % noise. That is cartoonish, so I narrowed the jumps to 450–1,200 m (still at least 162 km/h). Result: +36 %.
2. **Labels not trusted blindly.** I checked that the generator's labels obey the rules: clean pings are at most 15.0 m off road, true speed is at most 54.6 km/h, noise is at least 113 m off road or at least 553 km/h. Without this, "129/129 caught" would mean nothing.
3. **QA tool count bug.** The per-day "noise pings billed" column used `a | b & c`, which Python reads as `a | (b & c)`, so it counted non-noise pings. I caught it because the column summed to more than the billed total, and fixed it.
4. **QA tool crash** when nothing was billed (an empty pandas groupby), found by running it on v1. Fixed.
5. **A test that passed for the wrong reason.** The known-limitation test passed on v0 because its teleport point lay outside the zone. I moved the point inside the zone.
6. **Count mismatch explained, not hidden.** 75 billed-ping rows vs 74 billed pings: one ping (`P01714`) sits on the UTC-midnight line, so it is billed into two report days.

## Still not solved

| What | Size on this data | Next step |
|---|---|---|
| **#2 Day cut at 00:00 UTC instead of 00:00 UTC+9** | 19.1 km booked to the wrong day; 12 driver-day rows wrong (worst 6.9 km); net 0. That is why D01/D04 still show a "2026-11-01" row for shifts that started 08:35 and 08:45 local on 2 November. | One line: bucket by `ts.tz_convert(LOCAL_TZ).date()`. Then re-freeze the expected numbers and add a test for shifts crossing 09:00 and 00:00 local. |
| **#3 Zone edge judged on the start ping only** | 8.2 km of exit legs counted, 7.6 km of entry legs missed, about 0.6 km net | Clip each segment to the zone polygon (shapely `intersection`). Needs a product decision on partial segments. |
| **First ping of a session is a teleport** | 0 cases in this data (the generator never puts noise in the first 3 pings), but possible in real data | If N pings in a row fail the speed check and agree with each other, re-anchor on them. xfail test in place. |
| Distance hidden behind removed pings | the chord between good pings slightly under-counts curves | Map-match to the road graph. |
| Sphere vs ellipsoid | haversine on a sphere differs from WGS84 by about 0.2–0.3 % at this latitude, the same for before and after | Use `pyproj.Geod` when installable. |
| Real roads | the road path is a synthetic grid | Production needs OSM road geometry plus map matching (e.g. OSRM / Valhalla). |
| Rule thresholds on real data | 100 m / 150 km/h are the brief's rules, not tuned on real GPS | Run the QA tool on a sanitized real sample and review borderline flags. |
