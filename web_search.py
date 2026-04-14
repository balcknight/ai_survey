import requests
from typing import Optional

from langchain_core.tools import tool


@tool
def web_search_summary(query: str, count: Optional[int] = 3) -> str:
    """
    使用 Cloudsway SmartSearch 进行实时网页摘要搜索。
    
    Args:
        query: 搜索查询词（必填，例如 "最新 AI 新闻"）。
        count: 返回结果数量（默认 3）。
    Returns:
        格式化的搜索结果文本，便于 LLM 解析。
    """
    base_url = "https://searchapi.xiaosuai.com"
    access_key = "539vFjvr2m7nwK1mvQAU" 

    endpoint_path = "qGFHlZVNYlphTeXO"  # 国内智能
    url = f"{base_url}/search/{endpoint_path}/smart"

    params = {
        "q": query,
        "count": str(count),
        "safeSearch": "Moderate",
        "mkt": "zh-CN"  
    }
    headers = {
        "Authorization": f"Bearer {access_key}",
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            web_pages = data.get("webPages", {}).get("value", [])
            results = []
            for page in web_pages:
                title = page.get("name", "N/A")
                url = page.get("url", "N/A")
                snippet = page.get("snippet", "N/A")[:]
                results.append(f"标题: {title}\nURL: {url}\n摘要: {snippet}\n---")
            return "\n".join(results) if results else "未找到相关结果。"
        else:
            return f"搜索失败: {response.status_code} - {response.text}"
    except Exception as e:
        return f"工具调用错误: {str(e)}"



@tool
def web_search(query: str) -> str:
    """
    使用 Cloudsway SmartSearch 进行实时网页搜索，获取相关信息。
    返回网页搜索结果的标题、URL、摘要。
    
    Args:
        query: 需要搜索的内容，例如"中国2015年-2020年的GDP数据"
    
    Returns:
        格式化的搜索结果文本，包含标题、URL、摘要和内容
    """
    count = 10
    base_url = "https://searchapi.xiaosuai.com"
    access_key = "539vFjvr2m7nwK1mvQAU" 
    
    endpoint_path = "vasXbJMUcNwopLNq"  # 国内全文
    url = f"{base_url}/search/{endpoint_path}/full"
    params = {
        "q": query,
        "count": str(count),
        "safeSearch": "Moderate",
        "mkt": "zh-CN"  
    }
    headers = {
        "Authorization": f"Bearer {access_key}",
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            web_pages = data.get("webPages", {}).get("value", [])
            results = []
            for page in web_pages:
                title = page.get("name", "N/A")
                url = page.get("url", "N/A")
                snippet = page.get("snippet", "N/A")
                content = page.get("content", "N/A")
                # 如果内容太长，只取前 500 字并加省略号
                if isinstance(content, str) and len(content) > 500:
                    content = content[:500] + "……【内容已截断】"
                results.append(f"标题: {title}\nURL: {url}\n摘要: {snippet}\n内容: {content}\n---")
            return "\n".join(results) if results else "未找到相关结果。"
        else:
            return f"搜索失败: {response.status_code} - {response.text}"
    except Exception as e:
        return f"搜索失败: {str(e)}"