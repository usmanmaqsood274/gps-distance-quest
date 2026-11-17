"""Small geometry helpers (the only hand-written geometry in the repo).

Why hand-written: shapely / pyproj were not installable in the offline build
environment. Everything here is city-scale (< 10 km), where a local
equirectangular projection is accurate to well under 0.1 %. If shapely and
pyproj are available, each function maps 1:1 onto a library call:

    haversine_m            -> pyproj.Geod(ellps="WGS84").inv(...)
    distance_to_roads_m    -> shapely  MultiLineString.distance(Point)  (projected)
    in_polygon             -> shapely  Polygon.contains(Point)          (projected)
"""
from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_M = 6_371_008.8  # IUGG mean Earth radius


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Works on scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


class LocalProjection:
    """Equirectangular projection around an origin: (lat, lon) -> metres (x east, y north)."""

    M_PER_DEG_LAT = 111_320.0

    def __init__(self, lat0: float, lon0: float):
        self.lat0 = lat0
        self.lon0 = lon0
        self.m_per_deg_lon = self.M_PER_DEG_LAT * math.cos(math.radians(lat0))

    def to_xy(self, lat, lon):
        x = (np.asarray(lon) - self.lon0) * self.m_per_deg_lon
        y = (np.asarray(lat) - self.lat0) * self.M_PER_DEG_LAT
        return x, y

    def to_latlon(self, x, y):
        lat = self.lat0 + np.asarray(y) / self.M_PER_DEG_LAT
        lon = self.lon0 + np.asarray(x) / self.m_per_deg_lon
        return lat, lon


def _segments_xy(polylines_latlon, proj: LocalProjection) -> np.ndarray:
    """All road polylines -> array of segments [[ax, ay, bx, by], ...] in metres."""
    segs = []
    for line in polylines_latlon:
        lat = np.array([p[0] for p in line])
        lon = np.array([p[1] for p in line])
        x, y = proj.to_xy(lat, lon)
        for i in range(len(x) - 1):
            segs.append((x[i], y[i], x[i + 1], y[i + 1]))
    return np.array(segs, dtype=float)


class RoadNetwork:
    def __init__(self, polylines_latlon, proj: LocalProjection):
        self.proj = proj
        self.segs = _segments_xy(polylines_latlon, proj)

    def distance_m(self, lat, lon):
        """Distance from each point to the nearest road segment, in metres."""
        px, py = self.proj.to_xy(np.atleast_1d(lat), np.atleast_1d(lon))
        px = px[:, None]
        py = py[:, None]
        ax, ay, bx, by = (self.segs[:, i][None, :] for i in range(4))
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        t = np.where(seg_len2 > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(seg_len2 > 0, seg_len2, 1), 0)
        t = np.clip(t, 0.0, 1.0)
        cx, cy = ax + t * dx, ay + t * dy
        d = np.hypot(px - cx, py - cy)
        return d.min(axis=1)


class Zone:
    def __init__(self, ring_latlon, proj: LocalProjection):
        self.proj = proj
        lat = np.array([p[0] for p in ring_latlon])
        lon = np.array([p[1] for p in ring_latlon])
        self.x, self.y = proj.to_xy(lat, lon)

    def contains(self, lat, lon):
        """Ray-casting point-in-polygon. Points exactly on an edge are not guaranteed either way."""
        px, py = self.proj.to_xy(np.atleast_1d(lat), np.atleast_1d(lon))
        inside = np.zeros(px.shape, dtype=bool)
        n = len(self.x)
        j = n - 1
        for i in range(n):
            xi, yi, xj, yj = self.x[i], self.y[i], self.x[j], self.y[j]
            crosses = (yi > py) != (yj > py)
            with np.errstate(divide="ignore", invalid="ignore"):
                x_at = (xj - xi) * (py - yi) / (yj - yi) + xi
            inside ^= crosses & (px < x_at)
            j = i
        return inside
