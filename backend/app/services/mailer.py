from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import get_mail_settings

logger = logging.getLogger("uvicorn.error")


def send_survey_done_email(
    *,
    case_id: int,
    sample_code: str | None,
    sample_dir: str,
    transfer_suggestion: str | None,
    summary_text: str | None,
) -> None:
    settings = get_mail_settings()
    logger.info(
        "邮件提醒准备发送: case_id=%s, enabled=%s, to=%s, host=%s:%s, ssl=%s",
        case_id,
        settings.enabled,
        ",".join(settings.to_addrs),
        settings.smtp_host,
        settings.smtp_port,
        settings.use_ssl,
    )
    if not settings.enabled:
        logger.info("邮件提醒未启用，跳过发送。case_id=%s", case_id)
        return
    if not settings.to_addrs:
        logger.warning("邮件提醒已启用但 MAIL_TO 为空，跳过发送。case_id=%s", case_id)
        return
    if not settings.password:
        logger.warning("邮件提醒已启用但 MAIL_SMTP_PASSWORD 为空，跳过发送。case_id=%s", case_id)
        return
    if "<" in settings.password or ">" in settings.password:
        logger.warning(
            "邮件提醒已启用但 MAIL_SMTP_PASSWORD 看起来仍是占位值，跳过发送。case_id=%s",
            case_id,
        )
        return

    subject = f"{settings.subject_prefix} case_id={case_id} 判定完成"
    lines = [
        "Survey 判定已完成，请及时查看结果。",
        "",
        f"样本编号: {sample_code or '未提供'}",
        f"case_id: {case_id}",
        f"样本目录: {sample_dir}",
        f"流转建议: {transfer_suggestion or '未提供'}",
        f"判定摘要: {summary_text or '未提供'}",
        "",
        f"前端查看地址: {settings.case_list_url}",
    ]
    body = "\n".join(lines)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.from_addr
    message["To"] = ",".join(settings.to_addrs)
    message.set_content(body)

    if settings.use_ssl:
        logger.info("邮件提醒使用 SMTP_SSL 发送。case_id=%s", case_id)
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.login(settings.username, settings.password)
            client.send_message(message)
    else:
        logger.info("邮件提醒使用 STARTTLS 发送。case_id=%s", case_id)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.starttls()
            client.login(settings.username, settings.password)
            client.send_message(message)

    logger.info("邮件提醒发送成功: case_id=%s, to=%s", case_id, ",".join(settings.to_addrs))
