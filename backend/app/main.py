from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers.cases import router as cases_router

app = FastAPI(title="Survey Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # 本地开发常见来源：
    # - http://localhost:5173
    # - http://127.0.0.1:5173
    # - http://192.168.x.x:5173
    # 允许任意端口，便于切换开发服务器端口。
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db():
    db_path = Path("data/survey_backend.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cases_router)

# 兜底初始化，避免测试场景未触发 startup 时出现无表错误。
init_db()
