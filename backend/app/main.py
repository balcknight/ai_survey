from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from . import models, security
from .config import load_env_files, log_mail_settings_on_startup
from .db import Base, SessionLocal, engine
from .routers.auth import router as auth_router
from .routers.cases import public_router as cases_public_router
from .routers.cases import router as cases_router

logger = logging.getLogger("uvicorn.error")

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
    _ensure_manual_review_columns()
    _ensure_gc_result_columns()
    ensure_default_admin()


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


def _ensure_manual_review_columns() -> None:
    # 老库补 reviewer_id 列。注意：SQLite 的 ALTER TABLE ADD COLUMN 不支持附带
    # FOREIGN KEY/UNIQUE 约束，因此老库中该列为普通可空 INTEGER（新库 create_all 有 FK）。
    # 业务层不依赖 DB 级 FK，此处仅补列并建索引。
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(manual_reviews)")).fetchall()
        existing = {str(r[1]) for r in rows}
        if "reviewer_id" not in existing:
            conn.execute(text("ALTER TABLE manual_reviews ADD COLUMN reviewer_id INTEGER"))
        # 老库补 kmer_incorrect_reason 列（Kmer 判定不正确原因，仅记录用于算法校对）。
        if "kmer_incorrect_reason" not in existing:
            conn.execute(text("ALTER TABLE manual_reviews ADD COLUMN kmer_incorrect_reason TEXT"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_manual_reviews_reviewer_id ON manual_reviews(reviewer_id)")
        )


def _ensure_gc_result_columns() -> None:
    # 老库补 participated 列（GC 是否参与最终裁决；SQLite 无该列时为 NULL）。
    # 注意：SQLite 的 ALTER TABLE ADD COLUMN 不支持附带约束，老库中该列为普通可空 BOOLEAN。
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(gc_results)")).fetchall()
        existing = {str(r[1]) for r in rows}
        if "participated" not in existing:
            conn.execute(text("ALTER TABLE gc_results ADD COLUMN participated BOOLEAN"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_gc_results_participated ON gc_results(participated)")
        )


def ensure_default_admin() -> None:
    """users 表为空时自动创建默认管理员。幂等（--reload 下会多次执行 init_db）。

    密码优先取 ADMIN_PASSWORD；留空则随机生成并打印到启动日志。
    """
    with SessionLocal() as db:
        count = db.execute(select(func.count(models.User.id))).scalar_one()
        if count > 0:
            return
        username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
        display_name = os.getenv("ADMIN_DISPLAY_NAME", "管理员").strip() or username
        password = os.getenv("ADMIN_PASSWORD", "").strip()
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)
        try:
            db.add(
                models.User(
                    username=username,
                    display_name=display_name,
                    password_hash=security.hash_password(password),
                )
            )
            db.commit()
        except IntegrityError:
            # 并发种子（reloader/worker 各跑一次）兜底：另一进程已建好。
            db.rollback()
            return
        if generated:
            logger.warning(
                "已创建默认管理员 %s（显示名: %s），随机密码: %s —— 请登录后尽快用 scripts/manage_users.py 修改",
                username,
                display_name,
                password,
            )
        else:
            logger.info("已创建默认管理员 %s（显示名: %s），密码取自 ADMIN_PASSWORD", username, display_name)


@app.on_event("startup")
def on_startup():
    init_db()
    log_mail_settings_on_startup()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(cases_public_router)

# 兜底初始化，避免测试场景未触发 startup 时出现无表错误。
init_db()
