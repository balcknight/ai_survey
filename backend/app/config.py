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
    masked_pwd = "已设置" if settings.password else "未设置"
    logger.info(
        "邮件配置启动检查: enabled=%s, from=%s, to=%s, smtp=%s:%s, ssl=%s, password=%s",
        settings.enabled,
        settings.from_addr,
        ",".join(settings.to_addrs) or "(空)",
        settings.smtp_host,
        settings.smtp_port,
        settings.use_ssl,
        masked_pwd,
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
    smtp_host: str
    smtp_port: int
    use_ssl: bool
    username: str
    password: str
    from_addr: str
    to_addrs: list[str]
    subject_prefix: str
    case_list_url: str


def get_mail_settings() -> MailSettings:
    to_raw = os.getenv("MAIL_TO", "zhurui8901@novogene.com")
    to_addrs = [item.strip() for item in to_raw.split(",") if item.strip()]
    return MailSettings(
        enabled=_as_bool(os.getenv("MAIL_ENABLED"), default=False),
        smtp_host=os.getenv("MAIL_SMTP_HOST", "smtp.qq.com").strip(),
        smtp_port=int(os.getenv("MAIL_SMTP_PORT", "465").strip()),
        use_ssl=_as_bool(os.getenv("MAIL_SMTP_USE_SSL"), default=True),
        username=os.getenv("MAIL_SMTP_USERNAME", "1623893955@qq.com").strip(),
        password=os.getenv("MAIL_SMTP_PASSWORD", "").strip(),
        from_addr=os.getenv("MAIL_FROM", "1623893955@qq.com").strip(),
        to_addrs=to_addrs,
        subject_prefix=os.getenv("MAIL_SUBJECT_PREFIX", "[Survey提醒]").strip() or "[Survey提醒]",
        case_list_url=os.getenv("MAIL_CASE_LIST_URL", "http://192.168.20.24:5173/cases").strip(),
    )
