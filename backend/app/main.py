from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import load_env_files, log_mail_settings_on_startup
from .db import Base, engine
from .routers.cases import router as cases_router

# 启动时自动加载项目配置文件（.env / backend/.env）。
load_env_files()

app = FastAPI(title="Survey Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # 本地开发常见来源：
    # - http://localhost:5173
    # - http://127.0.0.1:5173
    # - http://10.11.x.x:5173
    # 允许任意端口，便于切换开发服务器端口。
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.11\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db():
    db_path = Path("data/survey_backend.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_case_columns()


def _ensure_case_columns() -> None:
    required_columns = {
        "stage_code": "VARCHAR(64)",
        "contact_name": "VARCHAR(128)",
        "contact_email": "VARCHAR(255)",
        "cc_emails_json": "TEXT",
        "bioinfo_emails_json": "TEXT",
        "operation_emails_json": "TEXT",
        "group_emails_json": "TEXT",
        "archive_path": "TEXT",
    }
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(survey_cases)")).fetchall()
        existing = {str(r[1]) for r in rows}
        for col, ddl in required_columns.items():
            if col in existing:
                continue
            conn.execute(text(f"ALTER TABLE survey_cases ADD COLUMN {col} {ddl}"))


@app.on_event("startup")
def on_startup():
    init_db()
    log_mail_settings_on_startup()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cases_router)

# 兜底初始化，避免测试场景未触发 startup 时出现无表错误。
init_db()
