"""Детектор строительной техники.

Приоритет бэкендов:
1. YOLO-World — open-vocabulary, все 8 классов по текстовым промптам.
2. YOLOv8 COCO — запасной вариант (грузовики и близкие классы).
3. demo — детерминированные детекции для встроенных сэмплов и офлайн-показа.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from .knowledge import CATALOG_BY_CODE, EQUIPMENT_CATALOG, resolve_equipment_code

logger = logging.getLogger(__name__)


@dataclass
class RawDetection:
    equipment_code: str
    label_ru: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class EquipmentDetector:
    def __init__(self) -> None:
        self.backend = "demo"
        self.model = None
        self._loaded = False

    def load(self) -> str:
        if self._loaded:
            return self.backend
        requested = settings.detector_backend
        if requested in ("auto", "world"):
            if self._try_world():
                self._loaded = True
                return self.backend
            if requested == "world":
                logger.warning("YOLO-World недоступен, переключаюсь на запасной режим")
        if requested in ("auto", "coco"):
            if self._try_coco():
                self._loaded = True
                return self.backend
        self.backend = "demo"
        self._loaded = True
        logger.info("Детектор работает в demo-режиме")
        return self.backend

    def _try_world(self) -> bool:
        try:
            from ultralytics import YOLOWorld

            model = YOLOWorld("yolov8s-worldv2.pt")
            prompts = []
            for item in EQUIPMENT_CATALOG:
                prompts.append(item["prompts"][0])
            model.set_classes(prompts)
            self.model = model
            self.backend = "world"
            logger.info("Загружен YOLO-World, классы: %s", prompts)
            return True
        except Exception as exc:
            logger.warning("YOLO-World не загрузился: %s", exc)
            return False

    def _try_coco(self) -> bool:
        try:
            from ultralytics import YOLO

            self.model = YOLO("yolov8n.pt")
            self.backend = "coco"
            logger.info("Загружен YOLOv8n (COCO)")
            return True
        except Exception as exc:
            logger.warning("YOLOv8n не загрузился: %s", exc)
            return False

    def detect(self, image_path: str | Path, hint: str | None = None) -> list[RawDetection]:
        path = Path(image_path)
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Не удалось прочитать изображение: {path}")
        h, w = image.shape[:2]
        name = f"{hint or ''} {path.name}".lower()
        # Синтетические демо-сцены рисуются иконками — нейросеть их не узнает.
        if "sample_" in name and settings.detector_backend != "world":
            return self._demo_detect(w, h, name)
        self.load()
        if self.backend == "world":
            return self._predict_ultralytics(image, open_vocab=True)
        if self.backend == "coco":
            return self._predict_ultralytics(image, open_vocab=False)
        return self._demo_detect(w, h, hint or path.name)

    def _predict_ultralytics(self, image: np.ndarray, open_vocab: bool) -> list[RawDetection]:
        results = self.model.predict(image, conf=settings.detector_conf, verbose=False)
        detections: list[RawDetection] = []
        if not results:
            return detections
        result = results[0]
        names = result.names
        if result.boxes is None:
            return detections
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else str(names[cls_id])
            code = resolve_equipment_code(label)
            if not code:
                continue
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append(
                RawDetection(
                    equipment_code=code,
                    label_ru=CATALOG_BY_CODE[code]["name_ru"],
                    confidence=round(conf, 3),
                    x1=float(xyxy[0]),
                    y1=float(xyxy[1]),
                    x2=float(xyxy[2]),
                    y2=float(xyxy[3]),
                )
            )
        return _nms_by_class(detections)

    def _demo_detect(self, width: int, height: int, hint: str) -> list[RawDetection]:
        """Стабильные боксы для демонстрации и CI без GPU/весов."""
        key = hint.lower()
        presets: dict[str, list[tuple[str, float, tuple[float, float, float, float]]]] = {
            "foundation": [
                ("excavator", 0.91, (0.08, 0.42, 0.38, 0.82)),
                ("concrete_mixer", 0.88, (0.42, 0.38, 0.68, 0.72)),
                ("dump_truck", 0.84, (0.66, 0.48, 0.94, 0.80)),
            ],
            "earthworks": [
                ("bulldozer", 0.90, (0.12, 0.46, 0.40, 0.78)),
                ("excavator", 0.87, (0.44, 0.40, 0.72, 0.84)),
                ("dump_truck", 0.82, (0.70, 0.50, 0.96, 0.82)),
            ],
            "frame": [
                ("mobile_crane", 0.93, (0.18, 0.12, 0.48, 0.88)),
                ("truck", 0.81, (0.52, 0.55, 0.78, 0.82)),
                ("manipulator_crane", 0.79, (0.72, 0.42, 0.96, 0.80)),
            ],
            "roads": [
                ("roller", 0.89, (0.20, 0.50, 0.48, 0.78)),
                ("dump_truck", 0.85, (0.52, 0.46, 0.82, 0.80)),
                ("bulldozer", 0.77, (0.08, 0.42, 0.28, 0.70)),
            ],
            "mismatch": [
                ("mobile_crane", 0.86, (0.15, 0.18, 0.45, 0.86)),
                ("concrete_mixer", 0.80, (0.50, 0.48, 0.78, 0.78)),
            ],
            "empty": [],
        }
        chosen = "foundation"
        for name in presets:
            if name in key:
                chosen = name
                break
        boxes = presets[chosen]
        detections = []
        for code, conf, rel in boxes:
            x1, y1, x2, y2 = rel
            detections.append(
                RawDetection(
                    equipment_code=code,
                    label_ru=CATALOG_BY_CODE[code]["name_ru"],
                    confidence=conf,
                    x1=x1 * width,
                    y1=y1 * height,
                    x2=x2 * width,
                    y2=y2 * height,
                )
            )
        return detections


def _nms_by_class(detections: list[RawDetection], iou_thr: float = 0.55) -> list[RawDetection]:
    kept: list[RawDetection] = []
    by_class: dict[str, list[RawDetection]] = {}
    for det in detections:
        by_class.setdefault(det.equipment_code, []).append(det)
    for items in by_class.values():
        items.sort(key=lambda d: d.confidence, reverse=True)
        selected: list[RawDetection] = []
        for cand in items:
            if all(_iou(cand, other) < iou_thr for other in selected):
                selected.append(cand)
        kept.extend(selected)
    return kept


def _iou(a: RawDetection, b: RawDetection) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0.0, (a.x2 - a.x1) * (a.y2 - a.y1))
    area_b = max(0.0, (b.x2 - b.x1) * (b.y2 - b.y1))
    union = area_a + area_b - inter
    return inter / union if union else 0.0


detector = EquipmentDetector()
