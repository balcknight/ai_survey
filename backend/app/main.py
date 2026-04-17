from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

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
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations():
    # 当前项目无 alembic，这里做幂等增量列补齐，避免升级时需要手动清库。
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "kmer_results" not in inspector.get_table_names():
            return
        cols = {c["name"] for c in inspector.get_columns("kmer_results")}
        if "spe_plot_path" not in cols:
            conn.execute(text("ALTER TABLE kmer_results ADD COLUMN spe_plot_path TEXT"))
        if "num_plot_path" not in cols:
            conn.execute(text("ALTER TABLE kmer_results ADD COLUMN num_plot_path TEXT"))


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(cases_router)

# 兜底初始化，避免测试场景未触发 startup 时出现无表错误。
init_db()
