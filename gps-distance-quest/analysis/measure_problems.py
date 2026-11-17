"""Measure the impact (in km) of each candidate problem, to rank them.

Uses the generator's ground-truth labels, so this is an analysis script, not
part of the production calculation. Each problem is measured by switching ONE
behaviour of v0 at a time and comparing kilometres.

Run: python analysis/measure_problems.py   -> writes evidence/problem_ranking.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance import calc_v0  # noqa: E402
from distance.data_io import REPO, load_geo, load_pings  # noqa: E402
from distance.rules import LOCAL_TZ  # noqa: E402

geo = load_geo()
raw = load_pings(with_labels=True)
is_noise = raw["synthetic_fault"].str.startswith("noise")
pings = raw.drop(columns=[c for c in raw.columns if c.startswith("synthetic_") or c == "dataset"])
clean = pings[~is_noise.values]


def km(seg):
    return seg["m"].sum() / 1000


# P1 - noise
seg_all = calc_v0.counted_segments_v0(pings, geo)
seg_clean = calc_v0.counted_segments_v0(clean, geo)
p1_total = km(seg_all) - km(seg_clean)
by_day_all = seg_all.groupby(["driver_id", "report_day"])["m"].sum() / 1000
by_day_clean = seg_clean.groupby(["driver_id", "report_day"])["m"].sum() / 1000
p1_worst = (by_day_all - by_day_clean).max()

# P2 - day cut at 00:00 UTC instead of 00:00 UTC+9 (measured on noise-free data)
s = seg_clean.copy()
s["local_day"] = s["start_ts_utc"].dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d")
utc = s.groupby(["driver_id", "report_day"])["m"].sum() / 1000
loc = s.groupby(["driver_id", "local_day"])["m"].sum() / 1000
loc.index = loc.index.set_names(["driver_id", "report_day"])
diff = utc.sub(loc, fill_value=0)
p2_moved = diff.abs().sum() / 2
p2_worst = diff.abs().max()
p2_driver_days_wrong = int((diff.abs() > 0.001).sum())

# P3 - zone: v0 counts a segment if its START is inside; the rule needs the vehicle inside
segs = calc_v0.build_segments(calc_v0.sort_and_dedupe(clean))
start_in = geo.zone.contains(segs["lat1"].values, segs["lon1"].values)
end_in = geo.zone.contains(segs["lat2"].values, segs["lon2"].values)
p3_over = segs.loc[start_in & ~end_in, "m"].sum() / 1000
p3_under = segs.loc[~start_in & end_in, "m"].sum() / 1000

# Data faults v0 already handles: duplicates and late pings
dups = int((raw["synthetic_fault"] == "duplicate").sum())
late = int((raw["synthetic_fault"] == "late").sum())
no_dups = clean[(raw.loc[~is_noise.values, "synthetic_fault"] != "duplicate").values]
dup_effect = km(seg_clean) - km(calc_v0.counted_segments_v0(no_dups, geo))
arrival_order = clean.sort_values("received_at_utc")  # v0 must not care about arrival order
late_effect = km(seg_clean) - km(calc_v0.counted_segments_v0(arrival_order, geo))

total_clean = km(seg_clean)
rows = [
    dict(problem="P1 GPS noise counted as distance", direction="over-pays (advertiser loses)",
         km_impact=round(p1_total, 3), pct_of_true=round(100 * p1_total / total_clean, 1),
         worst_driver_day_km=round(p1_worst, 3), note=f"{int(is_noise.sum())} noise pings, all counted"),
    dict(problem="P2 day cut at 00:00 UTC not 00:00 UTC+9", direction="km moved between days, net 0",
         km_impact=round(p2_moved, 3), pct_of_true=round(100 * p2_moved / total_clean, 1),
         worst_driver_day_km=round(p2_worst, 3), note=f"{p2_driver_days_wrong} driver-day rows wrong"),
    dict(problem="P3 boundary segments counted on start ping only", direction="over-counts exits, misses entries",
         km_impact=round(p3_over, 3), pct_of_true=round(100 * p3_over / total_clean, 1),
         worst_driver_day_km=None, note=f"exit legs counted {p3_over:.3f} km, entry legs missed {p3_under:.3f} km"),
    dict(problem="(checked) duplicate pings", direction="none today", km_impact=round(dup_effect, 3),
         pct_of_true=0.0, worst_driver_day_km=None, note=f"{dups} duplicates, v0 de-duplicates"),
    dict(problem="(checked) late / out-of-order pings", direction="none today", km_impact=round(late_effect, 3),
         pct_of_true=0.0, worst_driver_day_km=None, note=f"{late} late pings, v0 sorts by timestamp"),
]
out = pd.DataFrame(rows)
(REPO / "evidence").mkdir(exist_ok=True)
out.to_csv(REPO / "evidence" / "problem_ranking.csv", index=False)
pd.set_option("display.width", 200)
print(f"Noise-free km counted by v0 logic: {total_clean:.3f}")
print(out.to_string(index=False))
