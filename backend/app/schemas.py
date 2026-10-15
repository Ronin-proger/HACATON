from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EquipmentOut(BaseModel):
    code: str
    name_ru: str
    name_en: str
    color: str
    prompts: list[str] = Field(default_factory=list)


class StageOut(BaseModel):
    wbs: str
    parent_wbs: str | None = None
    name: str
    level: int
    zone: str
    start_date: str
    end_date: str
    required_equipment: list[str] = Field(default_factory=list)
    allowed_equipment: list[str] = Field(default_factory=list)
    forbidden_equipment: list[str] = Field(default_factory=list)
    typical_signature: list[str] = Field(default_factory=list)
    description: str = ""
    time_status: str | None = None


class CameraOut(BaseModel):
    id: str
    name: str
    zone: str
    linked_wbs: list[str]
    view: str
    height_m: float
    angle_deg: float
    recommendations: str


class DetectionOut(BaseModel):
    equipment_code: str
    label_ru: str
    confidence: float
    bbox: list[float]


class DeviationOut(BaseModel):
    code: str
    severity: str
    title: str
    explanation: str
    wbs: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class SnapshotOut(BaseModel):
    id: int
    camera_id: str
    captured_at: str
    original_url: str
    annotated_url: str | None
    detector_backend: str
    site_status: str
    match_score: float
    summary: str
    active_stages: list[dict[str, Any]]
    detected_counts: dict[str, int]
    criteria: dict[str, Any] = Field(default_factory=dict)
    detections: list[DetectionOut]
    deviations: list[DeviationOut]


class AnalyzeResponse(BaseModel):
    snapshot: SnapshotOut
    linked_stages: list[StageOut]
    camera: CameraOut
