"""Рисует демонстрационные снимки площадки и Excel-график.

Синтетические кадры нужны, чтобы прототип запускался без внешнего датасета.
Имена файлов содержат ключ сцены — demo-детектор возвращает стабильные боксы.
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
SCHEDULE_DIR = ROOT / "data" / "schedule"


def _font(size: int):
    for name in ("arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _sky_ground(draw, w, h, ground="#6B5A3E"):
    for y in range(int(h * 0.42)):
        t = y / (h * 0.42)
        r = int(92 + 70 * t)
        g = int(130 + 50 * t)
        b = int(168 + 20 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    draw.rectangle([0, int(h * 0.42), w, h], fill=ground)


def _building(draw, box, color="#C4B8A5"):
    x1, y1, x2, y2 = box
    draw.rectangle(box, fill=color, outline="#3E3A36", width=3)
    step = max(18, (x2 - x1) // 6)
    for x in range(x1 + 12, x2 - 8, step):
        for y in range(y1 + 16, y2 - 12, 22):
            draw.rectangle([x, y, x + 10, y + 12], fill="#2C3E50")


def _label(draw, xy, text, fill="#F5A623"):
    draw.rounded_rectangle([xy[0], xy[1], xy[0] + 8 + 9 * len(text), xy[1] + 28], radius=6, fill=fill)
    draw.text((xy[0] + 6, xy[1] + 6), text, fill="#1A1A1A", font=_font(16))


def _excavator(draw, x, y, scale=1.0):
    s = scale
    draw.rectangle([x, y, x + 110 * s, y + 48 * s], fill="#F1C40F", outline="#1A1A1A", width=2)
    draw.polygon([(x + 90 * s, y), (x + 170 * s, y - 70 * s), (x + 185 * s, y - 58 * s), (x + 110 * s, y + 10 * s)], fill="#D4AC0D")
    draw.ellipse([x + 8 * s, y + 36 * s, x + 40 * s, y + 62 * s], fill="#2C3E50")
    draw.ellipse([x + 70 * s, y + 36 * s, x + 102 * s, y + 62 * s], fill="#2C3E50")
    _label(draw, (x, y - 34), "Экскаватор")


def _mixer(draw, x, y, scale=1.0):
    s = scale
    draw.rectangle([x, y + 18 * s, x + 140 * s, y + 52 * s], fill="#3498DB", outline="#1A1A1A", width=2)
    draw.ellipse([x + 70 * s, y - 10 * s, x + 145 * s, y + 55 * s], fill="#5DADE2", outline="#1A1A1A", width=2)
    draw.ellipse([x + 18 * s, y + 42 * s, x + 48 * s, y + 70 * s], fill="#2C3E50")
    draw.ellipse([x + 95 * s, y + 42 * s, x + 125 * s, y + 70 * s], fill="#2C3E50")
    _label(draw, (x, y - 28), "Бетоносмеситель", fill="#3498DB")


def _dump(draw, x, y, scale=1.0):
    s = scale
    draw.rectangle([x + 40 * s, y, x + 150 * s, y + 46 * s], fill="#E67E22", outline="#1A1A1A", width=2)
    draw.rectangle([x, y + 12 * s, x + 48 * s, y + 46 * s], fill="#D35400")
    draw.ellipse([x + 18 * s, y + 38 * s, x + 48 * s, y + 66 * s], fill="#2C3E50")
    draw.ellipse([x + 105 * s, y + 38 * s, x + 135 * s, y + 66 * s], fill="#2C3E50")
    _label(draw, (x, y - 30), "Самосвал", fill="#E67E22")


def _crane(draw, x, y, scale=1.0):
    s = scale
    draw.rectangle([x, y + 120 * s, x + 90 * s, y + 170 * s], fill="#C0392B")
    draw.line([(x + 45 * s, y + 120 * s), (x + 45 * s, y), (x + 160 * s, y + 40 * s)], fill="#F5A623", width=int(8 * s))
    draw.line([(x + 160 * s, y + 40 * s), (x + 160 * s, y + 110 * s)], fill="#BDC3C7", width=2)
    _label(draw, (x, y + 175 * s), "Автокран", fill="#C0392B")


def _truck(draw, x, y):
    draw.rectangle([x, y, x + 130, y + 40], fill="#2980B9", outline="#1A1A1A", width=2)
    draw.rectangle([x, y - 18, x + 40, y + 10], fill="#1A5276")
    draw.ellipse([x + 16, y + 30, x + 42, y + 54], fill="#2C3E50")
    draw.ellipse([x + 90, y + 30, x + 116, y + 54], fill="#2C3E50")
    _label(draw, (x, y - 46), "Грузовик", fill="#2980B9")


def _manip(draw, x, y):
    draw.rectangle([x, y + 30, x + 110, y + 70], fill="#8E44AD")
    draw.line([(x + 90, y + 30), (x + 150, y - 40), (x + 175, y - 10)], fill="#BB8FCE", width=7)
    _label(draw, (x, y - 8), "Кран-манипулятор", fill="#8E44AD")


def _dozer(draw, x, y):
    draw.rectangle([x + 20, y, x + 120, y + 42], fill="#27AE60")
    draw.rectangle([x, y - 8, x + 24, y + 50], fill="#1E8449")
    draw.ellipse([x + 28, y + 32, x + 58, y + 58], fill="#2C3E50")
    draw.ellipse([x + 80, y + 32, x + 110, y + 58], fill="#2C3E50")
    _label(draw, (x, y - 32), "Бульдозер", fill="#27AE60")


def _roller(draw, x, y):
    draw.rectangle([x + 30, y, x + 110, y + 38], fill="#7F8C8D")
    draw.ellipse([x, y - 6, x + 48, y + 50], fill="#566573")
    draw.ellipse([x + 95, y + 8, x + 135, y + 50], fill="#566573")
    _label(draw, (x, y - 34), "Каток", fill="#95A5A6")


def _hud(draw, w, title, cam, date):
    draw.rectangle([0, 0, w, 54], fill="#0E1116")
    draw.text((18, 8), "StroySync  ·  видеонаблюдение стройплощадки", fill="#F5A623", font=_font(20))
    draw.text((18, 32), f"{cam}   {date}   {title}", fill="#D5DDE8", font=_font(14))


def render(name: str, painter, title: str, cam: str, date: str, ground="#6B5A3E"):
    w, h = 1280, 720
    img = Image.new("RGB", (w, h), "#4A6FA5")
    draw = ImageDraw.Draw(img)
    _sky_ground(draw, w, h, ground)
    _building(draw, (820, 140, 1180, 360), "#B0A090")
    painter(draw)
    _hud(draw, w, title, cam, date)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    path = SAMPLES / name
    img.save(path, quality=92)
    print("wrote", path)


def make_images():
    render(
        "sample_foundation.jpg",
        lambda d: (_excavator(d, 90, 380), _mixer(d, 520, 360), _dump(d, 900, 430)),
        "Бетонирование фундаментной плиты",
        "CAM-01",
        "17.09.2026 10:15",
        "#5C4A32",
    )
    render(
        "sample_earthworks.jpg",
        lambda d: (_dozer(d, 120, 400), _excavator(d, 480, 360), _dump(d, 900, 420)),
        "Разработка котлована",
        "CAM-01",
        "20.07.2026 09:00",
        "#6B5330",
    )
    render(
        "sample_frame.jpg",
        lambda d: (_crane(d, 220, 160), _truck(d, 620, 430), _manip(d, 920, 360)),
        "Монтаж каркаса",
        "CAM-03",
        "21.09.2026 11:40",
        "#7A7268",
    )
    render(
        "sample_mismatch.jpg",
        lambda d: (_crane(d, 180, 150), _mixer(d, 640, 390)),
        "Смешанный состав техники",
        "CAM-01",
        "17.09.2026 14:00",
        "#5C4A32",
    )
    render(
        "sample_roads.jpg",
        lambda d: (_roller(d, 280, 410), _dump(d, 700, 400), _dozer(d, 80, 390)),
        "Каток на активном фундаменте",
        "CAM-01",
        "17.09.2026 16:20",
        "#5C4A32",
    )
    render(
        "sample_empty.jpg",
        lambda d: d.rectangle([60, 420, 1220, 520], fill="#4A3C2A"),
        "Смена не вышла / техника вне кадра",
        "CAM-01",
        "17.09.2026 07:05",
        "#5C4A32",
    )


def make_schedule():
    from app.seed import STAGES

    SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = SCHEDULE_DIR / "calendar_schedule.csv"
    fieldnames = [
        "wbs",
        "parent_wbs",
        "name",
        "level",
        "zone",
        "start_date",
        "end_date",
        "required_equipment",
        "allowed_equipment",
        "forbidden_equipment",
        "typical_signature",
        "description",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in STAGES:
            flat = {
                **row,
                "required_equipment": ",".join(row["required_equipment"]),
                "allowed_equipment": ",".join(row["allowed_equipment"]),
                "forbidden_equipment": ",".join(row["forbidden_equipment"]),
                "typical_signature": ",".join(row["typical_signature"]),
            }
            writer.writerow(flat)

    wb = Workbook()
    ws = wb.active
    ws.title = "Календарный график"
    ws.append(["Код WBS", "Родитель", "Этап", "Уровень", "Зона", "Начало", "Окончание", "Обязательная техника", "Допустимая", "Запрещённая"])
    for row in STAGES:
        ws.append(
            [
                row["wbs"],
                row["parent_wbs"] or "",
                row["name"],
                row["level"],
                row["zone"],
                row["start_date"],
                row["end_date"],
                ", ".join(row["required_equipment"]),
                ", ".join(row["allowed_equipment"]),
                ", ".join(row["forbidden_equipment"]),
            ]
        )
    xlsx = SCHEDULE_DIR / "calendar_schedule.xlsx"
    wb.save(xlsx)
    print("wrote", csv_path)
    print("wrote", xlsx)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    make_images()
    make_schedule()
