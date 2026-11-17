"""Regression check for problem P1: GPS noise counted as distance.

Run against the fixed calculation (default):   pytest
Run against the original calculation:           pytest --impl=v0   (must FAIL)

Part A uses the full synthetic dataset and the acceptance numbers frozen in
evidence/acceptance_expected.csv before the fix was written.
Part B uses tiny hand-built tracks for the edge cases that matter.
"""
from __future__ import annotations

import random

import pandas as pd
import pytest

from analysis.acceptance_expected import expected_table
from distance.data_io import REPO, load_geo, load_pings

GEO = load_geo()
FROZEN = pd.read_csv(REPO / "evidence" / "acceptance_expected.csv")


@pytest.fixture(scope="module")
def labelled():
    return load_pings(with_labels=True)


@pytest.fixture(scope="module")
def pings(labelled):
    return labelled[["ping_id", "driver_id", "ts_utc", "lat", "lon", "received_at_utc"]]


# ---------------------------------------------------------------- Part A: dataset

def test_frozen_acceptance_numbers_still_match_dataset():
    """Guard: the expected numbers were frozen before the fix; the dataset must not drift."""
    now = expected_table()
    pd.testing.assert_frame_equal(now[FROZEN.columns].reset_index(drop=True), FROZEN, check_exact=False, atol=1e-6)


def test_A3_km_per_driver_per_day_matches_acceptance(impl, pings):
    got = impl.daily_km(pings, GEO)
    m = FROZEN.merge(got, on=["driver_id", "report_day"], how="outer")
    m["km"] = m["km"].fillna(0.0)
    m["diff"] = (m["km"] - m["km_expected"]).abs()
    bad = m[m["diff"] > 0.001]
    assert len(m) == 17
    assert bad.empty, "driver-days off by > 1 m:\n" + bad[["driver_id", "report_day", "km", "km_expected", "diff"]].to_string()


def test_A4_campaign_total(impl, pings):
    assert impl.daily_km(pings, GEO)["km"].sum() == pytest.approx(181.611, abs=0.005)


def test_A1_A2_no_noise_billed_and_no_clean_ping_dropped(impl, labelled, pings):
    noise_ids = set(labelled.loc[labelled.synthetic_fault.str.startswith("noise"), "ping_id"])
    seg = impl.counted_segments(pings, GEO)
    touched = (set(seg.start_ping) | set(seg.end_ping)) & noise_ids
    assert not touched, f"{len(touched)} labelled noise pings still billed, e.g. {sorted(touched)[:5]}"
    # every segment the expected (noise-free) calculation counts is still counted -> no clean ping lost
    from distance import calc_v0
    expected_pairs = set(zip(*calc_v0.counted_segments(pings[~pings.ping_id.isin(noise_ids)], GEO)[["start_ping", "end_ping"]].values.T))
    got_pairs = set(zip(*seg[["start_ping", "end_ping"]].values.T))
    assert expected_pairs == got_pairs


def test_A5_duplicates_counted_once(impl, labelled, pings):
    no_dups = pings[(labelled.synthetic_fault != "duplicate").values]
    a = impl.daily_km(pings, GEO).set_index(["driver_id", "report_day"])["km"]
    b = impl.daily_km(no_dups, GEO).set_index(["driver_id", "report_day"])["km"]
    pd.testing.assert_series_equal(a, b)


def test_A6_late_pings_placed_by_own_timestamp(impl, pings):
    shuffled = pings.sample(frac=1.0, random_state=7)
    a = impl.daily_km(pings, GEO).set_index(["driver_id", "report_day"])["km"]
    b = impl.daily_km(shuffled, GEO).set_index(["driver_id", "report_day"])["km"]
    pd.testing.assert_series_equal(a, b)


# ------------------------------------------------------------ Part B: edge cases
# Tracks run east along the y = 1000 m road, inside the zone, one ping every 10 s.

T0 = pd.Timestamp("2026-11-03T03:00:00Z")  # 12:00 local, mid-day: no day-cut effects


def track(points, dup_index=None):
    lat, lon = GEO.proj.to_latlon([p[0] for p in points], [p[1] for p in points])
    rows = [dict(ping_id=f"T{i:03d}", driver_id="DX", ts_utc=T0 + pd.Timedelta(seconds=10 * i),
                 lat=float(lat[i]), lon=float(lon[i]),
                 received_at_utc=T0 + pd.Timedelta(seconds=10 * i + 2)) for i in range(len(points))]
    if dup_index is not None:
        d = dict(rows[dup_index]); d["ping_id"] = "TDUP"; d["received_at_utc"] += pd.Timedelta(seconds=30)
        rows.append(d)
    random.Random(1).shuffle(rows)  # arrival order must not matter
    return pd.DataFrame(rows)


def km(impl, df):
    return impl.daily_km(df, GEO)["km"].sum()


STRAIGHT = [(1000 + 100 * i, 1000) for i in range(6)]  # 0.5 km at 36 km/h


@pytest.mark.parametrize("offset_m, counted", [(99, True), (101, False), (300, False)])
def test_off_road_threshold(impl, offset_m, counted):
    pts = list(STRAIGHT)
    pts[3] = (1300, 1000 + offset_m)
    if counted:
        import math
        expected = 0.2 + 2 * math.hypot(100, offset_m) / 1000 + 0.1  # the 99 m ping is legitimate
    else:
        expected = 0.5  # chord 1200 -> 1400 replaces the detour
    assert km(impl, track(pts)) == pytest.approx(expected, abs=0.002)


def test_speed_spike_on_road_is_dropped(impl):
    pts = list(STRAIGHT)
    pts[3] = (1000, 1700)  # on the x = 1000 road, 728 m away in 10 s = 262 km/h
    assert km(impl, track(pts)) == pytest.approx(0.5, abs=0.002)


def test_ping_after_spike_is_kept(impl):
    """Speed must be measured from the last GOOD ping, otherwise the driver loses real distance."""
    pts = list(STRAIGHT)
    pts[2] = (1000, 1700)  # spike; next real ping (1300,1000) is 762 m from the spike but 200 m from last good
    seg = impl.counted_segments(track(pts), GEO)
    assert "T003" in set(seg.start_ping) | set(seg.end_ping)
    assert km(impl, track(pts)) == pytest.approx(0.5, abs=0.002)


def test_fast_but_legal_movement_is_kept(impl):
    pts = [(1000 + 388.9 * i, 1000) for i in range(4)]  # 140 km/h
    assert km(impl, track(pts)) == pytest.approx(1.1667, abs=0.002)


def test_duplicate_of_noise_ping_not_counted(impl):
    pts = list(STRAIGHT)
    pts[3] = (1300, 1300)
    assert km(impl, track(pts, dup_index=3)) == pytest.approx(0.5, abs=0.002)


@pytest.mark.xfail(reason="KNOWN LIMITATION: if the FIRST ping of a session is an on-road teleport, "
                          "later real pings look too fast and are dropped. Not solved - see evidence.md.",
                   strict=False)
def test_known_limitation_first_ping_is_teleport(impl):
    pts = [(2000, 2000)] + [(1000 + 100 * i, 1000) for i in range(1, 6)]
    assert km(impl, track(pts)) == pytest.approx(0.4, abs=0.002)
