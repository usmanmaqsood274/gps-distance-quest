"""FIXED calculation (v1): v0 plus the GPS-noise rule. Nothing else changed.

Root cause of P1: v0 builds segments from every de-duplicated ping, so a ping
thrown 100s of metres off the road (or teleported along it) adds two long legs
- out to the bad point and back - to the billed distance.

The fix: before building segments, drop every ping that the brief defines as
noise (distance/rules.py::classify_noise):
  * more than 100 m from the road path, or
  * implying more than 150 km/h from the driver's last ACCEPTED ping.
The two good pings either side of a removed ping are then joined directly.

Deliberately NOT changed here (separate tickets, see evidence.md):
  * day cut is still the UTC date (P2)
  * zone test still uses the segment's start ping (P3)
"""
from __future__ import annotations

import pandas as pd

from .calc_v0 import build_segments, sort_and_dedupe
from .rules import classify_noise


def accepted_pings(pings: pd.DataFrame, geo) -> pd.DataFrame:
    p = classify_noise(sort_and_dedupe(pings), geo)
    return p[~p["is_noise"]]


def counted_segments(pings: pd.DataFrame, geo) -> pd.DataFrame:
    seg = build_segments(accepted_pings(pings, geo))
    seg["in_zone"] = geo.zone.contains(seg["lat1"].values, seg["lon1"].values)
    seg = seg[seg["in_zone"]].copy()
    seg["report_day"] = seg["start_ts_utc"].dt.strftime("%Y-%m-%d")  # unchanged from v0 (P2 out of scope)
    return seg


def daily_km(pings: pd.DataFrame, geo) -> pd.DataFrame:
    seg = counted_segments(pings, geo)
    out = seg.groupby(["driver_id", "report_day"], as_index=False)["m"].sum()
    out["km"] = (out.pop("m") / 1000).round(3)
    return out
