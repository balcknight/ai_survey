"""登录 / 登出 / 当前用户接口。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..db import get_db
from ..deps import extract_raw_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = (
        db.execute(select(models.User).where(models.User.username == payload.username.strip()))
        .scalar_one_or_none()
    )
    # 用户不存在 / 已停用 / 密码错误统一同一文案，避免用户名枚举。
    if user is None or not user.is_active or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误", headers={"WWW-Authenticate": "Bearer"})

    # 惰性清理全表过期会话（用户量极小，直接删）。
    db.execute(delete(models.UserSession).where(models.UserSession.expires_at < datetime.utcnow()))
    token = security.generate_token()
    expires_at = datetime.utcnow() + timedelta(hours=security.get_token_ttl_hours())
    db.add(
        models.UserSession(
            user_id=user.id,
            token_hash=security.hash_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return schemas.LoginOut(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/logout", response_model=schemas.LogoutOut)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, alias="token", include_in_schema=False),
):
    """幂等登出：token 已失效时调用也不报错。"""
    raw = extract_raw_token(request, authorization, token)
    if raw:
        db.execute(delete(models.UserSession).where(models.UserSession.token_hash == security.hash_token(raw)))
        db.commit()
    return schemas.LogoutOut(ok=True)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
