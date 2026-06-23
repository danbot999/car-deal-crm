"""Runtime configuration for the local valuation service."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRM_ROOT = ROOT / "crm"
WORK_DIR = CRM_ROOT / "work"
DATABASE_PATH = WORK_DIR / "vehicle-valuation.db"
CRM_DATABASE_PATH = CRM_ROOT / "prisma" / "dev.db"
N8N_DATABASE_PATH = Path.home() / ".n8n" / "database.sqlite"
CLOUD_ENV_PATH = CRM_ROOT / ".env.cloud"
CRM_ENV_PATH = CRM_ROOT / ".env"

API_HOST = os.getenv("VALUATION_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("VALUATION_API_PORT", "8010"))
WORKER_POLL_SECONDS = int(os.getenv("VALUATION_WORKER_POLL_SECONDS", "15"))
RECONCILE_SECONDS = int(os.getenv("VALUATION_RECONCILE_SECONDS", "600"))
INDEX_REFRESH_SECONDS = int(os.getenv("VALUATION_INDEX_REFRESH_SECONDS", "21600"))
DIRECTORY_REFRESH_SECONDS = int(os.getenv("VALUATION_DIRECTORY_REFRESH_SECONDS", "86400"))
LIVE_SEARCH_BUDGET_SECONDS = int(os.getenv("VALUATION_LIVE_BUDGET_SECONDS", "300"))
SOURCE_TIMEOUT_SECONDS = int(os.getenv("VALUATION_SOURCE_TIMEOUT_SECONDS", "20"))
SOURCE_RESULT_LIMIT = int(os.getenv("VALUATION_SOURCE_RESULT_LIMIT", "30"))
MAX_SOURCE_WORKERS = int(os.getenv("VALUATION_SOURCE_WORKERS", "4"))
INDEX_TARGET_LIMIT = int(os.getenv("VALUATION_INDEX_TARGET_LIMIT", "10"))
USER_AGENT = os.getenv(
    "VALUATION_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 CarDealCRM/1.0",
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def combined_env() -> dict[str, str]:
    values = load_env_file(CRM_ENV_PATH)
    values.update(load_env_file(CLOUD_ENV_PATH))
    values.update({key: value for key, value in os.environ.items()})
    return values


def valuation_database_url() -> str:
    configured = os.getenv("VALUATION_DATABASE_URL")
    if configured:
        return configured
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATABASE_PATH.as_posix()}"


def crm_targets() -> list[str]:
    values = combined_env()
    local = values.get("CRM_LOCAL_URL", "http://127.0.0.1:3001").rstrip("/")
    cloud = values.get("CRM_CLOUD_URL", "https://car-deal-crm.onrender.com").rstrip("/")
    return list(dict.fromkeys([local, cloud]))


def shared_token() -> str:
    values = combined_env()
    return values.get("VALUATION_API_TOKEN") or values.get("CRM_INGEST_TOKEN") or ""


def openai_settings() -> tuple[str, str]:
    values = combined_env()
    return (
        values.get("OPENAI_API_KEY", ""),
        values.get("OPENAI_MODEL", "gpt-4o-mini"),
    )
