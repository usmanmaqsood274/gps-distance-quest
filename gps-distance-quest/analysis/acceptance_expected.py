"""Freeze the acceptance test as numbers BEFORE the fix exists.

Expected km per driver per report day for the chosen problem (P1 GPS noise):
the v0 calculation run on the dataset with the generator's labelled noise pings
removed. Only the noise behaviour differs between "before" and "expected";
the day cut and zone behaviour are deliberately left as in v0 (out of scope,
see intent.md), so the comparison isolates exactly the problem being fixed.

Run: python analysis/acceptance_expected.py  -> evidence/acceptance_expected.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance import calc_v0  # noqa: E402
from distance.data_io import REPO, load_geo, load_pings  # noqa: E402


def expected_table():
    geo = load_geo()
    raw = load_pings(with_labels=True)
    is_noise = raw["synthetic_fault"].str.startswith("noise").values
    pings = raw.drop(columns=[c for c in raw.columns if c.startswith("synthetic_") or c == "dataset"])
    before = calc_v0.daily_km(pings, geo).rename(columns={"km": "km_before_v0"})
    expected = calc_v0.daily_km(pings[~is_noise], geo).rename(columns={"km": "km_expected"})
    t = before.merge(expected, on=["driver_id", "report_day"], how="outer").fillna(0.0)
    t["noise_km_in_before"] = (t["km_before_v0"] - t["km_expected"]).round(3)
    return t.sort_values(["driver_id", "report_day"]).reset_index(drop=True)


if __name__ == "__main__":
    t = expected_table()
    (REPO / "evidence").mkdir(exist_ok=True)
    t.to_csv(REPO / "evidence" / "acceptance_expected.csv", index=False)
    print(t.to_string(index=False))
    print(f"\nTOTAL before {t.km_before_v0.sum():.3f} km, expected {t.km_expected.sum():.3f} km")
