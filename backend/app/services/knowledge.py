"""Таксономия техники и правила сопоставления с этапами WBS.

Правила — явная, проверяемая база знаний: для каждого этапа заданы
обязательная, допустимая и запрещённая техника, а также «цифровой
отпечаток» типичного состава машин. Сопоставление снимка с графиком
считается как Jaccard-сходство множества обнаруженных классов с
отпечатком активного этапа и соседних этапов.
"""

from __future__ import annotations

from datetime import date, datetime

from dateutil.parser import parse as parse_date


EQUIPMENT_CATALOG = [
    {
        "code": "dump_truck",
        "name_ru": "Самосвал",
        "name_en": "Dump truck",
        "prompts": ["dump truck", "dumper truck", "tipper truck", "самосвал"],
        "color": "#E67E22",
    },
    {
        "code": "excavator",
        "name_ru": "Экскаватор",
        "name_en": "Excavator",
        "prompts": ["excavator", "crawler excavator", "digger", "экскаватор"],
        "color": "#F1C40F",
    },
    {
        "code": "roller",
        "name_ru": "Каток",
        "name_en": "Road roller",
        "prompts": ["road roller", "steamroller", "soil compactor", "каток"],
        "color": "#7F8C8D",
    },
    {
        "code": "manipulator_crane",
        "name_ru": "Кран-манипулятор",
        "name_en": "Knuckle-boom crane",
        "prompts": ["knuckle boom crane", "loader crane", "manipulator crane", "кран-манипулятор"],
        "color": "#8E44AD",
    },
    {
        "code": "concrete_mixer",
        "name_ru": "Бетоносмеситель",
        "name_en": "Concrete mixer",
        "prompts": ["concrete mixer truck", "cement mixer", "бетоносмеситель", "миксер"],
        "color": "#3498DB",
    },
    {
        "code": "bulldozer",
        "name_ru": "Бульдозер",
        "name_en": "Bulldozer",
        "prompts": ["bulldozer", "crawler dozer", "бульдозер"],
        "color": "#27AE60",
    },
    {
        "code": "truck",
        "name_ru": "Грузовик",
        "name_en": "Truck",
        "prompts": ["cargo truck", "lorry", "flatbed truck", "грузовик"],
        "color": "#2980B9",
    },
    {
        "code": "mobile_crane",
        "name_ru": "Автокран",
        "name_en": "Mobile crane",
        "prompts": ["mobile crane", "truck crane", "all terrain crane", "автокран"],
        "color": "#C0392B",
    },
]

CODE_BY_PROMPT = {}
for item in EQUIPMENT_CATALOG:
    CODE_BY_PROMPT[item["code"]] = item["code"]
    CODE_BY_PROMPT[item["name_en"].lower()] = item["code"]
    CODE_BY_PROMPT[item["name_ru"].lower()] = item["code"]
    for prompt in item["prompts"]:
        CODE_BY_PROMPT[prompt.lower()] = item["code"]

CATALOG_BY_CODE = {item["code"]: item for item in EQUIPMENT_CATALOG}

# Роль техники в технологической цепочке — отдельный критерий, не сводимый к Jaccard.
EQUIPMENT_ROLE = {
    "excavator": "earthwork",
    "bulldozer": "earthwork",
    "dump_truck": "haul",
    "roller": "compaction",
    "concrete_mixer": "concrete",
    "mobile_crane": "lift",
    "manipulator_crane": "lift",
    "truck": "logistics",
}

ROLE_RU = {
    "earthwork": "земляные",
    "haul": "вывоз грунта",
    "compaction": "уплотнение",
    "concrete": "бетон",
    "lift": "подъём",
    "logistics": "логистика",
}

CRITERIA_WEIGHTS = {
    "coverage": 0.30,
    "signature": 0.20,
    "role_fit": 0.15,
    "safety": 0.25,
    "activity": 0.10,
}

# COCO-классы → строительная техника (грубое соответствие для запасного детектора).
COCO_TO_EQUIPMENT = {
    "truck": "truck",
    "bus": "truck",
    "car": None,
    "train": None,
    "boat": None,
}


def resolve_equipment_code(label: str) -> str | None:
    key = (label or "").strip().lower()
    if key in CODE_BY_PROMPT:
        return CODE_BY_PROMPT[key]
    for prompt, code in CODE_BY_PROMPT.items():
        if prompt in key or key in prompt:
            return code
    if key in COCO_TO_EQUIPMENT:
        return COCO_TO_EQUIPMENT[key]
    return None


def parse_day(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return parse_date(str(value)).date()


def is_stage_active(stage: dict, on_day: date) -> bool:
    return parse_day(stage["start_date"]) <= on_day <= parse_day(stage["end_date"])


def stage_time_status(stage: dict, on_day: date) -> str:
    start, end = parse_day(stage["start_date"]), parse_day(stage["end_date"])
    if on_day < start:
        return "future"
    if on_day > end:
        return "past"
    return "active"


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0
