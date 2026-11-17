# intent.md: GPS distance Quest

> All data in this repo is **synthetic**. No real people, vehicles, trips or roads are involved. The road grid sits in open sea in the Korea Strait on purpose, so that no point can be mistaken for a real location.

## The customers' problem, in my words

Advertisers pay for every kilometre a car drives inside their campaign zone. Drivers are paid on the same kilometres. Both read one number: **km per driver per day inside the zone**. If that number contains kilometres that never happened, the advertiser overpays. If it loses kilometres that did happen, the driver is underpaid. Once either side catches one wrong day, they stop trusting every report, so the cost is more than the error itself.

The rules that number must follow:

| Rule | What it means in practice |
|---|---|
| Noise | Ignore a ping that is **more than 100 m from the road**, or that would mean the car moved **faster than 150 km/h**. |
| Duplicates | Two pings from the same driver with the same timestamp count **once**. |
| Late / out-of-order | Order pings by **their own timestamp**, not by when the server received them. |
| Day cut | Timestamps are UTC, but a report day runs from **00:00 to 24:00 local time (UTC+9)**. |
| Zone | Count distance **only while the car is inside** the campaign zone. |

## How I found the problems

1. I generated a labelled synthetic dataset (`data/generate_dataset.py`, seed 20261117) with **4,411 pings** for 5 drivers over 3 local days, with pings every 10 s. It contains 129 noise pings (81 off-road, 48 on-road "teleports" above 150 km/h), 76 duplicates and 88 late pings. Every row is labelled with its fault and the car's true position.
2. I wrote down the original calculation exactly as the reports use it (`distance/calc_v0.py`).
3. `analysis/measure_problems.py` switches **one** v0 behaviour at a time and measures the change in km. The ranking below comes from that output, not from intuition.

## Three problems, ranked by impact on advertiser and driver

| # | Problem (one line) | Measured impact on this dataset | Who is hurt |
|---|---|---|---|
| **1** | **GPS noise is counted as distance.** v0 never applies the 100 m / 150 km/h rule, so each noise ping adds a detour. | **+65.6 km on 181.6 km true (+36 %)**; every one of 17 driver-day rows is inflated; worst row +8.5 km | **Advertiser** overpays on every row; the driver is "paid" for kilometres that a spot check will claw back |
| 2 | **The day is cut at 00:00 UTC instead of 00:00 UTC+9.** Morning shifts (before 09:00 local) are booked to the previous day. | 19.1 km booked to the wrong day; 12 driver-day rows wrong; worst row off by 6.9 km; **net zero** over the campaign | Both sides on **daily** numbers (daily caps, daily pay, disputes); totals unaffected |
| 3 | **Zone edges are judged on the start ping only.** A segment that leaves the zone is counted, and a segment that enters it is not. | 8.2 km of exit legs counted vs 7.6 km of entry legs missed: **about 0.6 km net**, about 8 km gross | Small and mostly self-cancelling. Leaving it unfixed slightly favours drivers. |

Checked and **not** a problem today: the 76 duplicates and 88 late pings change v0's result by **0.000 km**, because v0 already sorts by timestamp and drops (driver, timestamp) duplicates. They stay in the regression test, so that a future change cannot break that.

### Why I picked #1 (GPS noise)

* It is the only one that moves **money in one direction**: advertisers overpay on every row, with no offsetting error.
* It is the largest: 36 % of the billed distance on this data, and every driver-day row is wrong.
* #2 is serious for daily reports but cancels out over a campaign. It is also a one-line fix that I list as the next ticket.

## Acceptance test, written as numbers before the fix

Frozen in `evidence/acceptance_expected.csv`, committed **before** any fix code existed (see git history).

"Expected" means: the original v0 calculation run with the 129 labelled noise pings removed. That isolates the noise problem. Day cut and zone behaviour stay exactly as in v0 because they are out of scope here.

| ID | Acceptance criterion | Target |
|---|---|---|
| A1 | Labelled noise pings removed by the fixed calculation | **129 / 129 (100 %)** |
| A2 | Clean pings wrongly removed (false positives) | **0 of 4,118 clean + 88 late** |
| A3 | Distance per driver per report day vs `km_expected` | **all 17 rows within ±0.001 km** |
| A4 | Campaign total | **181.611 km** (from 247.176 km before, i.e. 65.565 km of noise removed) |
| A5 | Duplicates counted | **0** (76 in the data) |
| A6 | Late pings placed by own timestamp | result identical whether input is in arrival order or timestamp order |
| A7 | Regression check | **fails on v0, passes on the fix** |

Expected km per driver per report day (report day = v0's UTC day; see problem #2):

| driver | day | before (v0) | expected | noise km in v0 |
|---|---|---:|---:|---:|
| D01 | 2026-11-01 | 8.818 | 5.966 | 2.852 |
| D01 | 2026-11-02 | 18.567 | 13.246 | 5.321 |
| D01 | 2026-11-03 | 15.031 | 11.649 | 3.382 |
| D01 | 2026-11-04 | 13.865 | 8.084 | 5.781 |
| D02 | 2026-11-02 | 16.470 | 12.055 | 4.415 |
| D02 | 2026-11-03 | 22.412 | 13.943 | 8.469 |
| D02 | 2026-11-04 | 14.293 | 12.155 | 2.138 |
| D03 | 2026-11-02 | 19.580 | 13.593 | 5.987 |
| D03 | 2026-11-03 | 17.199 | 15.385 | 1.814 |
| D03 | 2026-11-04 | 12.943 | 10.680 | 2.263 |
| D04 | 2026-11-01 | 5.568 | 4.602 | 0.966 |
| D04 | 2026-11-02 | 11.829 | 8.488 | 3.341 |
| D04 | 2026-11-03 | 8.136 | 6.927 | 1.209 |
| D04 | 2026-11-04 | 9.998 | 6.537 | 3.461 |
| D05 | 2026-11-02 | 13.497 | 10.399 | 3.098 |
| D05 | 2026-11-03 | 18.009 | 13.452 | 4.557 |
| D05 | 2026-11-04 | 20.961 | 14.450 | 6.511 |
| **Total** | | **247.176** | **181.611** | **65.565** |

Edge cases the regression check must cover:

* a ping 101 m off the road is dropped, and one 99 m off is kept;
* an on-road jump implying more than 150 km/h is dropped, and a fast but legal 140 km/h move is kept;
* the good ping **right after** a spike is kept. Speed is measured from the last accepted ping, not the spike, so the driver does not lose real distance;
* a duplicate of a noise ping is not counted twice.

## What I left out to fit 4 hours

* Fixing problems #2 (day cut) and #3 (zone edges). Both are measured and documented as next tickets.
* Real map matching. The road path is a known synthetic grid; real roads would need OSM data and a map-matching library.
* Maps, dashboards, a second tool, an API or any UI.
* Recovering the distance hidden behind a removed noise ping. Counting the chord between the good pings on either side is what the rules imply, and I keep it.
* Re-anchoring when the **first** ping of a session is itself an on-road teleport. Every following real ping would then look too fast. This is a known limitation, written down as an expected-failure test.
