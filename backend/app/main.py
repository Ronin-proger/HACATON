import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.analyze import router as analyze_router
from .api.catalog import router as catalog_router
from .api.demo import router as demo_router
from .api.notes import router as notes_router
from .api.twin import ensure_default_twin, router as twin_router
from .services.obsidian import ensure_seed
from .config import settings
from .db import Base, SessionLocal, engine, migrate_schema
from .seed import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("stroysync")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.annotated_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        ensure_default_twin(db)
        try:
            seed = ensure_seed()
            logger.info("Obsidian vault: %s notes, api=%s", seed.get("total"), seed.get("api", {}).get("ok"))
        except Exception:
            logger.exception("Не удалось подготовить хранилище HACAOBS")
    finally:
        db.close()
    sample = settings.data_dir / "samples" / "sample_foundation.jpg"
    if not sample.exists():
        import runpy

        script = Path(__file__).resolve().parents[2] / "scripts" / "generate_samples.py"
        if script.exists():
            logger.info("Генерирую демо-снимки и график")
            runpy.run_path(str(script), run_name="__main__")
    logger.info("StroySync готов к работе")
    yield


app = FastAPI(
    title="StroySync API",
    description="Детекция строительной техники и сопоставление с календарным графиком",
    version=settings.app_version,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog_router)
app.include_router(analyze_router)
app.include_router(demo_router)
app.include_router(twin_router)
app.include_router(notes_router)
app.mount("/files", StaticFiles(directory=str(settings.media_dir)), name="files")
_samples_dir = settings.data_dir / "samples"
_samples_dir.mkdir(parents=True, exist_ok=True)
app.mount("/samples", StaticFiles(directory=str(_samples_dir)), name="samples")

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="ui-static")


@app.get("/")
def ui():
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"name": "StroySync", "docs": "/docs", "health": "/api/health"}
