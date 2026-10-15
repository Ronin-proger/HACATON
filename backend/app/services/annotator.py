from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .knowledge import CATALOG_BY_CODE


def annotate_image(image_path: str | Path, detections: list, output_path: str | Path) -> str:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Не удалось открыть {image_path}")
    overlay = image.copy()
    for det in detections:
        color = _bgr(CATALOG_BY_CODE.get(det.equipment_code, {}).get("color", "#F5A623"))
        x1, y1, x2, y2 = map(int, (det.x1, det.y1, det.x2, det.y2))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
        label = f"{det.label_ru} {det.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        cv2.rectangle(overlay, (x1, max(0, y1 - th - 10)), (x1 + tw + 10, y1), color, -1)
        cv2.putText(
            overlay,
            label,
            (x1 + 5, y1 - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
    blended = cv2.addWeighted(overlay, 0.92, image, 0.08, 0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), blended)
    return str(output_path)


def _bgr(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    r, g, b = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    return b, g, r
