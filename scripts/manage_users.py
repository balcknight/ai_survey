#!/usr/bin/env python
"""用户管理 CLI（无注册系统，用户由此脚本维护）。

必须从项目根目录运行（数据库路径相对 cwd）：

    conda run -n zhurui_agent python scripts/manage_users.py list
    conda run -n zhurui_agent python scripts/manage_users.py create --username zhurui --display-name 朱锐
    conda run -n zhurui_agent python scripts/manage_users.py reset-password --username zhurui
    conda run -n zhurui_agent python scripts/manage_users.py set-active --username zhurui --active false

密码优先交互输入（两次确认）；也可用 --password 直接传入（会留在 shell history，仅自动化用）。
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from datetime import datetime
from pathlib import Path

# 确保从项目根目录运行时可导入 backend 包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from backend.app import models, security  # noqa: E402
from backend.app.db import Base, SessionLocal, engine  # noqa: E402

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{2,64}$")
MIN_PASSWORD_LEN = 10


def _read_password_from_args_or_prompt(args: argparse.Namespace) -> str:
    if getattr(args, "password", None):
        password = args.password.strip()
        if len(password) < MIN_PASSWORD_LEN:
            raise SystemExit(f"密码长度需 >= {MIN_PASSWORD_LEN} 位")
        return password
    while True:
        first = getpass.getpass("请输入密码（不回显）: ")
        if len(first) < MIN_PASSWORD_LEN:
            print(f"密码长度需 >= {MIN_PASSWORD_LEN} 位，请重新输入。")
            continue
        second = getpass.getpass("请再次输入密码确认: ")
        if first != second:
            print("两次输入不一致，请重新输入。")
            continue
        return first


def _get_user_or_exit(db, username: str) -> models.User:
    user = db.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"用户不存在: {username}")
    return user


def cmd_create(args: argparse.Namespace) -> None:
    username = args.username.strip()
    if not USERNAME_PATTERN.match(username):
        raise SystemExit("用户名需为 2-64 位，仅允许字母/数字/下划线/点/短横线")
    display_name = (args.display_name or "").strip() or username
    password = _read_password_from_args_or_prompt(args)
    with SessionLocal() as db:
        exists = db.execute(select(models.User).where(models.User.username == username)).scalar_one_or_none()
        if exists is not None:
            raise SystemExit(f"用户名已存在: {username}")
        db.add(
            models.User(
                username=username,
                display_name=display_name,
                password_hash=security.hash_password(password),
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise SystemExit(f"用户名已存在: {username}")
    print(f"已创建用户: {username}（显示名: {display_name}）")


def cmd_reset_password(args: argparse.Namespace) -> None:
    username = args.username.strip()
    password = _read_password_from_args_or_prompt(args)
    with SessionLocal() as db:
        user = _get_user_or_exit(db, username)
        user.password_hash = security.hash_password(password)
        db.commit()
    print(f"已重置密码: {username}")


def cmd_set_active(args: argparse.Namespace) -> None:
    username = args.username.strip()
    active = str(args.active).strip().lower() in {"1", "true", "yes", "on"}
    with SessionLocal() as db:
        user = _get_user_or_exit(db, username)
        user.is_active = active
        if not active:
            # 停用即撤销该用户全部在线会话。
            db.execute(delete(models.UserSession).where(models.UserSession.user_id == user.id))
        db.commit()
    print(f"已{'启用' if active else '停用'}用户: {username}" + ("" if active else "（其在线会话已全部注销）"))


def cmd_list(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        users = db.execute(select(models.User).order_by(models.User.id)).scalars().all()
        if not users:
            print("（暂无用户）")
            return
        now = datetime.utcnow()
        print(f"{'id':<4} {'username':<20} {'display_name':<16} {'active':<7} {'active_sessions':<15} created_at")
        for u in users:
            active_sessions = db.execute(
                select(func.count(models.UserSession.id))
                .where(models.UserSession.user_id == u.id)
                .where(models.UserSession.expires_at >= now)
            ).scalar_one()
            print(
                f"{u.id:<4} {u.username:<20} {u.display_name:<16} "
                f"{str(u.is_active).lower():<7} {active_sessions:<15} {u.created_at}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Survey 系统用户管理")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="创建用户")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--display-name", default=None, help="显示名（默认同用户名）")
    p_create.add_argument("--password", default=None, help="密码（缺省则交互输入）")
    p_create.set_defaults(func=cmd_create)

    p_reset = sub.add_parser("reset-password", help="重置密码")
    p_reset.add_argument("--username", required=True)
    p_reset.add_argument("--password", default=None, help="新密码（缺省则交互输入）")
    p_reset.set_defaults(func=cmd_reset_password)

    p_active = sub.add_parser("set-active", help="启用/停用用户")
    p_active.add_argument("--username", required=True)
    p_active.add_argument("--active", required=True, help="true/false")
    p_active.set_defaults(func=cmd_set_active)

    p_list = sub.add_parser("list", help="列出用户")
    p_list.set_defaults(func=cmd_list)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    # 确保 users/user_sessions 表存在（不依赖后端启动）。
    Base.metadata.create_all(bind=engine)
    args.func(args)


if __name__ == "__main__":
    main()
