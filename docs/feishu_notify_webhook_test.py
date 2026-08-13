"""飞书提醒 Webhook 测试脚本

POST https://ocnz4cb25scn.feishu.cn/ai/api/v1/skill_runtime/namespaces/spring_3bd562b8e3__c/trigger/g34g1xsq
"""

import json
from typing import Any, Dict

import requests

WEBHOOK_URL = (
    "https://ocnz4cb25scn.feishu.cn/ai/api/v1/skill_runtime/"
    "namespaces/spring_3bd562b8e3__c/trigger/g34g1xsq"
)
BEARER_TOKEN = "0.nlyb8zaaqwb"

USER_LIST = "zhurui8901@novogene.com"
# 与后端 build_survey_reminder_content() 生成格式一致：
# 完整的 post 富文本 JSON 字符串（发送节点要求 content 为 JSON 格式字符串，
# 工作流对 email_content 原样透传，故由发送方构造完整结构）
EMAIL_CONTENT = json.dumps(
    {
        "zh_cn": {
            "title": "【Survey提醒】case_id=123 判定完成，请及时复核",
            "content": [
                [{"tag": "text", "text": "Survey 判定已完成，请及时查看结果并完成人工复核。"}],
                [{"tag": "hr"}],
                [
                    {"tag": "text", "text": "样本编号：", "style": ["bold"]},
                    {"tag": "text", "text": "TS_20260812_001"},
                ],
                [
                    {"tag": "text", "text": "目标物种：", "style": ["bold"]},
                    {"tag": "text", "text": "水稻"},
                ],
                [
                    {"tag": "text", "text": "case_id：", "style": ["bold"]},
                    {"tag": "text", "text": "123"},
                ],
                [
                    {"tag": "text", "text": "流转建议：", "style": ["bold"]},
                    {"tag": "text", "text": "建议流转", "style": ["bold"]},
                ],
                [
                    {"tag": "text", "text": "判定摘要：", "style": ["bold"]},
                    {
                        "tag": "text",
                        "text": "采用kmer 21进行Survey分析，预估得到: 矫正后基因组大小为380.5Mbp，杂合率为1.20%，重复序列比例为15.30%。",
                    },
                ],
                [{"tag": "hr"}],
                [
                    {"tag": "a", "text": "👉 点击查看判定详情", "href": "http://10.11.0.6:5173/cases", "style": ["bold"]},
                ],
            ],
        }
    },
    ensure_ascii=False,
)


def call_webhook(url: str, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    result: Dict[str, Any] = {"status_code": resp.status_code}
    try:
        result["body"] = resp.json()
    except ValueError:
        result["body"] = resp.text
    return result


def main() -> None:
    payload = {
        "user_list": USER_LIST,
        "email_content": EMAIL_CONTENT,
    }
    result = call_webhook(WEBHOOK_URL, BEARER_TOKEN, payload)
    print(f"HTTP {result['status_code']}")
    print(json.dumps(result["body"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
