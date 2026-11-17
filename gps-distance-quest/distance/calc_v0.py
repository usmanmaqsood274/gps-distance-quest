"""ORIGINAL reference calculation (v0) - kept unchanged as the "before".

This is the calculation the advertiser and driver reports were built on. It was
AI-generated from a one-line prompt ("sum the GPS distance per driver per day
inside the zone") and it is wrong in ways documented in intent.md.

What v0 does:
  1. sorts pings by (driver, timestamp) and drops exact (driver, timestamp) duplicates
  2. joins consecutive pings into segments, breaking at gaps > 120 s
  3. counts a segment if its START ping is inside the zone
  4. assigns the segment to the UTC calendar date of its start ping
  5. sums haversine length -> km per driver per day

What v0 does NOT do: it never applies the GPS-noise rule (>100 m off road, or
>150 km/h implied speed), so every noise ping adds a detour to the distance.
"""
from __future__ import annotations

import pandas as pd

from .geo import haversine_m

MAX_GAP_S = 120


def build_segments(pings: pd.DataFrame) -> pd.DataFrame:
    """Consecutive ping pairs per driver (input must be sorted and de-duplicated)."""
    p = pings.reset_index(drop=True)
    nxt = p.shift(-1)
    same = (p["driver_id"] == nxt["driver_id"]) & (
        (nxt["ts_utc"] - p["ts_utc"]).dt.total_seconds() <= MAX_GAP_S
    )
    seg = pd.DataFrame({
        "driver_id": p["driver_id"],
        "start_ts_utc": p["ts_utc"],
        "end_ts_utc": nxt["ts_utc"],
        "start_ping": p["ping_id"],
        "end_ping": nxt["ping_id"],
        "lat1": p["lat"], "lon1": p["lon"], "lat2": nxt["lat"], "lon2": nxt["lon"],
    })[same.fillna(False).astype(bool)]
    seg["m"] = haversine_m(seg["lat1"], seg["lon1"], seg["lat2"], seg["lon2"])
    return seg.reset_index(drop=True)


def sort_and_dedupe(pings: pd.DataFrame) -> pd.DataFrame:
    return (pings.sort_values(["driver_id", "ts_utc", "received_at_utc"], kind="stable")
                 .drop_duplicates(["driver_id", "ts_utc"], keep="first"))


def counted_segments_v0(pings: pd.DataFrame, geo) -> pd.DataFrame:
    seg = build_segments(sort_and_dedupe(pings))
    seg["in_zone"] = geo.zone.contains(seg["lat1"].values, seg["lon1"].values)
    seg = seg[seg["in_zone"]].copy()
    seg["report_day"] = seg["start_ts_utc"].dt.strftime("%Y-%m-%d")  # UTC date
    return seg


def daily_km(pings: pd.DataFrame, geo) -> pd.DataFrame:
    seg = counted_segments_v0(pings, geo)
    out = seg.groupby(["driver_id", "report_day"], as_index=False)["m"].sum()
    out["km"] = (out.pop("m") / 1000).round(3)
    return out
counted_segments = counted_segments_v0  # common interface for the QA tool
