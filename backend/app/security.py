"""认证相关纯工具：密码哈希 / 会话 token。

不依赖 FastAPI，可被脚本（scripts/manage_users.py）与后端共用。

- 密码哈希：stdlib PBKDF2-HMAC-SHA256（OWASP 建议 60 万迭代），零第三方依赖。
  存储格式：``pbkdf2_sha256$<迭代数>$<salt_hex>$<hash_hex>``，
  带方案前缀，未来可按前缀分派升级到 bcrypt/argon2 而无需迁移旧哈希。
- 会话 token：``secrets.token_urlsafe(32)``，数据库只存 sha256(token)，
  支持服务端撤销（登出/停用即失效）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16

DEFAULT_TOKEN_TTL_HOURS = 168  # 7 天


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """按存储格式校验密码；格式非法或方案不匹配一律返回 False。"""
    try:
        scheme, iterations_raw, salt_hex, hash_hex = encoded.split("$")
    except (ValueError, AttributeError):
        return False
    if scheme != PBKDF2_SCHEME:
        return False
    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if iterations <= 0:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk.hex(), hash_hex)


def generate_token() -> str:
    """生成会话 token；明文只在登录响应中出现一次，库中仅存哈希。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_token_ttl_hours() -> int:
    raw = os.getenv("AUTH_TOKEN_TTL_HOURS", "").strip()
    if not raw:
        return DEFAULT_TOKEN_TTL_HOURS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TOKEN_TTL_HOURS
    return value if value > 0 else DEFAULT_TOKEN_TTL_HOURS
