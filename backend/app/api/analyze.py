from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Camera, Snapshot
from ..schemas import AnalyzeResponse
from ..seed import stages_as_dicts
from ..services.pipeline import analyze_image
from .serializers import camera_to_out, snapshot_to_out, stage_to_out

router = APIRouter(prefix="/api", tags=["analyze"])


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return cleaned or "snapshot.jpg"


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile = File(...),
    camera_id: str = Form("CAM-01"),
    captured_at: str | None = Form(None),
    db: Session = Depends(get_db),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, f"Камера {camera_id} не найдена")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = settings.upload_dir / f"{ts}_{_safe_filename(file.filename or 'snapshot.jpg')}"
    dest.write_bytes(await file.read())
    when = datetime.fromisoformat(captured_at) if captured_at else datetime.utcnow()
    try:
        snapshot = analyze_image(
            db,
            image_path=dest,
            camera_id=camera_id,
            captured_at=when,
            hint=file.filename,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

    by_wbs = {row["wbs"]: row for row in stages_as_dicts(db)}
    linked = []
    for item in snapshot.active_stages or []:
        raw = by_wbs.get(item["wbs"])
        if raw:
            linked.append(stage_to_out(SimpleNamespace(**raw), on_day=when))
    return AnalyzeResponse(
        snapshot=snapshot_to_out(snapshot),
        linked_stages=linked,
        camera=camera_to_out(camera),
    )


@router.get("/snapshots")
def list_snapshots(db: Session = Depends(get_db)):
    rows = db.query(Snapshot).order_by(Snapshot.created_at.desc()).limit(50).all()
    return [snapshot_to_out(row) for row in rows]


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    row = db.get(Snapshot, snapshot_id)
    if row is None:
        raise HTTPException(404, "Снимок не найден")
    return snapshot_to_out(row)
