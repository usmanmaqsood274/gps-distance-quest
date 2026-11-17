"""Generate the SYNTHETIC GPS ping dataset used in this Quest.

*** SYNTHETIC DATA. No real person, vehicle, road or trip. ***
The road grid and the campaign zone are placed in open sea in the Korea Strait
(around 34.0 N, 128.5 E) so that no coordinate can be mistaken for a real
location. The time zone matches the brief: reports cut at 00:00 UTC+9.

Run:  python data/generate_dataset.py      (deterministic, seed 20261117)

Outputs (in data/):
  pings_SYNTHETIC.csv   one row per received ping, in arrival order
  roads_SYNTHETIC.json  road centre-lines (a 1 km grid)
  zone_SYNTHETIC.json   the campaign zone polygon

Ground-truth columns (prefixed synthetic_) are for tests and the QA tool's
label check only:
  synthetic_fault   clean | noise_offroad | noise_speed | duplicate | late
  synthetic_true_lat / synthetic_true_lon   where the car really was
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance.geo import LocalProjection, RoadNetwork  # noqa: E402

SEED = 20261117
OUT = Path(__file__).resolve().parent
ORIGIN = (34.00, 128.50)  # open sea, Korea Strait - deliberately not a real road
KST = timezone(timedelta(hours=9))

GRID_X = [0, 1000, 2000, 3000, 4000]  # north-south roads at these x (metres)
GRID_Y = [0, 1000, 2000, 3000]        # east-west roads at these y (metres)
ZONE_XY = [(500, 500), (3500, 500), (3500, 2000), (2500, 2700), (500, 2700)]

PING_EVERY_S = 10
JITTER_SIGMA_M = 5.0
JITTER_CLIP_M = 15.0

# Shifts in LOCAL time (UTC+9). Chosen so that some cross 09:00 local
# (= 00:00 UTC) and some cross 00:00 local, which is where day cuts matter.
SHIFTS = {
    "D01": ("08:35", 50),
    "D02": ("23:35", 45),
    "D03": ("13:10", 55),
    "D04": ("08:45", 40),
    "D05": ("18:20", 50),
}
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04"]

NOISE_RATE = 0.03      # share of pings replaced by GPS noise
NOISE_OFFROAD_SHARE = 0.6
DUP_RATE = 0.02
LATE_RATE = 0.02


def build_geometry(proj: LocalProjection):
    polylines = []
    for x in GRID_X:
        lat, lon = proj.to_latlon([x, x], [GRID_Y[0], GRID_Y[-1]])
        polylines.append([[float(lat[0]), float(lon[0])], [float(lat[1]), float(lon[1])]])
    for y in GRID_Y:
        lat, lon = proj.to_latlon([GRID_X[0], GRID_X[-1]], [y, y])
        polylines.append([[float(lat[0]), float(lon[0])], [float(lat[1]), float(lon[1])]])
    zx = [p[0] for p in ZONE_XY] + [ZONE_XY[0][0]]
    zy = [p[1] for p in ZONE_XY] + [ZONE_XY[0][1]]
    zlat, zlon = proj.to_latlon(zx, zy)
    ring = [[float(a), float(b)] for a, b in zip(zlat, zlon)]
    return polylines, ring


def _next_line(pos: float, direction: int, lines: list[int]) -> float | None:
    """Next grid line strictly ahead of pos in the given direction, or None."""
    ahead = [g for g in lines if (g - pos) * direction > 1e-9]
    return min(ahead, key=lambda g: abs(g - pos)) if ahead else None


def drive(rng: np.random.Generator, seconds: int):
    """Simulate one shift on the road grid at 1 s resolution. Returns true (x, y) every 10 s."""
    x = float(rng.choice(GRID_X[1:-1]))
    y = float(rng.choice(GRID_Y[1:-1]))
    heading = [(1, 0), (-1, 0), (0, 1), (0, -1)][rng.integers(4)]
    speed = rng.uniform(25, 55) / 3.6  # m/s, max 55 km/h
    stop_left = 0
    pts = []
    for t in range(seconds + 1):
        if t % PING_EVERY_S == 0:
            pts.append((x, y))
        if stop_left > 0:
            stop_left -= 1
            continue
        if heading[0] != 0:
            nxt = _next_line(x, heading[0], GRID_X)
            gap = abs(nxt - x) if nxt is not None else 0.0
        else:
            nxt = _next_line(y, heading[1], GRID_Y)
            gap = abs(nxt - y) if nxt is not None else 0.0
        if nxt is not None and speed < gap:
            x += heading[0] * speed
            y += heading[1] * speed
            continue
        # reach the intersection this second (shorter step), then pick a new heading
        if nxt is not None:
            if heading[0] != 0:
                x = float(nxt)
            else:
                y = float(nxt)
        options = [h for h in [(1, 0), (-1, 0), (0, 1), (0, -1)]
                   if h != (-heading[0], -heading[1])
                   and GRID_X[0] <= x + h[0] <= GRID_X[-1] and GRID_Y[0] <= y + h[1] <= GRID_Y[-1]]
        if not options:
            options = [(-heading[0], -heading[1])]
        heading = options[rng.integers(len(options))]
        speed = rng.uniform(25, 55) / 3.6
        if rng.random() < 0.25:
            stop_left = int(rng.integers(20, 90))  # traffic light
    return pts


def main():
    rng = np.random.default_rng(SEED)
    proj = LocalProjection(*ORIGIN)
    polylines, ring = build_geometry(proj)
    roads = RoadNetwork(polylines, proj)

    rows = []
    for day in DAYS:
        for driver, (hhmm, minutes) in SHIFTS.items():
            start_local = datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=KST)
            start_utc = start_local.astimezone(timezone.utc)
            true_pts = drive(rng, minutes * 60)
            n = len(true_pts)
            fault = ["clean"] * n

            # choose noise positions: never in the first 3 pings, never adjacent to another noise ping
            n_noise = int(round(NOISE_RATE * n))
            chosen: set[int] = set()
            while len(chosen) < n_noise:
                i = int(rng.integers(3, n - 1))
                if {i - 1, i, i + 1} & chosen:
                    continue
                chosen.add(i)
            for i in sorted(chosen):
                fault[i] = "noise_offroad" if rng.random() < NOISE_OFFROAD_SHARE else "noise_speed"

            for i, (tx, ty) in enumerate(true_pts):
                ts = start_utc + timedelta(seconds=PING_EVERY_S * i)
                if fault[i] == "noise_offroad":
                    # thrown 150-600 m in a random direction and at least 110 m from any road
                    while True:
                        r = rng.uniform(150, 600)
                        a = rng.uniform(0, 2 * np.pi)
                        ox, oy = tx + r * np.cos(a), ty + r * np.sin(a)
                        olat, olon = proj.to_latlon(ox, oy)
                        if roads.distance_m(olat, olon)[0] > 110:
                            break
                elif fault[i] == "noise_speed":
                    # jumps ON a road 450-1200 m from where the car is (162-432 km/h implied over 10 s)
                    while True:
                        if rng.random() < 0.5:
                            ox, oy = float(rng.choice(GRID_X)), rng.uniform(GRID_Y[0], GRID_Y[-1])
                        else:
                            ox, oy = rng.uniform(GRID_X[0], GRID_X[-1]), float(rng.choice(GRID_Y))
                        px, py = true_pts[i - 1]
                        nx_, ny_ = true_pts[i + 1]
                        dp, dn = np.hypot(ox - px, oy - py), np.hypot(ox - nx_, oy - ny_)
                        if 450 <= dp <= 1200 and dn >= 450:
                            break
                else:
                    j = np.clip(rng.normal(0, JITTER_SIGMA_M, 2), -JITTER_CLIP_M, JITTER_CLIP_M)
                    ox, oy = tx + j[0], ty + j[1]
                lat, lon = proj.to_latlon(ox, oy)
                tlat, tlon = proj.to_latlon(tx, ty)
                received = ts + timedelta(seconds=float(rng.uniform(1, 3)))
                f = fault[i]
                if f == "clean" and rng.random() < LATE_RATE:
                    received = ts + timedelta(seconds=float(rng.uniform(60, 600)))
                    f = "late"
                rows.append(dict(driver_id=driver, ts_utc=ts, lat=float(lat), lon=float(lon),
                                 received_at_utc=received, synthetic_fault=f,
                                 synthetic_true_lat=float(tlat), synthetic_true_lon=float(tlon)))
                if f in ("clean", "late") and rng.random() < DUP_RATE:
                    dup = dict(rows[-1])
                    dup["received_at_utc"] = received + timedelta(seconds=float(rng.uniform(5, 120)))
                    dup["synthetic_fault"] = "duplicate"
                    rows.append(dup)

    df = pd.DataFrame(rows).sort_values("received_at_utc", kind="stable").reset_index(drop=True)
    df.insert(0, "ping_id", [f"P{i:05d}" for i in range(len(df))])
    df.insert(1, "dataset", "SYNTHETIC")
    df["ts_utc"] = df["ts_utc"].map(lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ"))
    df["received_at_utc"] = df["received_at_utc"].map(lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
    for c in ("lat", "lon", "synthetic_true_lat", "synthetic_true_lon"):
        df[c] = df[c].round(7)
    df.to_csv(OUT / "pings_SYNTHETIC.csv", index=False)

    meta = {"_label": "SYNTHETIC - generated by data/generate_dataset.py, not a real place",
            "projection_origin": list(ORIGIN)}
    (OUT / "roads_SYNTHETIC.json").write_text(json.dumps({**meta, "polylines": polylines}, indent=1))
    (OUT / "zone_SYNTHETIC.json").write_text(json.dumps({**meta, "ring": ring}, indent=1))

    print(f"wrote {len(df)} pings")
    print(df["synthetic_fault"].value_counts().to_string())


if __name__ == "__main__":
    main()
