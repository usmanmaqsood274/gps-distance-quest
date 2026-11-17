"""The distance rules from the brief, as constants and one function.

This module is the gap that no library filled: the GPS-noise rule itself.
Geometry comes from distance/geo.py, time zones from Python's zoneinfo.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .geo import haversine_m

OFF_ROAD_MAX_M = 100.0      # a ping more than 100 m from the road path is noise
SPEED_MAX_KMH = 150.0       # a ping implying more than 150 km/h is noise
LOCAL_TZ = ZoneInfo("Asia/Seoul")  # UTC+9, no daylight saving


def classify_noise(pings: pd.DataFrame, geo) -> pd.DataFrame:
    """Flag GPS-noise pings.

    Input must be one row per (driver, timestamp), sorted by driver then timestamp.
    Returns the same rows with columns:
      off_road_m      distance to the nearest road
      implied_kmh     speed from the last ACCEPTED ping of the same driver
      noise_reason    "" | "off_road" | "speed" | "off_road+speed"
      is_noise        bool

    Speed is measured from the last accepted ping, not the previous raw ping:
    otherwise the good ping right after a noise spike would also look too fast
    and be thrown away (the driver would lose real distance).
    """
    p = pings.reset_index(drop=True).copy()
    p["off_road_m"] = geo.roads.distance_m(p["lat"].values, p["lon"].values)
    implied = np.full(len(p), np.nan)
    reason = [""] * len(p)
    last = {}  # driver -> (ts, lat, lon) of last accepted ping
    ts = p["ts_utc"].values.astype("datetime64[ms]").astype("int64") / 1000.0
    for i, (drv, lat, lon, off) in enumerate(zip(p["driver_id"], p["lat"], p["lon"], p["off_road_m"])):
        r = []
        if off > OFF_ROAD_MAX_M:
            r.append("off_road")
        if drv in last:
            t0, lat0, lon0 = last[drv]
            dt = ts[i] - t0
            if dt > 0:
                implied[i] = float(haversine_m(lat0, lon0, lat, lon)) / dt * 3.6
                if implied[i] > SPEED_MAX_KMH:
                    r.append("speed")
        reason[i] = "+".join(r)
        if not r:
            last[drv] = (ts[i], lat, lon)
    p["implied_kmh"] = implied
    p["noise_reason"] = reason
    p["is_noise"] = p["noise_reason"] != ""
    return p
