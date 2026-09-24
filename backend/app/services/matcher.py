"""Сопоставление обнаруженной техники с календарным графиком.

Критерии (явный scorecard, каждый 0…1):
  coverage  — доля обязательной техники, видимой в кадре;
  signature — Jaccard с typical_signature активного этапа;
  role_fit  — совпадение технологических ролей (бетон / земляные / подъём…);
  safety    — 0 при запрещённой технике, иначе 1;
  activity  — есть ли вообще машины при активном этапе;
  confidence — средняя уверенность детектора (не в overall, а как фильтр).
Итоговый индекс — взвешенная сумма. Правила срабатывают на листовых WBS
(чтобы не дублировать parent/child). Каждое предупреждение несёт rule_id.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from .knowledge import (
    CATALOG_BY_CODE,
    CRITERIA_WEIGHTS,
    EQUIPMENT_ROLE,
    ROLE_RU,
    jaccard,
    stage_time_status,
)

def match_snapshot(
    *,
    detections: list,
    stages: list[dict],
    camera: dict,
    on_day: date,
) -> dict:
    detected_codes = [d.equipment_code for d in detections]
    detected_set = set(detected_codes)
    counts = dict(Counter(detected_codes))
    mean_conf = _mean_confidence(detections)

    linked = set(camera.get("linked_wbs") or [])
    relevant = []
    for stage in stages:
        if linked and not _stage_linked(stage["wbs"], linked):
            continue
        relevant.append({**stage, "time_status": stage_time_status(stage, on_day)})

    active = [s for s in relevant if s["time_status"] == "active"]
    past = [s for s in relevant if s["time_status"] == "past"]
    future = [s for s in relevant if s["time_status"] == "future"]
    leaves = _leaf_stages(active)

    scores = []
    for stage in relevant:
        signature = set(stage.get("typical_signature") or stage.get("allowed_equipment") or [])
        score = jaccard(detected_set, signature) if detected_set else 0.0
        scores.append(
            {
                "wbs": stage["wbs"],
                "name": stage["name"],
                "time_status": stage["time_status"],
                "score": round(score, 3),
                "coverage": _coverage(set(stage.get("required_equipment") or []), detected_set),
                "signature": sorted(signature),
            }
        )
    scores.sort(key=lambda x: x["score"], reverse=True)

    primary = leaves[0] if leaves else (active[0] if active else None)
    criteria = _scorecard(primary, detected_set, counts, mean_conf, bool(active))

    deviations = []
    for stage in leaves:
        deviations.extend(_rules_for_active_stage(stage, detected_set, counts, mean_conf))

    best_future = max(
        future,
        key=lambda s: jaccard(detected_set, set(s.get("typical_signature") or [])),
        default=None,
    )
    best_past = max(
        past,
        key=lambda s: jaccard(detected_set, set(s.get("typical_signature") or [])),
        default=None,
    )
    best_active_score = max(
        (jaccard(detected_set, set(s.get("typical_signature") or [])) for s in active),
        default=0.0,
    )

    if detected_set and best_future is not None:
        future_score = jaccard(detected_set, set(best_future.get("typical_signature") or []))
        if future_score >= 0.5 and future_score > best_active_score + 0.12:
            deviations.append(
                _dev(
                    "AHEAD_OF_SCHEDULE",
                    "warning",
                    f"Признаки работ будущего этапа {best_future['wbs']}",
                    best_future["wbs"],
                    (
                        f"Индекс сходства с будущим этапом «{best_future['name']}» = {future_score:.2f}, "
                        f"с текущим = {best_active_score:.2f}. Состав "
                        f"{', '.join(_ru(c) for c in sorted(detected_set))} ближе к работам "
                        f"{best_future['start_date']}–{best_future['end_date']}."
                    ),
                    {"future_score": round(future_score, 3), "active_score": round(best_active_score, 3), "detected": sorted(detected_set)},
                )
            )

    if detected_set and best_past is not None and active:
        past_score = jaccard(detected_set, set(best_past.get("typical_signature") or []))
        if past_score >= 0.5 and past_score > best_active_score + 0.12:
            deviations.append(
                _dev(
                    "BEHIND_SCHEDULE",
                    "warning",
                    f"Техника характерна для завершённого этапа {best_past['wbs']}",
                    best_past["wbs"],
                    (
                        f"Сходство с прошедшим этапом «{best_past['name']}» (до {best_past['end_date']}) "
                        f"= {past_score:.2f} против {best_active_score:.2f} у текущего. "
                        f"Возможны отставание или невыведенная техника."
                    ),
                    {"past_score": round(past_score, 3), "detected": sorted(detected_set)},
                )
            )

    if not detected_set and active:
        deviations.append(
            _dev(
                "NO_ACTIVITY",
                "warning",
                "На снимке нет строительной техники",
                active[0]["wbs"],
                (
                    "Критерий activity = 0 при активном WBS. Проверьте ракурс, освещённость "
                    "или выход подрядчика на смену."
                ),
                {"active_wbs": [s["wbs"] for s in active], "activity": 0},
            )
        )

    if not active and detected_set:
        deviations.append(
            _dev(
                "WORK_OUTSIDE_SCHEDULE",
                "info",
                "Техника вне активного окна графика этой камеры",
                None,
                "У камеры нет активного этапа на дату снимка, но техника обнаружена — логистика, простой или работы вне WBS зоны.",
                {"detected": sorted(detected_set)},
            )
        )

    if mean_conf and mean_conf < 0.55 and detected_set:
        deviations.append(
            _dev(
                "LOW_CONFIDENCE",
                "info",
                "Низкая уверенность распознавания",
                primary["wbs"] if primary else None,
                f"Средняя уверенность детектора {mean_conf:.2f} < 0.55. Вывод по графику считайте предварительным.",
                {"mean_confidence": round(mean_conf, 3)},
            )
        )

    status = _status_from_criteria(criteria, deviations)
    criteria["grade"] = _grade(criteria["overall"])
    summary = _summarize(status, active, detected_set, deviations, criteria)
    return {
        "detected_counts": counts,
        "detected_set": sorted(detected_set),
        "active_stages": [
            {
                "wbs": s["wbs"],
                "name": s["name"],
                "zone": s.get("zone", ""),
                "start_date": s["start_date"],
                "end_date": s["end_date"],
                "score": next((x["score"] for x in scores if x["wbs"] == s["wbs"]), 0.0),
                "leaf": s["wbs"] in {x["wbs"] for x in leaves},
            }
            for s in active
        ],
        "stage_scores": scores[:8],
        "deviations": deviations,
        "site_status": status,
        "match_score": criteria["overall"],
        "criteria": criteria,
        "summary": summary,
        "relevant_stages": relevant,
    }


def _scorecard(stage: dict | None, detected: set[str], counts: dict, mean_conf: float, has_active: bool) -> dict:
    if stage is None:
        overall = 0.35 if detected else 0.0
        return {
            "coverage": 0.0,
            "signature": 0.0,
            "role_fit": 0.0,
            "safety": 1.0,
            "activity": 1.0 if detected else 0.0,
            "confidence": round(mean_conf, 3),
            "overall": round(overall, 3),
            "weights": CRITERIA_WEIGHTS,
            "grade": _grade(overall),
            "primary_wbs": None,
        }
    required = set(stage.get("required_equipment") or [])
    signature = set(stage.get("typical_signature") or stage.get("allowed_equipment") or [])
    forbidden = set(stage.get("forbidden_equipment") or [])
    coverage = _coverage(required, detected)
    signature_s = jaccard(detected, signature) if detected else 0.0
    role_fit = _role_fit(stage, detected)
    safety = 0.0 if (detected & forbidden) else 1.0
    activity = 0.0 if (has_active and not detected) else (1.0 if detected else 0.5)
    overall = (
        CRITERIA_WEIGHTS["coverage"] * coverage
        + CRITERIA_WEIGHTS["signature"] * signature_s
        + CRITERIA_WEIGHTS["role_fit"] * role_fit
        + CRITERIA_WEIGHTS["safety"] * safety
        + CRITERIA_WEIGHTS["activity"] * activity
    )
    return {
        "coverage": round(coverage, 3),
        "signature": round(signature_s, 3),
        "role_fit": round(role_fit, 3),
        "safety": round(safety, 3),
        "activity": round(activity, 3),
        "confidence": round(mean_conf, 3),
        "overall": round(overall, 3),
        "weights": CRITERIA_WEIGHTS,
        "grade": _grade(overall),
        "primary_wbs": stage.get("wbs"),
        "roles_expected": sorted(_stage_roles(stage)),
        "roles_seen": sorted(_roles_of(detected)),
    }


def _coverage(required: set[str], detected: set[str]) -> float:
    if not required:
        return 1.0
    return len(required & detected) / len(required)


def _roles_of(codes: set[str]) -> set[str]:
    return {EQUIPMENT_ROLE[c] for c in codes if c in EQUIPMENT_ROLE}


def _stage_roles(stage: dict) -> set[str]:
    return _roles_of(
        set(stage.get("required_equipment") or [])
        | set(stage.get("typical_signature") or [])
        | set(stage.get("allowed_equipment") or [])
    )


def _role_fit(stage: dict, detected: set[str]) -> float:
    expected = _stage_roles(stage)
    seen = _roles_of(detected)
    if not expected:
        return 1.0
    if not seen:
        return 0.0
    return jaccard(expected, seen)


def _leaf_stages(active: list[dict]) -> list[dict]:
    wbs_set = {s["wbs"] for s in active}
    leaves = []
    for stage in active:
        if any(other != stage["wbs"] and other.startswith(stage["wbs"] + ".") for other in wbs_set):
            continue
        leaves.append(stage)
    return leaves or list(active)


def _stage_linked(wbs: str, linked: set[str]) -> bool:
    if wbs in linked:
        return True
    return any(wbs == prefix or wbs.startswith(prefix + ".") for prefix in linked)


def _rules_for_active_stage(stage: dict, detected: set[str], counts: dict[str, int], mean_conf: float) -> list[dict]:
    deviations = []
    required = set(stage.get("required_equipment") or [])
    allowed = set(stage.get("allowed_equipment") or required)
    forbidden = set(stage.get("forbidden_equipment") or [])
    min_counts = stage.get("min_count") or {}

    missing = required - detected
    if missing:
        deviations.append(
            _dev(
                "MISSING_REQUIRED",
                "warning",
                f"Не закрыт критерий coverage для этапа {stage['wbs']}",
                stage["wbs"],
                (
                    f"Этап «{stage['name']}» ({stage['start_date']}–{stage['end_date']}). "
                    f"Обязательны: {', '.join(_ru(c) for c in sorted(required))}. "
                    f"Не видны: {', '.join(_ru(c) for c in sorted(missing))}. "
                    f"coverage = {_coverage(required, detected):.0%}."
                ),
                {"missing": sorted(missing), "required": sorted(required), "seen": sorted(detected), "coverage": _coverage(required, detected)},
            )
        )

    for code, need in min_counts.items():
        have = counts.get(code, 0)
        if have and have < int(need):
            deviations.append(
                _dev(
                    "INSUFFICIENT_FLEET",
                    "info",
                    f"Мало единиц «{_ru(code)}» для {stage['wbs']}",
                    stage["wbs"],
                    f"По регламенту минимум {need}, в кадре {have}.",
                    {"code": code, "required": need, "seen": have},
                )
            )

    unexpected = (detected - allowed) - forbidden
    if unexpected:
        deviations.append(
            _dev(
                "UNEXPECTED_EQUIPMENT",
                "info",
                f"Нехарактерная техника для этапа {stage['wbs']}",
                stage["wbs"],
                (
                    f"Допустимы {', '.join(_ru(c) for c in sorted(allowed))}. "
                    f"Также найдены: {', '.join(_ru(c) for c in sorted(unexpected))}. "
                    f"Транзит по кадру не считается нарушением."
                ),
                {"unexpected": sorted(unexpected), "allowed": sorted(allowed)},
            )
        )

    hit_forbidden = detected & forbidden
    if hit_forbidden:
        deviations.append(
            _dev(
                "FORBIDDEN_EQUIPMENT",
                "critical",
                f"Нарушен критерий safety на этапе {stage['wbs']}",
                stage["wbs"],
                (
                    f"На «{stage['name']}» запрещены {', '.join(_ru(c) for c in sorted(forbidden))}. "
                    f"В кадре: {', '.join(_ru(c) for c in sorted(hit_forbidden))}. "
                    f"Это работы другого технологического передела."
                ),
                {"forbidden": sorted(hit_forbidden), "counts": counts, "safety": 0},
            )
        )

    expected_roles = _stage_roles(stage)
    seen_roles = _roles_of(detected)
    if expected_roles and seen_roles and jaccard(expected_roles, seen_roles) < 0.25 and not hit_forbidden:
        deviations.append(
            _dev(
                "ROLE_MISMATCH",
                "warning",
                f"Технологический профиль не совпадает с {stage['wbs']}",
                stage["wbs"],
                (
                    f"Ожидаемые роли: {', '.join(ROLE_RU.get(r, r) for r in sorted(expected_roles))}. "
                    f"В кадре: {', '.join(ROLE_RU.get(r, r) for r in sorted(seen_roles))}."
                ),
                {"expected_roles": sorted(expected_roles), "seen_roles": sorted(seen_roles)},
            )
        )

    if required and not missing and not hit_forbidden:
        deviations.append(
            _dev(
                "ON_TRACK",
                "ok",
                f"Критерии этапа {stage['wbs']} выполнены",
                stage["wbs"],
                (
                    f"coverage = 100%, safety = 1. Обязательный набор «{stage['name']}» закрыт: "
                    f"{', '.join(_ru(c) for c in sorted(detected)) or 'техника'}."
                ),
                {"detected": sorted(detected), "required": sorted(required)},
            )
        )
    return deviations


def _status_from_criteria(criteria: dict, deviations: list[dict]) -> str:
    if any(d["severity"] == "critical" for d in deviations) or criteria.get("safety", 1) < 1:
        return "critical"
    if any(d["severity"] == "warning" for d in deviations) or criteria.get("overall", 0) < 0.55:
        return "warning"
    if criteria.get("overall", 0) >= 0.55:
        return "on_track"
    return "unknown"


def _grade(overall: float) -> str:
    if overall >= 0.85:
        return "A"
    if overall >= 0.70:
        return "B"
    if overall >= 0.55:
        return "C"
    if overall >= 0.35:
        return "D"
    return "F"


def _summarize(status: str, active, detected_set, deviations, criteria) -> str:
    stage_names = ", ".join(s["name"] for s in active) or "нет активного этапа"
    tech = ", ".join(_ru(c) for c in sorted(detected_set)) or "техника не обнаружена"
    labels = {
        "on_track": "Площадка соответствует графику",
        "warning": "Есть отклонения от календарного графика",
        "critical": "Критическое несоответствие этапу работ",
        "unknown": "Недостаточно данных для уверенного вывода",
    }
    n_alert = len([d for d in deviations if d["severity"] in ("warning", "critical")])
    return (
        f"{labels.get(status, status)}. Индекс {criteria.get('overall', 0):.0%} "
        f"(оценка {criteria.get('grade', '—')}). Этапы: {stage_names}. В кадре: {tech}. "
        f"Предупреждений: {n_alert}."
    )


def _mean_confidence(detections: list) -> float:
    if not detections:
        return 0.0
    vals = [float(getattr(d, "confidence", 0.0) or 0.0) for d in detections]
    return sum(vals) / len(vals)


def _dev(code, severity, title, wbs, explanation, evidence) -> dict:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "wbs": wbs,
        "explanation": explanation,
        "evidence": evidence or {},
        "rule_id": code,
    }


def _ru(code: str) -> str:
    item = CATALOG_BY_CODE.get(code)
    return item["name_ru"] if item else code
