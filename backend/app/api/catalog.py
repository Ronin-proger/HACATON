from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Camera, Deviation, EquipmentType, Snapshot, WorkStage
from ..services.knowledge import EQUIPMENT_CATALOG
from .serializers import camera_to_out, snapshot_to_out, stage_to_out

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "StroySync"}


@router.get("/equipment")
def equipment(db: Session = Depends(get_db)):
    rows = db.query(EquipmentType).all()
    if rows:
        return [
            {
                "code": r.code,
                "name_ru": r.name_ru,
                "name_en": r.name_en,
                "color": r.color,
                "prompts": r.prompts,
            }
            for r in rows
        ]
    return EQUIPMENT_CATALOG


@router.get("/schedule")
def schedule(db: Session = Depends(get_db), on: str | None = None):
    on_day = date.fromisoformat(on) if on else date.today()
    rows = db.query(WorkStage).order_by(WorkStage.start_date, WorkStage.wbs).all()
    return [stage_to_out(row, on_day=on_day) for row in rows]


@router.get("/cameras")
def cameras(db: Session = Depends(get_db)):
    return [camera_to_out(row) for row in db.query(Camera).all()]


@router.get("/cameras/{camera_id}")
def camera(camera_id: str, db: Session = Depends(get_db)):
    row = db.get(Camera, camera_id)
    if row is None:
        raise HTTPException(404, "Камера не найдена")
    return camera_to_out(row)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    snapshots = db.query(Snapshot).order_by(Snapshot.created_at.desc()).limit(12).all()
    deviations = db.query(Deviation).order_by(Deviation.id.desc()).limit(20).all()
    status_counts = {"on_track": 0, "warning": 0, "critical": 0, "unknown": 0}
    equipment_total = {}
    for snap in db.query(Snapshot).all():
        status_counts[snap.site_status] = status_counts.get(snap.site_status, 0) + 1
        for code, n in (snap.detected_counts or {}).items():
            equipment_total[code] = equipment_total.get(code, 0) + n
    return {
        "status_counts": status_counts,
        "equipment_total": equipment_total,
        "recent": [snapshot_to_out(s) for s in snapshots],
        "alerts": [
            {
                "id": d.id,
                "snapshot_id": d.snapshot_id,
                "code": d.code,
                "severity": d.severity,
                "title": d.title,
                "explanation": d.explanation,
                "wbs": d.wbs,
            }
            for d in deviations
            if d.severity in ("warning", "critical")
        ],
    }


CAMERA_GUIDE = {
    "principles": [
        {
            "title": "Высота и угол",
            "text": "Для учёта техники оптимальна высота 8–18 м и угол 30–50°. Слишком крутой надир скрывает силуэт стрелы крана, слишком пологий — даёт сильные перекрытия.",
        },
        {
            "title": "Привязка к WBS",
            "text": "Каждая камера должна смотреть на конкретную зону графика (котлован, каркас, въезд, периметр). Это делает сопоставление снимка с этапом однозначным.",
        },
        {
            "title": "Перекрытие и въезд",
            "text": "Обязательна камера на въезде: она фиксирует миксеры и самосвалы ещё до слепой зоны котлована. Перекрытие соседних камер — не менее 15–20%.",
        },
        {
            "title": "Освещение и сезонность",
            "text": "Ночные заливки бетона требуют ИК или управляемой подсветки. Зимой камера не должна смотреть в низкое солнце; нужен козырёк от снега и обогрев.",
        },
        {
            "title": "Масштаб объекта в кадре",
            "text": "Техника должна занимать не менее 8–12% ширины кадра. Иначе YOLO-World путает каток с грузовиком и теряет манипулятор.",
        },
    ],
    "by_zone": [
        {
            "zone": "Котлован",
            "cameras": ["CAM-01"],
            "advice": "Две точки: борт котлована и противоположный въезд. Вид должен включать дно и бровку.",
        },
        {
            "zone": "Логистика",
            "cameras": ["CAM-02"],
            "advice": "Низкая камера на воротах + обзор площадки складирования. Фиксирует тип входящей техники.",
        },
        {
            "zone": "Пятно застройки",
            "cameras": ["CAM-03"],
            "advice": "Высокая точка, чтобы стрела автокрана не закрывала весь кадр. Второй ракурс с торца здания.",
        },
        {
            "zone": "Периметр",
            "cameras": ["CAM-04"],
            "advice": "Вдоль оси будущих проездов — иначе каток виден только торцом и плохо классифицируется.",
        },
    ],
}


@router.get("/camera-guide")
def camera_guide():
    return CAMERA_GUIDE


@router.get("/criteria")
def criteria_catalog():
    from ..services.knowledge import CRITERIA_WEIGHTS, EQUIPMENT_ROLE, ROLE_RU

    return {
        "weights": CRITERIA_WEIGHTS,
        "grades": {"A": "≥ 85%", "B": "≥ 70%", "C": "≥ 55%", "D": "≥ 35%", "F": "< 35%"},
        "metrics": [
            {"id": "coverage", "name": "Покрытие обязательной техники", "weight": CRITERIA_WEIGHTS["coverage"], "text": "Доля required_equipment, найденной на снимке."},
            {"id": "signature", "name": "Цифровой отпечаток этапа", "weight": CRITERIA_WEIGHTS["signature"], "text": "Jaccard множества классов с typical_signature."},
            {"id": "role_fit", "name": "Технологический профиль", "weight": CRITERIA_WEIGHTS["role_fit"], "text": "Совпадение ролей: земляные, бетон, подъём, вывоз, уплотнение, логистика."},
            {"id": "safety", "name": "Безопасность состава", "weight": CRITERIA_WEIGHTS["safety"], "text": "0, если в кадре запрещённая для этапа техника."},
            {"id": "activity", "name": "Наличие работ", "weight": CRITERIA_WEIGHTS["activity"], "text": "Есть ли техника при активном WBS."},
        ],
        "roles": [{"code": k, "role": v, "role_ru": ROLE_RU.get(v, v)} for k, v in EQUIPMENT_ROLE.items()],
        "rules": [
            "MISSING_REQUIRED",
            "FORBIDDEN_EQUIPMENT",
            "ROLE_MISMATCH",
            "AHEAD_OF_SCHEDULE",
            "BEHIND_SCHEDULE",
            "NO_ACTIVITY",
            "INSUFFICIENT_FLEET",
            "LOW_CONFIDENCE",
            "ON_TRACK",
        ],
    }
