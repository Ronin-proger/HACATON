"""Сборка цифровой 3D-модели площадки по фото и видео.

Два взаимно дополняющих контура:
1. Фотометрия: обратная проекция пикселей снимка на землю/котлован
   по известной позе камеры + сопоставление ключевых точек (AKAZE)
   между кадрами и триангуляция для облака точек.
2. Семантика: детекции техники → луч через нижнюю кромку бокса →
   точка контакта с грунтом → 3D-объект на двойнике.

Эталонная модель (mode=default) отдаётся, пока снимков нет.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from .detector import RawDetection, detector
from .knowledge import CATALOG_BY_CODE
from .site_map import CAMERA_POSES, in_pit, intersect_ground, pixel_ray

logger = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MAX_POINTS = 9000
MAX_FRAMES = 10


def default_scene() -> dict:
    return {
        "mode": "default",
        "title": "Эталонный цифровой двойник площадки",
        "summary": "Пока нет снимков — показываем проектную 3D-модель. Загрузите фото или видео, чтобы заменить её актуальной реконструкцией.",
        "progress": {"pit": True, "slab": True, "floors": 1, "crane": True, "roads": True},
        "cameras": _pose_list(),
        "equipment": [
            {"code": "excavator", "position": [-6.0, 0.0, 6.0], "yaw": 0.4, "confidence": 1.0, "label": "Экскаватор", "source": "default"},
            {"code": "concrete_mixer", "position": [2.5, 0.0, 9.5], "yaw": -0.5, "confidence": 1.0, "label": "Бетоносмеситель", "source": "default"},
            {"code": "dump_truck", "position": [-11.0, 0.0, 11.0], "yaw": 1.2, "confidence": 1.0, "label": "Самосвал", "source": "default"},
            {"code": "mobile_crane", "position": [8.0, 0.0, -2.0], "yaw": 0.2, "confidence": 1.0, "label": "Автокран", "source": "default"},
        ],
        "points": {"xyz": [], "rgb": []},
        "stats": {"points": 0, "frames": 0, "matches": 0, "method": "reference-model"},
        "gltf_url": None,
        "ply_url": None,
    }


def reconstruct_from_frames(
    frames: list[tuple[np.ndarray, str, str | None]],
    detections_per_frame: list[list[RawDetection]] | None = None,
) -> dict:
    """frames: (bgr_image, camera_id, label)."""
    if not frames:
        return default_scene()

    all_xyz: list[float] = []
    all_rgb: list[int] = []
    equipment = []
    used_cameras = []
    match_count = 0

    gray_frames = []
    for image, camera_id, _label in frames:
        pose = CAMERA_POSES.get(camera_id, CAMERA_POSES["CAM-01"])
        used_cameras.append({"id": camera_id, **pose})
        xyz, rgb = _backproject_image(image, pose)
        all_xyz.extend(xyz)
        all_rgb.extend(rgb)
        small = cv2.cvtColor(cv2.resize(image, (640, 360)), cv2.COLOR_BGR2GRAY)
        gray_frames.append(small)

    if len(gray_frames) >= 2:
        extra_xyz, extra_rgb, match_count = _triangulate_pairs(frames)
        all_xyz.extend(extra_xyz)
        all_rgb.extend(extra_rgb)

    if detections_per_frame:
        for (image, camera_id, _label), dets in zip(frames, detections_per_frame):
            pose = CAMERA_POSES.get(camera_id, CAMERA_POSES["CAM-01"])
            h, w = image.shape[:2]
            for det in dets:
                item = _detection_to_equipment(det, pose, w, h)
                if item:
                    equipment.append(item)

    xyz, rgb = _downsample(all_xyz, all_rgb, MAX_POINTS)
    progress = _progress_from_equipment(equipment)
    method = "backprojection+akaze" if match_count else "backprojection"
    n_frames = len(frames)
    return {
        "mode": "reconstructed",
        "title": "3D-модель по снимкам площадки",
        "summary": (
            f"Собрано из {n_frames} кадр(ов), {len(xyz) // 3} точек облака, "
            f"{len(equipment)} единиц техники. Метод: {method}."
        ),
        "progress": progress,
        "cameras": used_cameras,
        "equipment": equipment,
        "points": {"xyz": xyz, "rgb": rgb},
        "stats": {
            "points": len(xyz) // 3,
            "frames": n_frames,
            "matches": match_count,
            "method": method,
        },
        "gltf_url": None,
        "ply_url": None,
    }


def extract_media_frames(paths: list[Path], camera_id: str) -> list[tuple[np.ndarray, str, str]]:
    frames: list[tuple[np.ndarray, str, str]] = []
    for path in paths:
        if path.suffix.lower() in VIDEO_EXT:
            frames.extend(_video_frames(path, camera_id))
        else:
            image = cv2.imread(str(path))
            if image is not None:
                frames.append((image, camera_id, path.name))
        if len(frames) >= MAX_FRAMES:
            break
    return frames[:MAX_FRAMES]


def detect_on_frames(frames: list[tuple[np.ndarray, str, str | None]]) -> list[list[RawDetection]]:
    out = []
    tmp_dir = settings.upload_dir / "_twin_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for i, (image, _cam, hint) in enumerate(frames):
        tmp = tmp_dir / f"frame_{i}.jpg"
        cv2.imwrite(str(tmp), image)
        try:
            out.append(detector.detect(tmp, hint=hint))
        except Exception as exc:
            logger.warning("Детекция кадра %s не удалась: %s", i, exc)
            out.append([])
    return out


def write_ply(scene: dict, path: Path) -> Path:
    xyz = scene.get("points", {}).get("xyz") or []
    rgb = scene.get("points", {}).get("rgb") or []
    n = len(xyz) // 3
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as fh:
        fh.write("ply\nformat ascii 1.0\n")
        fh.write(f"element vertex {n}\n")
        fh.write("property float x\nproperty float y\nproperty float z\n")
        fh.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        fh.write("end_header\n")
        for i in range(n):
            x, y, z = xyz[i * 3 : i * 3 + 3]
            r = rgb[i * 3] if i * 3 + 2 < len(rgb) else 180
            g = rgb[i * 3 + 1] if i * 3 + 2 < len(rgb) else 180
            b = rgb[i * 3 + 2] if i * 3 + 2 < len(rgb) else 180
            fh.write(f"{x:.3f} {y:.3f} {z:.3f} {int(r)} {int(g)} {int(b)}\n")
    return path


def write_gltf(scene: dict, path: Path) -> Path:
    """Минимальный glTF: площадка + техника как боксы (для скачивания в CAD/просмотрщиках)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = []
    meshes = []
    accessors = []
    buffer_views = []
    positions = []

    def add_box(cx, cy, cz, sx, sy, sz, color):
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        corners = [
            [cx - hx, cy, cz - hz],
            [cx + hx, cy, cz - hz],
            [cx + hx, cy, cz + hz],
            [cx - hx, cy, cz + hz],
            [cx - hx, cy + sy, cz - hz],
            [cx + hx, cy + sy, cz - hz],
            [cx + hx, cy + sy, cz + hz],
            [cx - hx, cy + sy, cz + hz],
        ]
        idx0 = len(positions) // 3
        for c in corners:
            positions.extend(c)
        faces = [
            0, 1, 2, 0, 2, 3,
            4, 6, 5, 4, 7, 6,
            0, 4, 5, 0, 5, 1,
            1, 5, 6, 1, 6, 2,
            2, 6, 7, 2, 7, 3,
            3, 7, 4, 3, 4, 0,
        ]
        return idx0, faces, color

    boxes = [
        (0, -0.05, 0, 80, 0.1, 80, [0.42, 0.34, 0.24]),
        (-3, -1.4, 6, 20, 2.8, 18, [0.45, 0.36, 0.25]),
        (0, 0.15, 4, 16, 0.3, 12, [0.62, 0.62, 0.6]),
        (12, 0, -8, 16, 1.0, 12, [0.72, 0.71, 0.68]),
    ]
    for eq in scene.get("equipment") or []:
        p = eq["position"]
        boxes.append((p[0], 0.0, p[2], 4.2, 2.4, 2.2, [0.96, 0.65, 0.14]))

    bin_indices = []
    mesh_i = 0
    for cx, cy, cz, sx, sy, sz, color in boxes:
        idx0, faces, color = add_box(cx, cy, cz, sx, sy, sz, color)
        shifted = [idx0 + v for v in faces]
        start = len(bin_indices)
        bin_indices.extend(shifted)
        meshes.append({"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]})
        nodes.append({"mesh": 0, "name": f"part_{mesh_i}"})
        mesh_i += 1

    # Один общий mesh проще для просмотрщика: пересобираем как один primitive
    nodes = [{"mesh": 0, "name": "StroySyncTwin"}]
    meshes = [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}]

    pos_bytes = np.asarray(positions, dtype=np.float32).tobytes()
    idx_bytes = np.asarray(bin_indices, dtype=np.uint32).tobytes()
    blob = pos_bytes + idx_bytes
    bin_name = path.with_suffix(".bin").name
    path.with_suffix(".bin").write_bytes(blob)

    pos_arr = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
    gltf = {
        "asset": {"version": "2.0", "generator": "StroySync"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": meshes,
        "buffers": [{"uri": bin_name, "byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(pos_bytes), "byteLength": len(idx_bytes), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": int(pos_arr.shape[0]),
                "type": "VEC3",
                "min": pos_arr.min(axis=0).tolist(),
                "max": pos_arr.max(axis=0).tolist(),
            },
            {
                "bufferView": 1,
                "componentType": 5125,
                "count": len(bin_indices),
                "type": "SCALAR",
            },
        ],
    }
    import json

    path.write_text(json.dumps(gltf), encoding="utf-8")
    return path


def _pose_list() -> list[dict]:
    return [{"id": cid, **pose} for cid, pose in CAMERA_POSES.items()]


def _backproject_image(image: np.ndarray, pose: dict, stride: int = 7) -> tuple[list[float], list[int]]:
    h, w = image.shape[:2]
    xyz: list[float] = []
    rgb: list[int] = []
    small = image
    if max(h, w) > 1280:
        scale = 1280 / max(h, w)
        small = cv2.resize(image, (int(w * scale), int(h * scale)))
        h, w = small.shape[:2]
    for y in range(0, h, stride):
        for x in range(0, w, stride):
            origin, direction = pixel_ray(pose, x + 0.5, y + 0.5, w, h)
            y_plane = PIT_BOUNDS_DEPTH if False else 0.0
            hit = intersect_ground(origin, direction, 0.0)
            if hit is None:
                continue
            if in_pit(hit[0], hit[2]) and direction[1] < 0:
                pit_hit = intersect_ground(origin, direction, -2.6)
                if pit_hit is not None:
                    hit = pit_hit
            b, g, r = small[y, x]
            # отбрасываем чисто «небо»
            if y < h * 0.18 and r > 90 and b > 110:
                continue
            xyz.extend((float(hit[0]), float(hit[1]), float(hit[2])))
            rgb.extend((int(r), int(g), int(b)))
    return xyz, rgb


PIT_BOUNDS_DEPTH = -2.6


def _detection_to_equipment(det: RawDetection, pose: dict, width: int, height: int) -> dict | None:
    cx = (det.x1 + det.x2) / 2.0
    cy = min(height - 1.0, det.y2)
    origin, direction = pixel_ray(pose, cx, cy, width, height)
    hit = intersect_ground(origin, direction, 0.0)
    if hit is None:
        return None
    if in_pit(hit[0], hit[2]):
        pit = intersect_ground(origin, direction, -2.4)
        if pit is not None:
            hit = pit
    meta = CATALOG_BY_CODE.get(det.equipment_code, {})
    return {
        "code": det.equipment_code,
        "position": [round(float(hit[0]), 2), round(float(hit[1]), 2), round(float(hit[2]), 2)],
        "yaw": round(float(np.arctan2(direction[0], direction[2])), 3),
        "confidence": det.confidence,
        "label": det.label_ru or meta.get("name_ru", det.equipment_code),
        "source": "detection",
        "color": meta.get("color", "#F5A623"),
    }


def _triangulate_pairs(frames: list[tuple[np.ndarray, str, str | None]]) -> tuple[list[float], list[int], int]:
    """Сопоставление AKAZE между соседними кадрами одной камеры / ракурса."""
    xyz: list[float] = []
    rgb: list[int] = []
    matches_total = 0
    akaze = cv2.AKAZE_create()
    prev_gray = prev_color = prev_kp = prev_des = prev_cam = None
    for image, camera_id, _ in frames:
        gray = cv2.cvtColor(cv2.resize(image, (720, 405)), cv2.COLOR_BGR2GRAY)
        color = cv2.resize(image, (720, 405))
        kp, des = akaze.detectAndCompute(gray, None)
        if prev_des is not None and des is not None and prev_cam == camera_id and len(kp) > 20:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            raw = matcher.knnMatch(prev_des, des, k=2)
            good = []
            for pair in raw:
                if len(pair) < 2:
                    continue
                a, b = pair
                if a.distance < 0.75 * b.distance:
                    good.append(a)
            if len(good) >= 12:
                pts1 = np.float32([prev_kp[m.queryIdx].pt for m in good])
                pts2 = np.float32([kp[m.trainIdx].pt for m in good])
                fmat, mask = cv2.findFundamentalMat(pts1, pts2, cv2.FM_RANSAC, 3.0)
                if fmat is not None and mask is not None:
                    inliers = mask.ravel().astype(bool)
                    matches_total += int(inliers.sum())
                    pose = CAMERA_POSES.get(camera_id, CAMERA_POSES["CAM-01"])
                    h, w = color.shape[:2]
                    for p, ok in zip(pts2, inliers):
                        if not ok:
                            continue
                        origin, direction = pixel_ray(pose, float(p[0]), float(p[1]), w, h)
                        hit = intersect_ground(origin, direction, 0.0)
                        if hit is None:
                            continue
                        ix, iy = int(np.clip(p[0], 0, w - 1)), int(np.clip(p[1], 0, h - 1))
                        b, g, r = color[iy, ix]
                        xyz.extend((float(hit[0]), float(hit[1] + 0.15), float(hit[2])))
                        rgb.extend((int(r), int(g), int(b)))
        prev_gray, prev_color, prev_kp, prev_des, prev_cam = gray, color, kp, des, camera_id
    return xyz, rgb, matches_total


def _video_frames(path: Path, camera_id: str) -> list[tuple[np.ndarray, str, str]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, total // MAX_FRAMES) if total else 8
    out = []
    i = 0
    grabbed = 0
    while grabbed < MAX_FRAMES:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            out.append((frame, camera_id, f"{path.stem}_{grabbed}.jpg"))
            grabbed += 1
        i += 1
    cap.release()
    return out


def _downsample(xyz: list[float], rgb: list[int], limit: int) -> tuple[list[float], list[int]]:
    n = len(xyz) // 3
    if n <= limit:
        return xyz, rgb
    step = max(1, n // limit)
    xs, rs = [], []
    for i in range(0, n, step):
        xs.extend(xyz[i * 3 : i * 3 + 3])
        rs.extend(rgb[i * 3 : i * 3 + 3])
        if len(xs) // 3 >= limit:
            break
    return xs, rs


def _progress_from_equipment(equipment: list[dict]) -> dict:
    codes = {e["code"] for e in equipment}
    return {
        "pit": True,
        "slab": "concrete_mixer" in codes or "excavator" in codes,
        "floors": 2 if "mobile_crane" in codes or "manipulator_crane" in codes else 1,
        "crane": "mobile_crane" in codes or "manipulator_crane" in codes,
        "roads": "roller" in codes,
    }
