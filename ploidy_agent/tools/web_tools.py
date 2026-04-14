from typing import Any, Optional

import requests
from langchain_core.tools import tool


BASE_URL = "https://searchapi.xiaosuai.com"
ACCESS_KEY = "539vFjvr2m7nwK1mvQAU"
SMART_ENDPOINT = "qGFHlZVNYlphTeXO"
FULL_ENDPOINT = "vasXbJMUcNwopLNq"


def _search(query: str, endpoint: str, count: int, with_content: bool) -> str:
    url = f"{BASE_URL}/search/{endpoint}/{'full' if with_content else 'smart'}"
    params = {"q": query, "count": str(count), "safeSearch": "Moderate", "mkt": "zh-CN"}
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        web_pages = data.get("webPages", {}).get("value", [])
        if not web_pages:
            return "未找到相关结果。"

        blocks: list[str] = []
        for idx, page in enumerate(web_pages, start=1):
            title = page.get("name", "N/A")
            page_url = page.get("url", "N/A")
            snippet = page.get("snippet", "")
            text = f"[{idx}] 标题: {title}\nURL: {page_url}\n摘要: {snippet}"
            if with_content:
                content = page.get("content", "")
                if isinstance(content, str) and len(content) > 500:
                    content = content[:500] + "……【内容截断】"
                text += f"\n内容: {content}"
            blocks.append(text)
        return "\n---\n".join(blocks)
    except Exception as exc:  # pragma: no cover - 网络失败时兜底
        return f"搜索失败: {exc}"


@tool
def web_search_summary(query: str, count: Optional[int] = 5) -> str:
    """联网摘要搜索。适合先快速找物种倍性、染色体和是否有多倍体报道。"""
    return _search(query=query, endpoint=SMART_ENDPOINT, count=count or 5, with_content=False)


@tool
def web_search(query: str, count: Optional[int] = 8) -> str:
    """联网全文搜索。适合对争议结论做二次核对并提取更完整上下文。"""
    return _search(query=query, endpoint=FULL_ENDPOINT, count=count or 8, with_content=True)

