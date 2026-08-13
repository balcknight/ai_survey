from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger("uvicorn.error")


def load_env_files() -> None:
    """自动加载 .env 配置文件，不覆盖已存在的系统环境变量。"""
    root = Path(__file__).resolve().parents[2]
    candidates = [root / ".env", root / "backend" / ".env"]
    for env_path in candidates:
        if not env_path.exists() or not env_path.is_file():
            continue
        logger.info("加载配置文件: %s", env_path)
        _load_one_env_file(env_path)


def _load_one_env_file(env_path: Path) -> None:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and ((value[0] == value[-1]) and value[0] in {"'", '"'}):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def log_mail_settings_on_startup() -> None:
    settings = get_mail_settings()
    logger.info(
        "邮件配置启动检查: enabled=%s, to=%s, api_url=%s, local=%s",
        settings.enabled,
        ",".join(settings.to_addrs) or "(空)",
        settings.api_url,
        settings.local,
    )
    if not settings.enabled:
        logger.info(
            "邮件配置提示: 当前 MAIL_ENABLED 为 false。若 .env 已设为 true，请检查是否被 shell 同名环境变量覆盖。"
        )


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MailSettings:
    enabled: bool
    api_url: str
    local: str
    to_addrs: list[str]
    subject_prefix: str
    case_list_url: str


def get_mail_settings() -> MailSettings:
    to_raw = os.getenv("MAIL_TO", "zhurui8901@novogene.com")
    to_addrs = [item.strip() for item in to_raw.split(",") if item.strip()]
    return MailSettings(
        enabled=_as_bool(os.getenv("MAIL_ENABLED"), default=False),
        api_url=os.getenv("MAIL_API_URL", "http://172.17.64.36:8075/api/").strip(),
        local=os.getenv("MAIL_LOCAL", "TJ").strip() or "TJ",
        to_addrs=to_addrs,
        subject_prefix=os.getenv("MAIL_SUBJECT_PREFIX", "[Survey提醒]").strip() or "[Survey提醒]",
        case_list_url=os.getenv("MAIL_CASE_LIST_URL", "http://10.11.0.6:5173/cases").strip(),
    )


@dataclass(frozen=True)
class FeishuSettings:
    enabled: bool
    trigger_url: str
    token: str
    user_list: str


def get_feishu_settings() -> FeishuSettings:
    return FeishuSettings(
        enabled=_as_bool(os.getenv("FEISHU_ENABLED"), default=False),
        trigger_url=os.getenv(
            "FEISHU_TRIGGER_URL",
            "https://ocnz4cb25scn.feishu.cn/ai/api/v1/skill_runtime/namespaces/"
            "spring_3bd562b8e3__c/trigger/g34g1xsq",
        ).strip(),
        token=os.getenv("FEISHU_TOKEN", "0.nlyb8zaaqwb").strip(),
        # 提醒人先写死，后续可改为动态收件策略。
        user_list=os.getenv("FEISHU_USER_LIST", "zhurui8901@novogene.com").strip(),
    )


def log_feishu_settings_on_startup() -> None:
    settings = get_feishu_settings()
    logger.info(
        "飞书提醒配置启动检查: enabled=%s, user_list=%s, trigger_url=%s",
        settings.enabled,
        settings.user_list or "(空)",
        settings.trigger_url,
    )
    if not settings.enabled:
        logger.info(
            "飞书提醒配置提示: 当前 FEISHU_ENABLED 为 false。若 .env 已设为 true，请检查是否被 shell 同名环境变量覆盖。"
        )
