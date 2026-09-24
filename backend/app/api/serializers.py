from pathlib import Path

from ..config import settings
from ..models import Snapshot
from ..schemas import CameraOut, DetectionOut, DeviationOut, SnapshotOut, StageOut
from ..services.knowledge import stage_time_status, parse_day


def file_url(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path).resolve()
    for base, prefix in (
        (settings.media_dir.resolve(), "/files"),
        ((settings.data_dir / "samples").resolve(), "/samples"),
    ):
        try:
            rel = p.relative_to(base)
            return f"{prefix}/{rel.as_posix()}"
        except ValueError:
            continue
    return f"/files/{p.name}"


def snapshot_to_out(snapshot: Snapshot) -> SnapshotOut:
    return SnapshotOut(
        id=snapshot.id,
        camera_id=snapshot.camera_id,
        captured_at=snapshot.captured_at.isoformat(),
        original_url=file_url(snapshot.original_path) or "",
        annotated_url=file_url(snapshot.annotated_path),
        detector_backend=snapshot.detector_backend,
        site_status=snapshot.site_status,
        match_score=snapshot.match_score,
        summary=snapshot.summary,
        active_stages=snapshot.active_stages or [],
        detected_counts=snapshot.detected_counts or {},
        criteria=getattr(snapshot, "criteria", None) or {},
        detections=[
            DetectionOut(
                equipment_code=d.equipment_code,
                label_ru=d.label_ru,
                confidence=d.confidence,
                bbox=[d.x1, d.y1, d.x2, d.y2],
            )
            for d in snapshot.detections
        ],
        deviations=[
            DeviationOut(
                code=d.code,
                severity=d.severity,
                title=d.title,
                explanation=d.explanation,
                wbs=d.wbs,
                evidence=d.evidence or {},
            )
            for d in snapshot.deviations
        ],
    )


def stage_to_out(stage, on_day=None) -> StageOut:
    payload = StageOut(
        wbs=stage.wbs,
        parent_wbs=stage.parent_wbs,
        name=stage.name,
        level=stage.level,
        zone=stage.zone,
        start_date=stage.start_date,
        end_date=stage.end_date,
        required_equipment=stage.required_equipment or [],
        allowed_equipment=stage.allowed_equipment or [],
        forbidden_equipment=stage.forbidden_equipment or [],
        typical_signature=stage.typical_signature or [],
        description=stage.description,
    )
    if on_day is not None:
        payload.time_status = stage_time_status(
            {"start_date": stage.start_date, "end_date": stage.end_date},
            parse_day(on_day),
        )
    return payload


def camera_to_out(camera) -> CameraOut:
    return CameraOut(
        id=camera.id,
        name=camera.name,
        zone=camera.zone,
        linked_wbs=camera.linked_wbs or [],
        view=camera.view,
        height_m=camera.height_m,
        angle_deg=camera.angle_deg,
        recommendations=camera.recommendations,
    )
