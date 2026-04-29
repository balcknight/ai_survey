from __future__ import annotations

import os
from dataclasses import dataclass


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
