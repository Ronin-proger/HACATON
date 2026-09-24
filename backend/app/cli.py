"""CLI: python -m app.cli analyze path.jpg --camera CAM-01"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .config import settings
from .db import Base, SessionLocal, engine
from .seed import seed_if_empty
from .services.pipeline import analyze_image


def main() -> None:
    parser = argparse.ArgumentParser(description="StroySync CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("image")
    analyze.add_argument("--camera", default="CAM-01")
    analyze.add_argument("--at", default=None, help="ISO-дата снимка")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_if_empty(db)
    captured = datetime.fromisoformat(args.at) if args.at else datetime.utcnow()
    snap = analyze_image(
        db,
        image_path=Path(args.image),
        camera_id=args.camera,
        captured_at=captured,
        hint=Path(args.image).name,
    )
    print(f"status={snap.site_status} score={snap.match_score:.2f}")
    print(snap.summary)
    for dev in snap.deviations:
        print(f"[{dev.severity}] {dev.title}")
        print(f"    {dev.explanation}")
    print("annotated:", snap.annotated_path)
    db.close()


if __name__ == "__main__":
    main()
