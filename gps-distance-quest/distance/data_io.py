"""Load the synthetic pings, road network and campaign zone."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .geo import LocalProjection, RoadNetwork, Zone

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

# Columns a production calculation is allowed to see. Anything starting with
# "synthetic_" is ground truth written by the generator and must never be used
# by a calculation (only by tests / the QA tool's optional label check).
PING_COLUMNS = ["ping_id", "driver_id", "ts_utc", "lat", "lon", "received_at_utc"]


@dataclass
class Geo:
    proj: LocalProjection
    roads: RoadNetwork
    zone: Zone


def load_geo(data_dir: Path = DATA) -> Geo:
    roads = json.loads((data_dir / "roads_SYNTHETIC.json").read_text())
    zone = json.loads((data_dir / "zone_SYNTHETIC.json").read_text())
    proj = LocalProjection(zone["projection_origin"][0], zone["projection_origin"][1])
    return Geo(proj=proj, roads=RoadNetwork(roads["polylines"], proj), zone=Zone(zone["ring"], proj))


def load_pings(path: Path = DATA / "pings_SYNTHETIC.csv", with_labels: bool = False) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df["received_at_utc"] = pd.to_datetime(df["received_at_utc"], utc=True)
    if not with_labels:
        df = df[PING_COLUMNS]
    return df
