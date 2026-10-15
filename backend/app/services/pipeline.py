from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Camera, Detection, Deviation, Snapshot
from ..seed import camera_as_dict, stages_as_dicts
from ..services.annotator import annotate_image
from ..services.detector import detector
from ..services.knowledge import parse_day
from ..services.matcher import match_snapshot


def analyze_image(
    db: Session,
    *,
    image_path: Path,
    camera_id: str,
    captured_at: datetime | None = None,
    hint: str | None = None,
) -> Snapshot:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise ValueError(f"Камера {camera_id} не найдена")
    captured_at = captured_at or datetime.utcnow()
    name = f"{hint or ''} {image_path.name}".lower()
    if "sample_" in name and settings.detector_backend != "world":
        backend = "demo"
        detections = detector.detect(image_path, hint=hint)
    else:
        backend = detector.load()
        detections = detector.detect(image_path, hint=hint)
    stages = stages_as_dicts(db)
    result = match_snapshot(
        detections=detections,
        stages=stages,
        camera=camera_as_dict(camera),
        on_day=parse_day(captured_at),
    )
    annotated_name = f"ann_{image_path.stem}.jpg"
    annotated_path = settings.annotated_dir / annotated_name
    annotate_image(image_path, detections, annotated_path)

    snapshot = Snapshot(
        camera_id=camera_id,
        captured_at=captured_at,
        original_path=str(image_path),
        annotated_path=str(annotated_path),
        detector_backend=backend,
        site_status=result["site_status"],
        match_score=result["match_score"],
        summary=result["summary"],
        active_stages=result["active_stages"],
        detected_counts=result["detected_counts"],
        criteria=result.get("criteria") or {},
    )
    db.add(snapshot)
    db.flush()
    for det in detections:
        db.add(
            Detection(
                snapshot_id=snapshot.id,
                equipment_code=det.equipment_code,
                label_ru=det.label_ru,
                confidence=det.confidence,
                x1=det.x1,
                y1=det.y1,
                x2=det.x2,
                y2=det.y2,
            )
        )
    for item in result["deviations"]:
        db.add(
            Deviation(
                snapshot_id=snapshot.id,
                code=item["code"],
                severity=item["severity"],
                title=item["title"],
                explanation=item["explanation"],
                wbs=item.get("wbs"),
                evidence=item.get("evidence") or {},
            )
        )
    db.commit()
    db.refresh(snapshot)
    return snapshot
