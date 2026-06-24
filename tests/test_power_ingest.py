"""Phase 1 power ingest: activity mapper, schema migration, power_meter_active()."""
from datetime import date, timedelta

from ai_endurance_coach_over50.analysis import (
    _fetch_power_zones,
    _power_summary_from_activity,
    _power_summary_from_dto,
    activity_needs_power_enrichment,
    enrich_activities_power,
    fetch_activity_detail,
)
from ai_endurance_coach_over50.history import (
    patch_activity_power,
    power_meter_active,
    save_activities,
    save_ftp_test,
    load_ftp_tests,
    load_recent_activities,
)
from ai_endurance_coach_over50.metrics import map_activity_power


# ── map_activity_power ───────────────────────────────────────────────────────

def test_map_activity_power_full_dto():
    raw = {
        "averagePower": 210,
        "maxPower": 450,
        "normalizedPower": 225,
        "hasPowerMeter": True,
    }
    assert map_activity_power(raw) == {
        "avg_power_w": 210.0,
        "max_power_w": 450.0,
        "norm_power_w": 225.0,
        "has_power_meter": 1,
    }


def test_map_activity_power_normative_key_variant():
    raw = {"averagePower": 180, "normativePower": 190}
    out = map_activity_power(raw)
    assert out["norm_power_w"] == 190.0
    assert out["has_power_meter"] == 1


def test_map_activity_power_infers_meter_from_avg():
    assert map_activity_power({"averagePower": 150})["has_power_meter"] == 1
    assert map_activity_power({})["has_power_meter"] == 0


def test_map_activity_power_infers_meter_from_max_when_avg_missing():
    out = map_activity_power({"maxPower": 707})
    assert out["has_power_meter"] == 1
    assert out["max_power_w"] == 707.0
    assert out["avg_power_w"] is None


def test_map_activity_power_zero_avg_not_meter():
    assert map_activity_power({"averagePower": 0, "hasPowerMeter": False})["has_power_meter"] == 0


# ── power summary helpers ────────────────────────────────────────────────────

def test_power_summary_from_dto():
    s = {"averagePower": 200, "maxPower": 400, "normalizedPower": 210}
    out = _power_summary_from_dto(s)
    assert out["avg_power_w"] == 200
    assert out["has_power_meter"] is True


def test_power_summary_from_activity_row():
    act = {"avg_power_w": 195, "max_power_w": 380, "norm_power_w": 200, "has_power_meter": 1}
    out = _power_summary_from_activity(act)
    assert out["avg_power_w"] == 195
    assert out["has_power_meter"] is True


# ── power zones fetch ────────────────────────────────────────────────────────

class _FakeApi:
    def __init__(self, zones):
        self._zones = zones

    def get_activity_power_in_timezones(self, activity_id):
        return self._zones


def test_fetch_power_zones_list_format():
    api = _FakeApi([
        {"zoneNumber": 2, "secsInZone": 600, "zoneLowBoundary": 150},
        {"zoneNumber": 1, "secsInZone": 1200, "zoneLowBoundary": 100},
    ])
    zones = _fetch_power_zones(api, 1)
    assert len(zones) == 2
    assert zones[0]["zone"] == 1
    assert zones[0]["secs"] == 1200
    assert zones[0]["pct"] == 67


def test_fetch_power_zones_empty_on_failure():
    class _FailApi:
        def get_activity_power_in_timezones(self, activity_id):
            raise RuntimeError("no power")

    assert _fetch_power_zones(_FailApi(), 1) == []


# ── fetch_activity_detail inline path ────────────────────────────────────────

def test_fetch_activity_detail_inline_includes_power():
    class _Api:
        def get_activity_power_in_timezones(self, activity_id):
            return [{"zoneNumber": 2, "secsInZone": 900, "zoneLowBoundary": 180}]

    activity = {
        "hr_zone_1_sec": 100,
        "hr_zone_2_sec": 200,
        "hr_zone_3_sec": 0,
        "hr_zone_4_sec": 0,
        "hr_zone_5_sec": 0,
        "aerobic_te": 3.2,
        "avg_power_w": 185,
        "max_power_w": 350,
        "norm_power_w": 190,
        "has_power_meter": 1,
    }
    detail = fetch_activity_detail(_Api(), 42, activity=activity)
    assert detail["avg_power_w"] == 185
    assert detail["has_power_meter"] is True
    assert len(detail["power_zones"]) == 1


# ── SQLite schema + power_meter_active ───────────────────────────────────────

def _cycling_act(d: date, *, power: bool, act_id: int) -> dict:
    return {
        "activity_id": act_id,
        "date": d.isoformat(),
        "type_key": "cycling",
        "has_power_meter": 1 if power else 0,
        "avg_power_w": 200 if power else None,
    }


def test_power_meter_active_false_without_enough_rides():
    today = date.today()
    save_activities([
        _cycling_act(today, power=True, act_id=1),
        _cycling_act(today - timedelta(days=1), power=True, act_id=2),
    ])
    assert power_meter_active() is False


def test_power_meter_active_true_with_three_power_rides():
    today = date.today()
    save_activities([
        _cycling_act(today - timedelta(days=i), power=True, act_id=10 + i)
        for i in range(3)
    ])
    assert power_meter_active() is True


def test_power_meter_active_ignores_hr_only_rides():
    today = date.today()
    save_activities([
        _cycling_act(today - timedelta(days=i), power=True, act_id=20 + i)
        for i in range(3)
    ] + [_cycling_act(today, power=False, act_id=99)])
    assert power_meter_active() is True


def test_ftp_tests_ftp_w_column():
    save_ftp_test("2026-06-01", 100, 155, 168, ftp_w=240)
    rows = load_ftp_tests()
    assert rows[0]["ftp_w"] == 240


def test_activity_needs_power_enrichment_list_api_gap():
    act = {
        "activity_id": 99,
        "type_key": "road_biking",
        "max_power_w": 707,
        "avg_power_w": None,
        "norm_power_w": None,
        "has_power_meter": 1,
    }
    assert activity_needs_power_enrichment(act) is True


def test_enrich_activities_power_fills_from_detail_api():
    save_activities([{
        "activity_id": 23360776470,
        "date": date.today().isoformat(),
        "type_key": "road_biking",
        "max_power_w": 707,
        "has_power_meter": 1,
    }])

    class _Api:
        def get_activity(self, activity_id):
            return {"summaryDTO": {
                "averagePower": 128,
                "maxPower": 707,
                "normalizedPower": 147,
            }}

        def get_activity_power_in_timezones(self, activity_id):
            return [{"zoneNumber": 2, "secsInZone": 900, "zoneLowBoundary": 154}]

    acts = load_recent_activities(7)
    n = enrich_activities_power(_Api(), acts)
    assert n == 1
    updated = next(a for a in load_recent_activities(7) if a["activity_id"] == 23360776470)
    assert updated["avg_power_w"] == 128
    assert updated["norm_power_w"] == 147


def test_patch_activity_power_updates_row():
    save_activities([{
        "activity_id": 50,
        "date": date.today().isoformat(),
        "type_key": "cycling",
        "max_power_w": 400,
        "has_power_meter": 1,
    }])
    assert patch_activity_power(50, {"avg_power_w": 210, "norm_power_w": 220}) is True
    row = next(a for a in load_recent_activities(7) if a["activity_id"] == 50)
    assert row["avg_power_w"] == 210
    assert row["norm_power_w"] == 220
