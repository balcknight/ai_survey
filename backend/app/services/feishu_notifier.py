from __future__ import annotations

import json
import logging

import requests

from ..config import get_feishu_settings, get_mail_settings

logger = logging.getLogger("uvicorn.error")


def build_survey_reminder_content(
    *,
    case_id: int,
    sample_code: str | None,
    target_species: str | None,
    transfer_suggestion: str | None,
    summary_text: str | None,
) -> str:
    """构造飞书提醒的 email_content：完整的 post 富文本 JSON 字符串。

    飞书工作流的发送消息节点把 email_content 原样透传给开放平台作为
    消息 content；``msg_type=post`` 时 content 必须是 post 结构的 JSON
    字符串（形如 ``{"zh_cn": {"title": ..., "content": [[...]]}}``），
    否则报 "content is not a string in json format"。

    因此由后端构造完整结构后用 ``json.dumps`` 序列化：结果恒为合法 JSON，
    且作为不透明字符串透传，无换行/引号转义问题。富文本结构使用 text/a/hr
    原生标签（与已验证渲染效果一致的排版）。
    """
    case_list_url = get_mail_settings().case_list_url
    post = {
        "zh_cn": {
            "title": f"【Survey提醒】case_id={case_id} 判定完成，请及时复核",
            "content": [
                [{"tag": "text", "text": "Survey 判定已完成，请及时查看结果并完成人工复核。"}],
                [{"tag": "hr"}],
                [
                    {"tag": "text", "text": "样本编号：", "style": ["bold"]},
                    {"tag": "text", "text": sample_code or "未提供"},
                ],
                [
                    {"tag": "text", "text": "目标物种：", "style": ["bold"]},
                    {"tag": "text", "text": target_species or "未提供"},
                ],
                [
                    {"tag": "text", "text": "case_id：", "style": ["bold"]},
                    {"tag": "text", "text": str(case_id)},
                ],
                [
                    {"tag": "text", "text": "流转建议：", "style": ["bold"]},
                    {"tag": "text", "text": transfer_suggestion or "未提供", "style": ["bold"]},
                ],
                [
                    {"tag": "text", "text": "判定摘要：", "style": ["bold"]},
                    {"tag": "text", "text": summary_text or "未提供"},
                ],
                [{"tag": "hr"}],
                [
                    {"tag": "a", "text": "👉 点击查看判定详情", "href": case_list_url, "style": ["bold"]},
                ],
            ],
        }
    }
    return json.dumps(post, ensure_ascii=False)


def send_feishu_reminder(*, email_content: str, user_list: str | None = None) -> None:
    """触发飞书工作流，发送 Survey 提醒。

    工作流入参两个：
    - ``user_list``：提醒人（当前写死，可用参数覆盖）；
    - ``email_content``：动态正文，由 :func:`build_survey_reminder_content` 生成。

    调用方应将本函数放入后台任务；失败只记日志，不影响主流程。
    """
    settings = get_feishu_settings()
    receivers = (user_list or settings.user_list).strip()
    logger.info(
        "飞书提醒准备发送: enabled=%s, user_list=%s, trigger_url=%s",
        settings.enabled,
        receivers,
        settings.trigger_url,
    )
    if not settings.enabled:
        logger.info("飞书提醒未启用，跳过发送。")
        return
    if not settings.trigger_url:
        logger.warning("飞书提醒已启用但 FEISHU_TRIGGER_URL 为空，跳过发送。")
        return
    if not settings.token:
        logger.warning("飞书提醒已启用但 FEISHU_TOKEN 为空，跳过发送。")
        return
    if not receivers:
        logger.warning("飞书提醒已启用但 FEISHU_USER_LIST 为空，跳过发送。")
        return

    payload = {
        "user_list": receivers,
        "email_content": email_content,
    }
    response = requests.post(
        url=settings.trigger_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        timeout=15,
    )
    response.raise_for_status()

    # 触发接口业务异常时也返回 HTTP 200，需检查响应体 data.code：
    # 成功: {"data": {"code": "0", "message": "success", "data": <记录ID>}, "status_code": "0"}
    # 失败: {"data": {"code": "k_csTri_ec_...", "message": "当前记录未找到"}, "status_code": "0"}
    try:
        body = response.json()
    except ValueError:
        logger.warning(
            "飞书提醒响应非 JSON: resp_status=%s, resp_text=%s",
            response.status_code,
            response.text[:200],
        )
        return
    data = body.get("data") if isinstance(body, dict) else None
    biz_code = data.get("code") if isinstance(data, dict) else None
    if biz_code != "0":
        logger.warning(
            "飞书提醒触发失败(业务错误): user_list=%s, resp_text=%s",
            receivers,
            response.text[:200],
        )
        return

    logger.info(
        "飞书提醒发送成功: user_list=%s, resp_status=%s, resp_text=%s",
        receivers,
        response.status_code,
        response.text[:200],
    )
