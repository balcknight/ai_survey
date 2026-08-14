from __future__ import annotations

import logging

import requests

from ..config import get_mail_settings

logger = logging.getLogger("uvicorn.error")


def send_survey_done_email(
    *,
    case_id: int,
    sample_code: str | None,
    sample_dir: str,
    transfer_suggestion: str | None,
    summary_text: str | None,
    body_text: str | None = None,
    to_addrs: list[str] | None = None,
    cc_addrs: list[str] | None = None,
) -> None:
    settings = get_mail_settings()
    receivers = [addr.strip() for addr in (to_addrs or []) if addr.strip()] or settings.to_addrs
    cc_receivers = [addr.strip() for addr in (cc_addrs or []) if addr.strip()]
    logger.info(
        "邮件提醒准备发送: case_id=%s, enabled=%s, to=%s, cc=%s, api_url=%s, local=%s",
        case_id,
        settings.enabled,
        ",".join(receivers),
        ",".join(cc_receivers) or "(无)",
        settings.api_url,
        settings.local,
    )
    if not settings.enabled:
        logger.info("邮件提醒未启用，跳过发送。case_id=%s", case_id)
        return
    if not receivers:
        logger.warning("邮件提醒已启用但收件人为空（MAIL_TO 与动态收件人均为空），跳过发送。case_id=%s", case_id)
        return
    if not settings.api_url:
        logger.warning("邮件提醒已启用但 MAIL_API_URL 为空，跳过发送。case_id=%s", case_id)
        return

    subject = f"{settings.subject_prefix} case_id={case_id} 判定完成"
    if body_text is not None:
        body = body_text.strip() or "（无备注）"
    else:
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

    # 公司内部邮件网关：无需账号密码，POST 表单即可发送。抄送字段为 CC_USER。
    data = {
        "BODY": body,
        "LOCAL": settings.local,
        "USER": ";".join(receivers),
        "TITLE": subject,
    }
    if cc_receivers:
        data["CC_USER"] = ";".join(cc_receivers)
    logger.info("邮件提醒通过内部网关发送。case_id=%s", case_id)
    response = requests.post(
        url=settings.api_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    response.raise_for_status()

    logger.info(
        "邮件提醒发送成功: case_id=%s, to=%s, cc=%s, resp_status=%s, resp_text=%s",
        case_id,
        ",".join(receivers),
        ",".join(cc_receivers) or "(无)",
        response.status_code,
        response.text[:200],
    )
