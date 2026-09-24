from types import SimpleNamespace

from app.services.detector import RawDetection
from app.services.matcher import match_snapshot


def _det(*codes):
    return [RawDetection(c, c, 0.9, 0, 0, 10, 10) for c in codes]


STAGES = [
    {
        "wbs": "3.1",
        "name": "Бетонирование",
        "zone": "Котлован",
        "start_date": "2026-09-01",
        "end_date": "2026-09-22",
        "required_equipment": ["concrete_mixer"],
        "allowed_equipment": ["concrete_mixer", "excavator", "truck"],
        "forbidden_equipment": ["roller"],
        "typical_signature": ["concrete_mixer", "truck"],
    },
    {
        "wbs": "6",
        "name": "Благоустройство",
        "zone": "Периметр",
        "start_date": "2027-02-01",
        "end_date": "2027-03-31",
        "required_equipment": ["roller"],
        "allowed_equipment": ["roller", "dump_truck"],
        "forbidden_equipment": ["concrete_mixer"],
        "typical_signature": ["roller", "dump_truck"],
    },
]

CAMERA = {"id": "CAM-01", "linked_wbs": ["3.1", "6"], "zone": "Котлован"}


def test_on_track_foundation():
    from datetime import date

    result = match_snapshot(
        detections=_det("concrete_mixer", "truck"),
        stages=STAGES,
        camera=CAMERA,
        on_day=date(2026, 9, 17),
    )
    codes = {d["code"] for d in result["deviations"]}
    assert result["site_status"] in ("on_track", "warning")
    assert "ON_TRACK" in codes
    assert "FORBIDDEN_EQUIPMENT" not in codes


def test_forbidden_roller_on_foundation():
    from datetime import date

    result = match_snapshot(
        detections=_det("roller", "concrete_mixer"),
        stages=STAGES,
        camera=CAMERA,
        on_day=date(2026, 9, 17),
    )
    assert any(d["code"] == "FORBIDDEN_EQUIPMENT" for d in result["deviations"])
    assert result["site_status"] == "critical"


def test_ahead_of_schedule_signal():
    from datetime import date

    result = match_snapshot(
        detections=_det("roller", "dump_truck"),
        stages=STAGES,
        camera=CAMERA,
        on_day=date(2026, 9, 17),
    )
    codes = {d["code"] for d in result["deviations"]}
    assert "AHEAD_OF_SCHEDULE" in codes or "MISSING_REQUIRED" in codes
    assert "criteria" in result
    assert "overall" in result["criteria"]


def test_scorecard_safety_zero_on_forbidden():
    from datetime import date

    result = match_snapshot(
        detections=_det("roller", "concrete_mixer"),
        stages=STAGES,
        camera=CAMERA,
        on_day=date(2026, 9, 17),
    )
    assert result["criteria"]["safety"] == 0.0
    assert result["criteria"]["grade"] in ("D", "F", "C")
