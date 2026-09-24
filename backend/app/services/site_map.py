"""Мировая система координат стройплощадки и позы камер.

Ось Y — высота. Начало — центр пятна застройки.
Камеры из ТЗ получают фиксированные поза, чтобы снимки
можно было обратно проецировать на землю без калибровки.
"""

from __future__ import annotations

import math

import numpy as np


# Эталонная площадка ~ 80×80 м
CAMERA_POSES = {
    "CAM-01": {
        "position": [0.0, 12.0, 26.0],
        "look_at": [0.0, -1.0, 2.0],
        "fov": 52.0,
        "zone": "pit",
    },
    "CAM-02": {
        "position": [-34.0, 6.5, 10.0],
        "look_at": [-8.0, 1.0, 8.0],
        "fov": 55.0,
        "zone": "gate",
    },
    "CAM-03": {
        "position": [30.0, 18.0, -10.0],
        "look_at": [10.0, 6.0, -6.0],
        "fov": 46.0,
        "zone": "frame",
    },
    "CAM-04": {
        "position": [4.0, 8.0, -32.0],
        "look_at": [0.0, 0.5, -12.0],
        "fov": 50.0,
        "zone": "perimeter",
    },
}

PIT_BOUNDS = {"x0": -14.0, "x1": 8.0, "z0": -4.0, "z1": 16.0, "depth": -2.8}
BUILDING = {"x": 12.0, "z": -8.0, "w": 16.0, "d": 12.0}


def camera_basis(pose: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    origin = np.asarray(pose["position"], dtype=np.float64)
    target = np.asarray(pose["look_at"], dtype=np.float64)
    forward = target - origin
    n = np.linalg.norm(forward)
    forward = forward / n if n else np.array([0.0, 0.0, -1.0])
    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    if np.linalg.norm(right) < 1e-6:
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    up = up / np.linalg.norm(up)
    return origin, right, up, forward


def pixel_ray(pose: dict, x: float, y: float, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    origin, right, up, forward = camera_basis(pose)
    fov = math.radians(pose.get("fov", 50.0))
    aspect = width / max(height, 1)
    ndc_x = x / width * 2.0 - 1.0
    ndc_y = 1.0 - y / height * 2.0
    direction = (
        right * (ndc_x * math.tan(fov / 2.0) * aspect)
        + up * (ndc_y * math.tan(fov / 2.0))
        + forward
    )
    direction = direction / np.linalg.norm(direction)
    return origin, direction


def intersect_ground(origin: np.ndarray, direction: np.ndarray, y_plane: float = 0.0) -> np.ndarray | None:
    if abs(direction[1]) < 1e-6:
        return None
    t = (y_plane - origin[1]) / direction[1]
    if t <= 0.2 or t > 160:
        return None
    point = origin + t * direction
    if abs(point[0]) > 70 or abs(point[2]) > 70:
        return None
    return point


def in_pit(x: float, z: float) -> bool:
    b = PIT_BOUNDS
    return b["x0"] <= x <= b["x1"] and b["z0"] <= z <= b["z1"]
