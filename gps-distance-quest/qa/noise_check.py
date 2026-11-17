"""QA tool: GPS-noise checker for the km-per-driver-per-day calculation.

Answers one question for any calculation and any ping file:
    "How many kilometres in this report come from GPS noise, and from which pings?"

It does NOT need ground-truth labels. It applies the noise rule from the brief
(> 100 m from the road, or > 150 km/h implied from the last good ping) and then
asks the calculation under test which segments it counted. Any counted segment
that touches a noise ping is billed noise.

Usage:
    python -m qa.noise_check --calc v0          # the original calculation
    python -m qa.noise_check --calc v1          # the fixed calculation
    python -m qa.noise_check --calc v0 --pings path/to/pings.csv

Outputs (in out/):
    noise_pings_<calc>.csv        every noise ping: where, why, km it put into the report
    noise_by_driver_day_<calc>.csv  reported km vs km without noise, per driver per day

Exit code: 0 if the calculation counts no noise km, 1 if it does (CI-friendly).
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance.calc_v0 import sort_and_dedupe  # noqa: E402
from distance.data_io import DATA, PING_COLUMNS, REPO, load_geo, load_pings  # noqa: E402
from distance.rules import LOCAL_TZ, OFF_ROAD_MAX_M, SPEED_MAX_KMH, classify_noise  # noqa: E402

TOLERANCE_KM = 0.0005


def run(calc_name: str, pings_path: Path, out_dir: Path, quiet: bool = False) -> int:
    calc = importlib.import_module(f"distance.calc_{calc_name}")
    geo = load_geo()
    raw = load_pings(pings_path, with_labels=True)
    has_labels = "synthetic_fault" in raw.columns
    pings = raw[PING_COLUMNS]

    # 1. Apply the rule independently of the calculation under test
    flagged = classify_noise(sort_and_dedupe(pings), geo)
    noise = flagged[flagged["is_noise"]].copy()
    noise_ids = set(noise["ping_id"])

    # 2. Ask the calculation which segments it billed
    seg = calc.counted_segments(pings, geo)
    seg["touches_noise"] = seg["start_ping"].isin(noise_ids) | seg["end_ping"].isin(noise_ids)

    # 3. Per driver-day: km reported vs the same calculation without the noise pings
    reported = calc.daily_km(pings, geo).rename(columns={"km": "km_reported"})
    without = calc.daily_km(pings[~pings["ping_id"].isin(noise_ids)], geo).rename(columns={"km": "km_without_noise"})
    by_day = reported.merge(without, on=["driver_id", "report_day"], how="outer").fillna(0.0)
    by_day["noise_km"] = (by_day["km_reported"] - by_day["km_without_noise"]).round(3)
    by_day["noise_pct"] = (100 * by_day["noise_km"] / by_day["km_without_noise"].where(by_day["km_without_noise"] > 0)).round(1)
    t = seg[seg["touches_noise"]]
    billed_pairs = pd.concat([t[["driver_id", "report_day", "start_ping"]].set_axis(["driver_id", "report_day", "p"], axis=1),
                              t[["driver_id", "report_day", "end_ping"]].set_axis(["driver_id", "report_day", "p"], axis=1)])
    n_noise = (billed_pairs[billed_pairs["p"].isin(noise_ids)].drop_duplicates()
               .groupby(["driver_id", "report_day"]).size().rename("noise_pings_billed").reset_index())
    by_day = by_day.merge(n_noise, on=["driver_id", "report_day"], how="left")
    by_day["noise_pings_billed"] = by_day["noise_pings_billed"].fillna(0).astype(int)
    by_day = by_day.sort_values(["driver_id", "report_day"]).reset_index(drop=True)

    # 4. Per noise ping: where, why, and how much distance it put into the report
    billed_m = pd.concat([
        seg[seg["start_ping"].isin(noise_ids)].groupby("start_ping")["m"].sum(),
        seg[seg["end_ping"].isin(noise_ids)].groupby("end_ping")["m"].sum(),
    ]).groupby(level=0).sum()
    noise["billed_segments_m"] = noise["ping_id"].map(billed_m).fillna(0.0).round(1)
    noise["local_time"] = noise["ts_utc"].dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d %H:%M:%S")
    noise["why"] = noise.apply(_explain, axis=1)
    cols = ["ping_id", "driver_id", "ts_utc", "local_time", "lat", "lon", "off_road_m", "implied_kmh",
            "noise_reason", "billed_segments_m", "why"]
    if has_labels:
        noise = noise.merge(raw[["ping_id", "synthetic_fault"]], on="ping_id", how="left")
        cols.append("synthetic_fault")
    noise = noise[cols].round({"off_road_m": 1, "implied_kmh": 1})

    out_dir.mkdir(parents=True, exist_ok=True)
    noise.to_csv(out_dir / f"noise_pings_{calc_name}.csv", index=False)
    by_day.to_csv(out_dir / f"noise_by_driver_day_{calc_name}.csv", index=False)

    total_noise_km = by_day["noise_km"].sum()
    billed = noise[noise["billed_segments_m"] > 0]
    if not quiet:
        pd.set_option("display.width", 220)
        pd.set_option("display.max_colwidth", 80)
        print(f"\n=== GPS noise check: calculation {calc_name} on {pings_path.name} ===")
        print(f"Rule: noise = > {OFF_ROAD_MAX_M:.0f} m from road OR > {SPEED_MAX_KMH:.0f} km/h from last good ping")
        print(f"Pings: {len(pings)} rows, {len(flagged)} after de-duplication; "
              f"noise pings found: {len(noise)} "
              f"({(noise.noise_reason.str.contains('off_road')).sum()} off-road, "
              f"{(noise.noise_reason == 'speed').sum()} speed-only)")
        print(f"Noise pings the calculation BILLED: {len(billed)}")
        print("\nPer driver per report day:")
        print(by_day.to_string(index=False))
        print(f"\nTOTAL reported {by_day.km_reported.sum():.3f} km | without noise "
              f"{by_day.km_without_noise.sum():.3f} km | noise billed {total_noise_km:.3f} km")
        if len(billed):
            print("\nWorst 5 noise pings by billed distance:")
            print(billed.sort_values("billed_segments_m", ascending=False).head(5)[
                ["ping_id", "driver_id", "local_time", "billed_segments_m", "why"]].to_string(index=False))
        if has_labels:
            lab = raw.set_index("ping_id")["synthetic_fault"]
            labelled = set(lab[lab.str.startswith("noise")].index)
            found = noise_ids
            print(f"\nLabel check (synthetic ground truth): caught {len(found & labelled)}/{len(labelled)} "
                  f"labelled noise pings; flagged {len(found - labelled)} clean pings as noise")
        print(f"\nReport written to {out_dir}/noise_pings_{calc_name}.csv and noise_by_driver_day_{calc_name}.csv")
        print("RESULT:", "FAIL - report contains GPS-noise distance" if total_noise_km > TOLERANCE_KM
              else "PASS - no GPS-noise distance in the report")
    return 1 if total_noise_km > TOLERANCE_KM else 0


def _explain(r) -> str:
    parts = []
    if "off_road" in r["noise_reason"]:
        parts.append(f"{r['off_road_m']:.0f} m from the road (limit {OFF_ROAD_MAX_M:.0f} m)")
    if "speed" in r["noise_reason"]:
        parts.append(f"implies {r['implied_kmh']:.0f} km/h from the last good ping (limit {SPEED_MAX_KMH:.0f})")
    return "; ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calc", default="v1", choices=["v0", "v1"], help="calculation to check")
    ap.add_argument("--pings", type=Path, default=DATA / "pings_SYNTHETIC.csv")
    ap.add_argument("--out", type=Path, default=REPO / "out")
    a = ap.parse_args(argv)
    return run(a.calc, a.pings, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
