from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class EquipmentType(Base):
    __tablename__ = "equipment_types"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str] = mapped_column(String(128))
    prompts: Mapped[list] = mapped_column(JSON)
    color: Mapped[str] = mapped_column(String(16), default="#F5A623")


class WorkStage(Base):
    """Иерархический этап календарного графика (WBS)."""

    __tablename__ = "work_stages"

    wbs: Mapped[str] = mapped_column(String(32), primary_key=True)
    parent_wbs: Mapped[str | None] = mapped_column(String(32), ForeignKey("work_stages.wbs"), nullable=True)
    name: Mapped[str] = mapped_column(String(256))
    level: Mapped[int] = mapped_column(Integer, default=1)
    zone: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[str] = mapped_column(String(16))
    end_date: Mapped[str] = mapped_column(String(16))
    required_equipment: Mapped[list] = mapped_column(JSON, default=list)
    allowed_equipment: Mapped[list] = mapped_column(JSON, default=list)
    forbidden_equipment: Mapped[list] = mapped_column(JSON, default=list)
    typical_signature: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    zone: Mapped[str] = mapped_column(String(128))
    linked_wbs: Mapped[list] = mapped_column(JSON, default=list)
    view: Mapped[str] = mapped_column(Text, default="")
    height_m: Mapped[float] = mapped_column(Float, default=8.0)
    angle_deg: Mapped[float] = mapped_column(Float, default=35.0)
    recommendations: Mapped[str] = mapped_column(Text, default="")

    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="camera")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(32), ForeignKey("cameras.id"))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    original_path: Mapped[str] = mapped_column(String(512))
    annotated_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detector_backend: Mapped[str] = mapped_column(String(32), default="demo")
    site_status: Mapped[str] = mapped_column(String(32), default="unknown")
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text, default="")
    active_stages: Mapped[list] = mapped_column(JSON, default=list)
    detected_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    camera: Mapped[Camera] = relationship(back_populates="snapshots")
    detections: Mapped[list["Detection"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")
    deviations: Mapped[list["Deviation"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("snapshots.id"))
    equipment_code: Mapped[str] = mapped_column(String(64))
    label_ru: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)

    snapshot: Mapped[Snapshot] = relationship(back_populates="detections")


class Deviation(Base):
    __tablename__ = "deviations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("snapshots.id"))
    code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(256))
    explanation: Mapped[str] = mapped_column(Text)
    wbs: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)

    snapshot: Mapped[Snapshot] = relationship(back_populates="deviations")


class SiteTwin(Base):
    """Активная 3D-модель площадки: эталон или реконструкция по снимкам."""

    __tablename__ = "site_twins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(32), default="default")
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scene: Mapped[dict] = mapped_column(JSON, default=dict)
    gltf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ply_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
