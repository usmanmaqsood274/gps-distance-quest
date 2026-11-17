# Loom script (≤ 5 min)

**0:00–0:40 The problem, for the advertiser.** Open `intent.md`, rules table. "You pay per km in the zone; drivers are paid on the same km. On this synthetic data, 26.5 % of the bill was GPS noise: kilometres that never happened."

**0:40–1:20 Why this one.** Show the ranking table: noise +65.6 km, always against the advertiser; day cut 19.1 km moved but net zero; zone edges about 0.6 km net. "I picked the one that moves money in one direction."

**1:20–2:30 Run the tool on the original.** In a terminal: `python -m qa.noise_check --calc v0`. Point at one row (D02 on 3 Nov: 22.4 km billed, 13.9 km real) and at the worst ping, P00873, at 396 km/h, which added 2.3 km. Mention the label check: 129/129 caught, 0 false alarms.

**2:30–3:20 The fix and the after.** Show `calc_v1.py` (one change). Run `python -m qa.noise_check --calc v1`, which shows 0.000 km and PASS. Open the before/after table in `evidence.md`.

**3:20–4:20 It can't come back.** Run `python -m pytest --impl=v0` (8 failed), then `python -m pytest` (13 passed, 1 known limitation). Show `git log`: the acceptance numbers were committed before the fix.

**4:20–5:00 What's next.** Day cut (one-line fix, next ticket), zone edges, first-ping teleport. "Run `./run.sh` to reproduce everything."
