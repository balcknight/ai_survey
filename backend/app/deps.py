"""FastAPI 鉴权依赖。"""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from . import models, security
from .db import get_db

_BEARER_PREFIX = "bearer "


def extract_raw_token(request: Request, authorization: str | None, token_query: str | None) -> str | None:
    """优先取 Authorization: Bearer <token>；`?token=` 仅作浏览器原生资源加载兜底。

    `<img>/<iframe>/<a>` 直连的资源端点（峰图/GC 图/HTML 报告/压缩包下载）
    无法携带请求头，故允许 query 传 token；JSON 接口一律走 Header。
    """
    if authorization and authorization.lower().startswith(_BEARER_PREFIX):
        raw = authorization[len(_BEARER_PREFIX):].strip()
        if raw:
            return raw
    return token_query or None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, alias="token", include_in_schema=False),
) -> models.User:
    raw = extract_raw_token(request, authorization, token)
    if not raw:
        raise HTTPException(status_code=401, detail="未登录或登录已过期", headers={"WWW-Authenticate": "Bearer"})

    stmt = (
        select(models.UserSession)
        .where(models.UserSession.token_hash == security.hash_token(raw))
        .options(joinedload(models.UserSession.user))
    )
    session = db.execute(stmt).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期", headers={"WWW-Authenticate": "Bearer"})
    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录", headers={"WWW-Authenticate": "Bearer"})
    # 停用账号即使有未过期会话也逐请求拒绝（脚本停用时会另删其全部会话，双保险）。
    if not session.user.is_active:
        raise HTTPException(status_code=401, detail="账号已停用", headers={"WWW-Authenticate": "Bearer"})
    return session.user
