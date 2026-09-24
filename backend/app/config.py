from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StroySync"
    app_version: str = "1.0.0"
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'stroysync.db'}"
    media_dir: Path = ROOT_DIR / "media"
    data_dir: Path = ROOT_DIR / "data"
    detector_backend: str = "demo"  # demo | auto | world | coco
    detector_conf: float = 0.18
    cors_origins: str = "*"
    obsidian_api_url: str = "https://127.0.0.1:27124"
    obsidian_api_key: str = ""
    obsidian_vault_dir: Path = ROOT_DIR / "HACAOBS"

    @property
    def upload_dir(self) -> Path:
        path = self.media_dir / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def annotated_dir(self) -> Path:
        path = self.media_dir / "annotated"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def twins_dir(self) -> Path:
        path = self.media_dir / "twins"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
