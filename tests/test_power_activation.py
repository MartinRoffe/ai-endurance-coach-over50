"""Phase 6: power meter activation workflow."""
import json
from datetime import date, timedelta

from ai_endurance_coach_over50.analysis import (
    _ensure_analysis_schema,
    patch_analysis_power,
    refresh_power_backfill,
    save_detail,
)
from ai_endurance_coach_over50.history import (
    DB_PATH,
    _conn,
    count_power_rides,
    power_activation_status,
    power_meter_active,
    save_activities,
    save_ftp_test,
)


def _power_act(aid: int, d: str | None = None):
    d = d or date.today().isoformat()
    return {
        "activity_id": aid,
        "date": d,
        "type_key": "road_biking",
        "has_power_meter": 1,
        "avg_power_w": 200,
        "duration_seconds": 5400,
    }


def test_count_power_rides_and_activation_status_empty():
    status = power_activation_status()
    assert status["power_rides_60d"] == 0
    assert status["power_meter_active"] is False
    assert status["complete"] is False
    assert status["next_action"] is not None


def test_activation_complete_when_active_and_ftp_w():
    acts = [_power_act(4000 + i, (date.today() - timedelta(days=i)).isoformat()) for i in range(3)]
    save_activities(acts)
    save_ftp_test(date.today().isoformat(), 4000, 168, 175, ftp_w=250)
    assert count_power_rides(60) == 3
    assert power_meter_active() is True
    status = power_activation_status()
    assert status["has_measured_ftp_w"] is True
    assert status["complete"] is True


def test_patch_analysis_power_updates_zones():
    aid = 5001
    with _conn() as con:
        _ensure_analysis_schema(con)
    save_detail(aid, {
        "hr_zones": [],
        "analysis_text": "ok",
        "ftp_effort_avg_hr": None,
    }, "existing analysis")
    patched = patch_analysis_power(aid, {
        "power_zones": [{"zone": 2, "secs": 1200}],
        "ftp_effort_avg_w": 240,
    })
    assert patched is True
    with _conn() as con:
        row = con.execute(
            "SELECT power_zones_json, ftp_effort_avg_w FROM activity_analyses WHERE activity_id = ?",
            (aid,),
        ).fetchone()
    assert row["ftp_effort_avg_w"] == 240
    zones = json.loads(row["power_zones_json"])
    assert zones[0]["zone"] == 2


def test_refresh_power_backfill_patches_existing_analysis(monkeypatch):
    aid = 6001
    save_activities([_power_act(aid)])
    with _conn() as con:
        _ensure_analysis_schema(con)
    save_detail(aid, {"hr_zones": [], "analysis_text": "x"}, "prior")

    class FakeApi:
        def get_activity_power_in_timezones(self, activity_id):
            return [{"zoneNumber": 2, "secsInZone": 600.0}]

        def get_activity(self, activity_id):
            return {"summaryDTO": {"averagePower": 210}}

    monkeypatch.setattr(
        "ai_endurance_coach_over50.analysis.fetch_activity_detail",
        lambda api, act_id, **kw: {
            "hr_zones": [],
            "power_zones": [{"zone": 2, "secs": 600}],
            "ftp_effort_avg_w": 230,
        },
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.analysis.refresh_analyses",
        lambda api, days=14: None,
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.metrics.fetch_activities",
        lambda api, days=30: [_power_act(aid)],
    )

    stats = refresh_power_backfill(FakeApi(), days=30)
    assert stats["power_rides"] == 1
    assert stats["power_patched"] == 1
