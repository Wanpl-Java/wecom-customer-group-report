from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8088


class PathsConfig(BaseModel):
    data_dir: str = "./data"
    output_dir: str = "./output"
    db_path: str = "./data/archive.db"


class WecomConfig(BaseModel):
    corp_id: str = ""
    archive_secret: str = ""
    contact_secret: str = ""
    private_key_path: str = "./keys/private.pem"
    room_allowlist: list[str] = Field(default_factory=list)
    external_only: bool = True


class SdkConfig(BaseModel):
    library_path: str = "./lib/libWeWorkFinanceSdk_C.so"
    batch_size: int = 200
    timeout_seconds: int = 10
    proxy: str = ""
    proxy_password: str = ""


class SyncConfig(BaseModel):
    run_on_startup: bool = False
    interval_minutes: int = 0


class AnalyzeConfig(BaseModel):
    staff_userids: list[str] = Field(default_factory=list)
    default_product: str = "JS"
    sla_hours: float = 48.0


class ReportConfig(BaseModel):
    default_period: str = "month"


class AppConfig(BaseModel):
    mode: str = "demo"  # demo | sdk | json
    server: ServerConfig = Field(default_factory=ServerConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    wecom: WecomConfig = Field(default_factory=WecomConfig)
    sdk: SdkConfig = Field(default_factory=SdkConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    analyze: AnalyzeConfig = Field(default_factory=AnalyzeConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    def resolve(self, p: str | Path) -> Path:
        path = Path(p)
        if path.is_absolute():
            return path
        return (ROOT / path).resolve()

    @property
    def db_path(self) -> Path:
        return self.resolve(self.paths.db_path)

    @property
    def output_dir(self) -> Path:
        return self.resolve(self.paths.output_dir)

    @property
    def data_dir(self) -> Path:
        return self.resolve(self.paths.data_dir)

    @property
    def private_key_path(self) -> Path:
        return self.resolve(self.wecom.private_key_path)

    @property
    def library_path(self) -> Path:
        return self.resolve(self.sdk.library_path)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> AppConfig:
    cfg_path = Path(path or os.environ.get("WECOM_REPORT_CONFIG") or (ROOT / "config.yaml"))
    data: dict[str, Any] = {}
    example = ROOT / "config.example.yaml"
    if example.exists():
        data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    if cfg_path.exists():
        overlay = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        data = _deep_merge(data, overlay)
    # env overrides
    if os.environ.get("WECOM_CORP_ID"):
        data.setdefault("wecom", {})["corp_id"] = os.environ["WECOM_CORP_ID"]
    if os.environ.get("WECOM_ARCHIVE_SECRET"):
        data.setdefault("wecom", {})["archive_secret"] = os.environ["WECOM_ARCHIVE_SECRET"]
    if os.environ.get("WECOM_CONTACT_SECRET"):
        data.setdefault("wecom", {})["contact_secret"] = os.environ["WECOM_CONTACT_SECRET"]
    if os.environ.get("WECOM_MODE"):
        data["mode"] = os.environ["WECOM_MODE"]
    return AppConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
