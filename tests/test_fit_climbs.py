"""Climb detection, VAM, matcher, PB rules, essay prompt."""
from datetime import datetime, timedelta, timezone

import pytest

from ai_endurance_coach_over50.analysis.climb_essays import build_climb_essay_prompt
from ai_endurance_coach_over50.analysis.fit_climbs import (
    compute_climb_analysis,
    detect_climbs,
    est_wkg_from_vam,
    haversine_m,
    match_named_climb,
    vam_m_h,
)
from ai_endurance_coach_over50.analysis.fit_ingest import FitRecord, FitSession


def _ramp_records(
    *,
    n: int = 600,
    start_alt: float = 10.0,
    gain_per_m: float = 0.05,  # 5% grade
    power: float = 220.0,
    cadence: float = 75.0,
    start_lat: float = 51.8,
    start_lon: float = 0.9,
) -> list[FitRecord]:
    """~1 Hz climb: 600 m at 5% → +30 m gain."""
    t0 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    out: list[FitRecord] = []
    for i in range(n):
        dist = float(i)  # 1 m/s ≈ 3.6 km/h walking pace — fine for grade
        alt = start_alt + dist * gain_per_m
        # tiny lat drift north
        lat = start_lat + (dist / 111_000.0)
        out.append(FitRecord(
            timestamp=t0 + timedelta(seconds=i),
            power=power,
            hr=155,
            cadence=cadence,
            altitude=alt,
            distance=dist,
            speed=1.0,
            lat=lat,
            lon=start_lon,
        ))
    return out


def test_vam_and_est_wkg():
    assert vam_m_h(85, 8.2) == pytest.approx(621.95, rel=1e-3)
    # Ferrari: 1400 / (200 + 10*6) = 1400/260
    assert est_wkg_from_vam(1400, 6.0) == pytest.approx(5.38, abs=0.02)


def test_detect_ramp_climb():
    # 800 m at 5.5% → ~+44 m gain, well above thresholds
    recs = _ramp_records(n=800, gain_per_m=0.055, power=220)
    climbs = detect_climbs(recs, ftp_w=200, weight_kg=75.0)
    assert len(climbs) >= 1
    c = climbs[0]
    assert c["gain_m"] >= 30
    assert c["avg_grade"] >= 5.0
    assert c["vam_m_h"] is not None and c["vam_m_h"] > 0
    assert c["vam_confidence"] == "high"
    assert c["avg_power"] == pytest.approx(220, abs=2)
    assert c["wkg"] == pytest.approx(220 / 75, abs=0.05)
    assert c["est_wkg_from_vam"] is not None
    assert c["start_lat"] is not None
    assert c["fade_pct"] is not None  # even power → near 0


def test_flat_ride_no_climbs():
    t0 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    recs = [
        FitRecord(
            timestamp=t0 + timedelta(seconds=i),
            power=150, hr=130, cadence=80,
            altitude=10.0, distance=float(i), speed=8.0,
            lat=51.8, lon=0.9,
        )
        for i in range(500)
    ]
    assert detect_climbs(recs) == []


def test_fade_positive_when_second_half_weaker():
    t0 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    recs: list[FitRecord] = []
    for i in range(800):
        p = 240.0 if i < 400 else 200.0
        dist = float(i)
        alt = 10.0 + dist * 0.05
        recs.append(FitRecord(
            timestamp=t0 + timedelta(seconds=i),
            power=p, hr=160, cadence=72,
            altitude=alt, distance=dist, speed=1.0,
            lat=51.8 + dist / 111_000, lon=0.9,
        ))
    climbs = detect_climbs(recs)
    assert climbs
    assert climbs[0]["fade_pct"] is not None
    assert climbs[0]["fade_pct"] > 5


def test_grade_bins_populated():
    recs = _ramp_records(n=800, gain_per_m=0.06)
    result = compute_climb_analysis(FitSession(records=recs), ftp_w=200, weight_kg=70)
    assert result["n_climbs"] >= 1
    assert result["grade_bins"]
    labels = {b["label"] for b in result["grade_bins"]}
    assert any("4-6" in l or "6-8" in l for l in labels)


def test_match_named_climb_geo():
    climb = {
        "start_lat": 51.8000,
        "start_lon": 0.9000,
        "length_m": 1000.0,
        "gain_m": 50.0,
        "avg_grade": 5.0,
    }
    named = {
        "ref_start_lat": 51.8001,
        "ref_start_lon": 0.9001,
        "ref_length_m": 1050.0,
        "ref_gain_m": 52.0,
        "ref_avg_grade": 5.1,
    }
    d = match_named_climb(climb, named)
    assert d is not None
    assert d < 100

    far = dict(named)
    far["ref_start_lat"] = 52.0
    assert match_named_climb(climb, far) is None

    long_mismatch = dict(named)
    long_mismatch["ref_length_m"] = 2000.0
    assert match_named_climb(climb, long_mismatch) is None


