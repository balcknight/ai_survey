from __future__ import annotations

import json
import logging

import requests

from ..config import get_feishu_settings, get_mail_settings

logger = logging.getLogger("uvicorn.error")

# 归一化后的 final_decision 展示文案。
_FINAL_DECISION_DISPLAY = {
    "transfer": "流转",
    "no_transfer": "不流转",
}


def _kv_row(label: str, value: str, *, bold_value: bool = False) -> list[dict]:
    """字段一行：label 加粗，value 可选加粗。"""
    value_tag: dict = {"tag": "text", "text": value}
    if bold_value:
        value_tag["style"] = ["bold"]
    return [
        {"tag": "text", "text": label, "style": ["bold"]},
        value_tag,
    ]


def _case_info_rows(
    *,
    case_id: int,
    sample_code: str | None,
    target_species: str | None,
    transfer_label: str,
    transfer_suggestion: str | None,
    summary_text: str | None,
    bold_transfer: bool,
) -> list[list[dict]]:
    """两个版本共用的样本基础信息行。"""
    return [
        _kv_row("样本编号：", sample_code or "未提供"),
        _kv_row("目标物种：", target_species or "未提供"),
        _kv_row("case_id：", str(case_id)),
        _kv_row(transfer_label, transfer_suggestion or "未提供", bold_value=bold_transfer),
        _kv_row("判定摘要：", summary_text or "未提供"),
    ]


def _link_row() -> list[dict]:
    case_list_url = get_mail_settings().case_list_url
    return [{"tag": "a", "text": "👉 点击查看判定详情", "href": case_list_url, "style": ["bold"]}]


def build_survey_reminder_content(
    *,
    case_id: int,
    sample_code: str | None,
    target_species: str | None,
    transfer_suggestion: str | None,
    summary_text: str | None,
) -> str:
    """构造第一次提醒（survey判定完成）的 email_content：完整 post 富文本 JSON 字符串。

    飞书工作流的发送消息节点把 email_content 原样透传给开放平台作为
    消息 content；``msg_type=post`` 时 content 必须是 post 结构的 JSON
    字符串（形如 ``{"zh_cn": {"title": ..., "content": [[...]]}}``），
    否则报 "content is not a string in json format"。

    因此由后端构造完整结构后用 ``json.dumps`` 序列化：结果恒为合法 JSON，
    且作为不透明字符串透传，无换行/引号转义问题。富文本结构使用 text/a/hr
    原生标签（与已验证渲染效果一致的排版）。
    """
    post = {
        "zh_cn": {
            "title": f"【Survey提醒】case_id={case_id} 判定完成，请及时复核",
            "content": [
                [{"tag": "text", "text": "Survey 判定已完成，请及时查看结果并完成人工复核。"}],
                [{"tag": "hr"}],
                *_case_info_rows(
                    case_id=case_id,
                    sample_code=sample_code,
                    target_species=target_species,
                    transfer_label="流转建议：",
                    transfer_suggestion=transfer_suggestion,
                    summary_text=summary_text,
                    bold_transfer=True,
                ),
                [{"tag": "hr"}],
                _link_row(),
            ],
        }
    }
    return json.dumps(post, ensure_ascii=False)


def build_survey_report_content(
    *,
    case_id: int,
    sample_code: str | None,
    target_species: str | None,
    transfer_suggestion: str | None,
    summary_text: str | None,
    reviewer_name: str | None,
    final_decision: str | None,
    note: str | None,
) -> str:
    """构造第二次提醒（人工复核完成）的 email_content：正文版 post 富文本 JSON 字符串。

    与审核邮件并行发送；收件人当前写死（``FEISHU_USER_LIST``），
    调用方不传 user_list 即用默认值。
    """
    decision_display = _FINAL_DECISION_DISPLAY.get(final_decision or "", final_decision or "未提供")
    post = {
        "zh_cn": {
            "title": f"【Survey报告】case_id={case_id} 人工复核完成",
            "content": [
                [{"tag": "text", "text": "人工复核已完成，最终结论如下："}],
                [{"tag": "hr"}],
                _kv_row("复核人：", reviewer_name or "未提供"),
                _kv_row("最终决定：", decision_display, bold_value=True),
                _kv_row("复核备注：", note or "未提供"),
                [{"tag": "hr"}],
                *_case_info_rows(
                    case_id=case_id,
                    sample_code=sample_code,
                    target_species=target_species,
                    transfer_label="AI流转建议：",
                    transfer_suggestion=transfer_suggestion,
                    summary_text=summary_text,
                    bold_transfer=False,
                ),
                [{"tag": "hr"}],
                _link_row(),
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
