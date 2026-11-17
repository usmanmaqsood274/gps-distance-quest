"""Before (v0) vs after (v1) km per driver per day, checked against the frozen acceptance numbers.

Run: python analysis/before_after.py   -> evidence/before_after.csv, evidence/before_after_by_driver.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance import calc_v0, calc_v1  # noqa: E402
from distance.data_io import REPO, load_geo, load_pings  # noqa: E402

geo = load_geo()
pings = load_pings()
frozen = pd.read_csv(REPO / "evidence" / "acceptance_expected.csv")

before = calc_v0.daily_km(pings, geo).rename(columns={"km": "km_before"})
after = calc_v1.daily_km(pings, geo).rename(columns={"km": "km_after"})
t = (before.merge(after, on=["driver_id", "report_day"], how="outer")
           .merge(frozen[["driver_id", "report_day", "km_expected"]], on=["driver_id", "report_day"], how="outer")
           .fillna(0.0).sort_values(["driver_id", "report_day"]).reset_index(drop=True))
t["change_km"] = (t["km_after"] - t["km_before"]).round(3)
t["change_pct"] = (100 * t["change_km"] / t["km_before"]).round(1)
t["after_minus_expected"] = (t["km_after"] - t["km_expected"]).round(3)
t["meets_A3"] = t["after_minus_expected"].abs() <= 0.001

by_driver = t.groupby("driver_id")[["km_before", "km_after", "km_expected"]].sum().round(3)
by_driver["change_pct"] = (100 * (by_driver.km_after - by_driver.km_before) / by_driver.km_before).round(1)
by_driver.loc["TOTAL"] = [t.km_before.sum().round(3), t.km_after.sum().round(3), t.km_expected.sum().round(3),
                          round(100 * (t.km_after.sum() - t.km_before.sum()) / t.km_before.sum(), 1)]

(REPO / "evidence").mkdir(exist_ok=True)
t.to_csv(REPO / "evidence" / "before_after.csv", index=False)
by_driver.to_csv(REPO / "evidence" / "before_after_by_driver.csv")
pd.set_option("display.width", 200)
print(t.to_string(index=False))
print()
print(by_driver.to_string())
print(f"\nA3: {int(t.meets_A3.sum())}/{len(t)} driver-days within 0.001 km of the frozen expected value")
sys.exit(0 if t.meets_A3.all() else 1)
