from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..seed import stages_as_dicts
from ..services.pipeline import analyze_image
from .serializers import snapshot_to_out

router = APIRouter(prefix="/api/demo", tags=["demo"])

SAMPLE_META = [
    {
        "id": "foundation",
        "file": "sample_foundation.jpg",
        "title": "Фундамент / бетонирование",
        "camera_id": "CAM-01",
        "captured_at": "2026-09-17T10:15:00",
        "note": "Ожидаются миксер и техника котлована",
    },
    {
        "id": "earthworks",
        "file": "sample_earthworks.jpg",
        "title": "Земляные работы (архив)",
        "camera_id": "CAM-01",
        "captured_at": "2026-07-20T09:00:00",
        "note": "Исторический снимок этапа 2.1",
    },
    {
        "id": "frame",
        "file": "sample_frame.jpg",
        "title": "Каркас — старт монтажа",
        "camera_id": "CAM-03",
        "captured_at": "2026-09-21T11:40:00",
        "note": "Автокран и доставка элементов",
    },
    {
        "id": "mismatch",
        "file": "sample_mismatch.jpg",
        "title": "Несоответствие этапу",
        "camera_id": "CAM-01",
        "captured_at": "2026-09-17T14:00:00",
        "note": "Автокран и миксер: смесь этапов 3 и 4",
    },
    {
        "id": "roads",
        "file": "sample_roads.jpg",
        "title": "Каток на котловане — чужой этап",
        "camera_id": "CAM-01",
        "captured_at": "2026-09-17T16:20:00",
        "note": "Каток запрещён на бетонировании",
    },
    {
        "id": "empty",
        "file": "sample_empty.jpg",
        "title": "Нет техники в кадре",
        "camera_id": "CAM-01",
        "captured_at": "2026-09-17T07:05:00",
        "note": "Простой на активном этапе",
    },
]


@router.get("/samples")
def list_samples():
    folder = settings.data_dir / "samples"
    items = []
    for meta in SAMPLE_META:
        path = folder / meta["file"]
        items.append({**meta, "available": path.exists()})
    return items


@router.post("/run/{sample_id}")
def run_sample(sample_id: str, db: Session = Depends(get_db)):
    meta = next((m for m in SAMPLE_META if m["id"] == sample_id), None)
    if meta is None:
        raise HTTPException(404, "Сэмпл не найден")
    path = settings.data_dir / "samples" / meta["file"]
    if not path.exists():
        raise HTTPException(404, "Файл сэмпла не сгенерирован. Запустите scripts/generate_samples.py")
    snap = analyze_image(
        db,
        image_path=path,
        camera_id=meta["camera_id"],
        captured_at=datetime.fromisoformat(meta["captured_at"]),
        hint=meta["file"],
    )
    return {"meta": meta, "snapshot": snapshot_to_out(snap), "schedule_hint": stages_as_dicts(db)[:3]}
