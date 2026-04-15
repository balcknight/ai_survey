from __future__ import annotations

from fastapi import FastAPI

from .db import Base, engine
from .routers.cases import router as cases_router

app = FastAPI(title="Survey Backend", version="0.1.0")


def init_db():
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