def test_haversine_nearby():
    # ~111 m per 0.001 deg lat
    d = haversine_m(51.8, 0.9, 51.8005, 0.9)
    assert 40 < d < 70


def test_pb_recompute_prefers_high_confidence_vam(tmp_path, monkeypatch):
    from ai_endurance_coach_over50.history import db as history_db
    from ai_endurance_coach_over50.history import training_store as ts

    monkeypatch.setattr(history_db, "DB_PATH", tmp_path / "t.db")

    nid = ts.create_named_climb(
        "Test Hill",
        ref_start_lat=51.8, ref_start_lon=0.9,
        ref_length_m=1000, ref_gain_m=55, ref_avg_grade=5.5,
    )
    # Lower VAM but high confidence
    ts.save_climb_attempt(nid, 1, 1, "2026-07-01", {
        "duration_s": 400, "vam_m_h": 500, "vam_confidence": "high",
        "wkg": 2.8, "avg_power": 200,
    })
    # Higher VAM but low confidence — should NOT win VAM PB when high exists
    ts.save_climb_attempt(nid, 2, 1, "2026-07-08", {
        "duration_s": 350, "vam_m_h": 700, "vam_confidence": "low",
        "wkg": 3.1, "avg_power": 220,
    })
    # Best high-confidence VAM
    ts.save_climb_attempt(nid, 3, 1, "2026-07-15", {
        "duration_s": 380, "vam_m_h": 620, "vam_confidence": "high",
        "wkg": 3.0, "avg_power": 210,
    })
    attempts = ts.load_climb_attempts(nid)
    pb_vam = [a for a in attempts if a["is_pb_vam"]]
    assert len(pb_vam) == 1
    assert pb_vam[0]["metrics"]["vam_m_h"] == 620
    pb_time = [a for a in attempts if a["is_pb_time"]]
    assert len(pb_time) == 1
    assert pb_time[0]["metrics"]["duration_s"] == 350
    pb_wkg = [a for a in attempts if a["is_pb_wkg"]]
    assert len(pb_wkg) == 1
    assert pb_wkg[0]["metrics"]["wkg"] == 3.1


def test_essay_prompt_includes_pb_delta():
    climb = {
        "climb_index": 1,
        "gain_m": 85,
        "avg_grade": 5.2,
        "vam_m_h": 640,
        "avg_power": 220,
        "fade_pct": 4.0,
        "avg_cadence": 77,
        "duration_s": 500,
    }
    prior = {
        "name": "Local Col",
        "attempts": [
            {
                "date": "2026-07-05",
                "activity_id": 111,
                "climb_index": 3,
                "metrics": {"vam_m_h": 653, "duration_s": 463, "avg_power": 227, "wkg": 2.5},
            },
            {
                "date": "2026-08-02",
                "activity_id": 222,
                "climb_index": 1,
                "metrics": {"vam_m_h": 640, "duration_s": 500, "avg_power": 220, "wkg": 2.4},
            },
        ],
        "n_attempts": 2,
        "pb_vam": 653,
        "pb_time_s": 463,
        "pb_wkg": 2.5,
        "primary_metric": "vam",
        "delta_vs_first_pct": 5.0,
    }
    prompt = build_climb_essay_prompt(
        climb,
        named={"name": "Local Col"},
        prior_summary=prior,
        activity_date="2026-08-02",
        activity_id=222,
    )
    assert "Local Col" in prompt
    assert "attempt 2 of 2" in prompt.lower()
    assert "NOT a first attempt" in prompt
    assert "first attempt / baseline" not in prompt
    assert "2026-07-05" in prompt
    assert "Season PB VAM: 653" in prompt
    assert "This VAM vs season PB:" in prompt


def test_seed_fit_file_optional():
    """Live check against the user's Aug 2 FIT when present on disk."""
    from pathlib import Path
    path = Path("/Users/martinroffe/Downloads/23823077329_ACTIVITY.fit")
    if not path.exists():
        pytest.skip("seed FIT not present")
    from ai_endurance_coach_over50.analysis.fit_ingest import parse_fit
    fit = parse_fit(str(path))
    assert fit.records
    assert any(r.altitude is not None for r in fit.records)
    assert any(r.power is not None for r in fit.records)
    result = compute_climb_analysis(fit, ftp_w=200, weight_kg=75.0)
    assert result["n_climbs"] >= 1
    # Expect the main ~45 km climb with ~80+ m gain
    main = max(result["climbs"], key=lambda c: c.get("gain_m") or 0)
    assert main["gain_m"] >= 60
    assert 40 < main["start_km"] < 55
    assert main["avg_power"] and main["avg_power"] > 150
    assert main["vam_m_h"] and main["vam_m_h"] > 400
    assert result["grade_bins"]
