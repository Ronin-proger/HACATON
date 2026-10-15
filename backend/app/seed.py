"""Справочники: типы техники, WBS-график, камеры и их привязка к этапам."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .models import Camera, EquipmentType, WorkStage
from .services.knowledge import EQUIPMENT_CATALOG


STAGES = [
    {
        "wbs": "1",
        "parent_wbs": None,
        "name": "Подготовительные работы",
        "level": 1,
        "zone": "Периметр",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "required_equipment": ["truck", "bulldozer"],
        "allowed_equipment": ["truck", "bulldozer", "dump_truck"],
        "forbidden_equipment": ["concrete_mixer", "mobile_crane"],
        "typical_signature": ["truck", "bulldozer"],
        "description": "Организация стройплощадки, ограждение, временные дороги.",
    },
    {
        "wbs": "1.1",
        "parent_wbs": "1",
        "name": "Расчистка и планировка территории",
        "level": 2,
        "zone": "Периметр",
        "start_date": "2026-06-01",
        "end_date": "2026-06-20",
        "required_equipment": ["bulldozer", "dump_truck"],
        "allowed_equipment": ["bulldozer", "dump_truck", "truck", "excavator"],
        "forbidden_equipment": ["concrete_mixer"],
        "typical_signature": ["bulldozer", "dump_truck"],
        "description": "Срезка растительного слоя, вывоз грунта.",
    },
    {
        "wbs": "2",
        "parent_wbs": None,
        "name": "Земляные работы",
        "level": 1,
        "zone": "Котлован",
        "start_date": "2026-07-01",
        "end_date": "2026-08-15",
        "required_equipment": ["excavator", "dump_truck"],
        "allowed_equipment": ["excavator", "dump_truck", "bulldozer", "roller"],
        "forbidden_equipment": ["concrete_mixer", "mobile_crane"],
        "typical_signature": ["excavator", "dump_truck", "bulldozer"],
        "description": "Разработка котлована, вывоз грунта, обратная засыпка.",
    },
    {
        "wbs": "2.1",
        "parent_wbs": "2",
        "name": "Разработка котлована",
        "level": 2,
        "zone": "Котлован",
        "start_date": "2026-07-01",
        "end_date": "2026-08-05",
        "required_equipment": ["excavator", "dump_truck"],
        "allowed_equipment": ["excavator", "dump_truck", "bulldozer"],
        "forbidden_equipment": ["concrete_mixer", "roller"],
        "typical_signature": ["excavator", "dump_truck"],
        "description": "Выемка грунта экскаваторами, вывоз самосвалами.",
    },
    {
        "wbs": "2.2",
        "parent_wbs": "2",
        "name": "Уплотнение основания",
        "level": 2,
        "zone": "Котлован",
        "start_date": "2026-08-01",
        "end_date": "2026-08-15",
        "required_equipment": ["roller", "dump_truck"],
        "allowed_equipment": ["roller", "dump_truck", "bulldozer"],
        "forbidden_equipment": ["mobile_crane"],
        "typical_signature": ["roller", "dump_truck", "bulldozer"],
        "description": "Послойное уплотнение катками.",
    },
    {
        "wbs": "3",
        "parent_wbs": None,
        "name": "Устройство фундаментов",
        "level": 1,
        "zone": "Котлован",
        "start_date": "2026-08-16",
        "end_date": "2026-09-25",
        "required_equipment": ["concrete_mixer", "excavator"],
        "allowed_equipment": ["concrete_mixer", "excavator", "dump_truck", "truck", "mobile_crane", "manipulator_crane"],
        "forbidden_equipment": ["roller"],
        "typical_signature": ["concrete_mixer", "excavator", "dump_truck"],
        "description": "Опалубка, арматура, бетонирование фундаментной плиты.",
    },
    {
        "wbs": "3.1",
        "parent_wbs": "3",
        "name": "Бетонирование фундаментной плиты",
        "level": 2,
        "zone": "Котлован",
        "start_date": "2026-09-01",
        "end_date": "2026-09-22",
        "required_equipment": ["concrete_mixer"],
        "allowed_equipment": ["concrete_mixer", "excavator", "truck", "mobile_crane", "dump_truck"],
        "forbidden_equipment": ["roller", "bulldozer"],
        "typical_signature": ["concrete_mixer", "truck"],
        "description": "Подача смеси миксерами, работа автокрана по арматурным картам.",
    },
    {
        "wbs": "4",
        "parent_wbs": None,
        "name": "Возведение каркаса",
        "level": 1,
        "zone": "Пятно застройки",
        "start_date": "2026-09-20",
        "end_date": "2026-12-20",
        "required_equipment": ["mobile_crane"],
        "allowed_equipment": ["mobile_crane", "manipulator_crane", "truck", "concrete_mixer"],
        "forbidden_equipment": ["roller", "bulldozer"],
        "typical_signature": ["mobile_crane", "truck", "manipulator_crane"],
        "description": "Монтаж сборных элементов и вертикальных конструкций.",
    },
    {
        "wbs": "4.1",
        "parent_wbs": "4",
        "name": "Монтаж колонн и перекрытий",
        "level": 2,
        "zone": "Пятно застройки",
        "start_date": "2026-09-20",
        "end_date": "2026-11-30",
        "required_equipment": ["mobile_crane", "truck"],
        "allowed_equipment": ["mobile_crane", "truck", "manipulator_crane", "concrete_mixer"],
        "forbidden_equipment": ["roller"],
        "typical_signature": ["mobile_crane", "truck"],
        "description": "Автокран + доставка элементов грузовиками.",
    },
    {
        "wbs": "5",
        "parent_wbs": None,
        "name": "Кровельные и фасадные работы",
        "level": 1,
        "zone": "Пятно застройки",
        "start_date": "2026-12-01",
        "end_date": "2027-02-15",
        "required_equipment": ["manipulator_crane"],
        "allowed_equipment": ["manipulator_crane", "mobile_crane", "truck"],
        "forbidden_equipment": ["excavator", "bulldozer", "roller"],
        "typical_signature": ["manipulator_crane", "truck"],
        "description": "Подача материалов на высоту манипулятором.",
    },
    {
        "wbs": "6",
        "parent_wbs": None,
        "name": "Благоустройство и дороги",
        "level": 1,
        "zone": "Периметр",
        "start_date": "2027-02-01",
        "end_date": "2027-03-31",
        "required_equipment": ["roller", "dump_truck"],
        "allowed_equipment": ["roller", "dump_truck", "bulldozer", "truck"],
        "forbidden_equipment": ["concrete_mixer"],
        "typical_signature": ["roller", "dump_truck", "bulldozer"],
        "description": "Основание дорог, асфальтирование, озеленение.",
    },
]


CAMERAS = [
    {
        "id": "CAM-01",
        "name": "Котлован, северный борт",
        "zone": "Котлован",
        "linked_wbs": ["2", "2.1", "2.2", "3", "3.1"],
        "view": "Обзор котлована и пятна фундаментных работ. Видны въезд самосвалов и зона бетонирования.",
        "height_m": 12.0,
        "angle_deg": 40.0,
        "recommendations": "Высота 10–14 м, угол 35–45°, ориентация на въезд и дно котлована. ИК-подсветка для ночных заливок.",
    },
    {
        "id": "CAM-02",
        "name": "Въезд и логистическая площадка",
        "zone": "Логистика",
        "linked_wbs": ["1", "1.1", "2", "3", "3.1", "4", "4.1"],
        "view": "Контроль входящей техники: самосвалы, миксеры, грузовики с конструкциями.",
        "height_m": 6.0,
        "angle_deg": 20.0,
        "recommendations": "Камера на въездных воротах, 5–7 м, небольшой угол. Нужен ANPR-ракурс и обзор очереди.",
    },
    {
        "id": "CAM-03",
        "name": "Пятно застройки / каркас",
        "zone": "Пятно застройки",
        "linked_wbs": ["4", "4.1", "5"],
        "view": "Вертикальные конструкции, стоянка автокрана, зона складирования.",
        "height_m": 18.0,
        "angle_deg": 50.0,
        "recommendations": "Мачта 16–20 м или фасад соседнего здания. Перекрытие слепых зон стрелой крана.",
    },
    {
        "id": "CAM-04",
        "name": "Периметр и благоустройство",
        "zone": "Периметр",
        "linked_wbs": ["1", "1.1", "6"],
        "view": "Временные дороги, ограждение, будущие проезды.",
        "height_m": 8.0,
        "angle_deg": 30.0,
        "recommendations": "8–10 м, вдоль периметра с перекрытием 20%. Для катков важен вид вдоль оси дороги.",
    },
]


def seed_if_empty(db: Session) -> None:
    if db.query(EquipmentType).count() == 0:
        for item in EQUIPMENT_CATALOG:
            db.add(
                EquipmentType(
                    code=item["code"],
                    name_ru=item["name_ru"],
                    name_en=item["name_en"],
                    prompts=item["prompts"],
                    color=item["color"],
                )
            )
    if db.query(WorkStage).count() == 0:
        for stage in STAGES:
            db.add(WorkStage(**stage))
    if db.query(Camera).count() == 0:
        for camera in CAMERAS:
            db.add(Camera(**camera))
    db.commit()


def stages_as_dicts(db: Session) -> list[dict]:
    rows = db.query(WorkStage).all()
    return [
        {
            "wbs": row.wbs,
            "parent_wbs": row.parent_wbs,
            "name": row.name,
            "level": row.level,
            "zone": row.zone,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "required_equipment": row.required_equipment or [],
            "allowed_equipment": row.allowed_equipment or [],
            "forbidden_equipment": row.forbidden_equipment or [],
            "typical_signature": row.typical_signature or [],
            "description": row.description,
        }
        for row in rows
    ]


def camera_as_dict(camera: Camera) -> dict:
    return {
        "id": camera.id,
        "name": camera.name,
        "zone": camera.zone,
        "linked_wbs": camera.linked_wbs or [],
        "view": camera.view,
        "height_m": camera.height_m,
        "angle_deg": camera.angle_deg,
        "recommendations": camera.recommendations,
    }
