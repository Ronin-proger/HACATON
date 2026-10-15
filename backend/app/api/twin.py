from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Camera, Detection, SiteTwin, Snapshot
from ..services.detector import RawDetection
from ..services.pipeline import analyze_image
from ..services.reconstructor import (
    default_scene,
    detect_on_frames,
    extract_media_frames,
    reconstruct_from_frames,
    write_gltf,
    write_ply,
)
from .serializers import file_url, snapshot_to_out

router = APIRouter(prefix="/api/twin", tags=["twin"])

VIDEO_AND_IMAGE = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "application/octet-stream",
}


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return cleaned or "media.bin"


def twin_payload(row: SiteTwin) -> dict:
    scene = dict(row.scene or {})
    scene["id"] = row.id
    scene["mode"] = row.mode
    scene["title"] = row.title
    scene["summary"] = row.summary
    scene["gltf_url"] = file_url(row.gltf_path)
    scene["ply_url"] = file_url(row.ply_path)
    scene["created_at"] = row.created_at.isoformat() if row.created_at else None
    scene["is_active"] = row.is_active
    return scene


def _deactivate(db: Session) -> None:
    for row in db.query(SiteTwin).filter(SiteTwin.is_active.is_(True)).all():
        row.is_active = False


def persist_scene(db: Session, scene: dict, source_count: int) -> SiteTwin:
    _deactivate(db)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    gltf_path = settings.twins_dir / f"twin_{ts}.gltf"
    ply_path = settings.twins_dir / f"twin_{ts}.ply"
    write_gltf(scene, gltf_path)
    write_ply(scene, ply_path)
    row = SiteTwin(
        mode=scene.get("mode", "reconstructed"),
        title=scene.get("title", ""),
        summary=scene.get("summary", ""),
        is_active=True,
        scene=scene,
        gltf_path=str(gltf_path),
        ply_path=str(ply_path),
        source_count=source_count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ensure_default_twin(db: Session) -> SiteTwin:
    active = db.query(SiteTwin).filter(SiteTwin.is_active.is_(True)).order_by(SiteTwin.id.desc()).first()
    if active:
        return active
    return persist_scene(db, default_scene(), 0)


@router.get("/current")
def current_twin(db: Session = Depends(get_db)):
    return twin_payload(ensure_default_twin(db))


@router.post("/reset")
def reset_twin(db: Session = Depends(get_db)):
    row = persist_scene(db, default_scene(), 0)
    return twin_payload(row)


@router.post("/reconstruct")
async def reconstruct(
    files: list[UploadFile] = File(...),
    camera_id: str = Form("CAM-01"),
    db: Session = Depends(get_db),
):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, f"Камера {camera_id} не найдена")
    if not files:
        raise HTTPException(400, "Нужен хотя бы один файл")
    saved: list[Path] = []
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    for i, upload in enumerate(files[:12]):
        dest = settings.upload_dir / f"{ts}_{i}_{_safe_name(upload.filename or 'frame.jpg')}"
        dest.write_bytes(await upload.read())
        saved.append(dest)
        suffix = dest.suffix.lower()
        is_video = suffix in {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
        if not is_video:
            try:
                analyze_image(db, image_path=dest, camera_id=camera_id, hint=upload.filename)
            except Exception:
                pass
    frames = extract_media_frames(saved, camera_id)
    if not frames:
        raise HTTPException(400, "Не удалось прочитать кадры")
    detections = detect_on_frames(frames)
    scene = reconstruct_from_frames(frames, detections)
    row = persist_scene(db, scene, len(frames))
    return twin_payload(row)


@router.post("/from-history")
def from_history(db: Session = Depends(get_db), limit: int = 8):
    snaps = db.query(Snapshot).order_by(Snapshot.created_at.desc()).limit(limit).all()
    if not snaps:
        raise HTTPException(400, "Нет снимков для сборки двойника")
    frames = []
    detections = []
    for snap in reversed(snaps):
        image_path = Path(snap.original_path)
        if not image_path.exists():
            continue
        import cv2

        image = cv2.imread(str(image_path))
        if image is None:
            continue
        frames.append((image, snap.camera_id, image_path.name))
        dets = [
            RawDetection(d.equipment_code, d.label_ru, d.confidence, d.x1, d.y1, d.x2, d.y2)
            for d in snap.detections
        ]
        detections.append(dets)
    if not frames:
        raise HTTPException(400, "Файлы снимков недоступны")
    scene = reconstruct_from_frames(frames, detections)
    row = persist_scene(db, scene, len(frames))
    return twin_payload(row)


@router.post("/from-snapshot/{snapshot_id}")
def from_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    snap = db.get(Snapshot, snapshot_id)
    if snap is None:
        raise HTTPException(404, "Снимок не найден")
    import cv2

    image = cv2.imread(snap.original_path)
    if image is None:
        raise HTTPException(400, "Не удалось открыть снимок")
    dets = [
        RawDetection(d.equipment_code, d.label_ru, d.confidence, d.x1, d.y1, d.x2, d.y2)
        for d in snap.detections
    ]
    scene = reconstruct_from_frames([(image, snap.camera_id, Path(snap.original_path).name)], [dets])
    row = persist_scene(db, scene, 1)
    payload = twin_payload(row)
    payload["snapshot"] = snapshot_to_out(snap)
    return payload
