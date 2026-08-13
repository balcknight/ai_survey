import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_WEBHOOK_URL = (
    "https://ocnz4cb25scn.feishu.cn/ai/api/v1/skill_runtime/"
    "namespaces/spring_5c4971530f__c/trigger/unl78lr8"
)
DEFAULT_BEARER_TOKEN = "0.koy0sn65xnm"
DEFAULT_USER_ACCESS_TOKEN = "请填写你的user_access_token"
DEFAULT_USER_REFRESH_TOKEN = "请填写你的user_refresh_token"
DEFAULT_APP_ID = "请填写你的app_id"
DEFAULT_APP_SECRET = "请填写你的app_secret"
DEFAULT_EXPORT_EXT = "pdf"  # 可选: "pdf" / "docx"

WEBHOOK_URL = DEFAULT_WEBHOOK_URL
BEARER_TOKEN = DEFAULT_BEARER_TOKEN
QUERY = "检索内容"
ENABLE_ENRICH_DOWNLOAD_LINK = True
EXPORT_EXT = DEFAULT_EXPORT_EXT
AUTO_REFRESH_USER_TOKEN = True
USER_ACCESS_TOKEN = DEFAULT_USER_ACCESS_TOKEN
USER_REFRESH_TOKEN = DEFAULT_USER_REFRESH_TOKEN
APP_ID = DEFAULT_APP_ID
APP_SECRET = DEFAULT_APP_SECRET

ONLINE_TYPES = {"docx", "doc", "sheet", "bitable"}
FILE_TYPES = {"file"}
POLL_INTERVAL_SEC = 1.5
POLL_MAX_TIMES = 80

TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
USER_REFRESH_URL = "https://open.feishu.cn/open-apis/authen/v1/refresh_access_token"


def call_webhook(url: str, token: str, query: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"query": query}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    result: Dict[str, Any] = {"status_code": resp.status_code}
    try:
        result["body"] = resp.json()
    except ValueError:
        result["body"] = resp.text
    return result


def webhook_is_success(result: Dict[str, Any]) -> bool:
    if result.get("status_code") != 200:
        return False
    body = result.get("body")
    if not isinstance(body, dict):
        return False
    return str(body.get("status_code")) == "0"


def extract_node_token_from_link(link: str) -> str:
    m = re.search(r"/wiki/([A-Za-z0-9]+)", link)
    if not m:
        raise ValueError(f"无法从链接解析 wiki token: {link}")
    return m.group(1)


def build_lark_client():
    import lark_oapi as lark

    return (
        lark.Client.builder()
        .enable_set_token(True)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


def build_option(user_access_token: str):
    import lark_oapi as lark

    return lark.RequestOption.builder().user_access_token(user_access_token).build()


def get_wiki_node_obj(client, user_access_token: str, node_token: str) -> Dict[str, str]:
    from lark_oapi.api.wiki.v2 import GetNodeSpaceRequest

    req = GetNodeSpaceRequest.builder().token(node_token).obj_type("wiki").build()
    resp = client.wiki.v2.space.get_node(req, build_option(user_access_token))
    if not resp.success():
        raise RuntimeError(f"wiki.get_node 失败: code={resp.code}, msg={resp.msg}")
    node = resp.data.node
    return {
        "obj_token": node.obj_token,
        "obj_type": node.obj_type,
        "title": node.title or "untitled",
    }


def create_export_task(client, user_access_token: str, obj_token: str, obj_type: str, ext: str):
    from lark_oapi.api.drive.v1 import CreateExportTaskRequest, ExportTask

    req = (
        CreateExportTaskRequest.builder()
        .request_body(
            ExportTask.builder()
            .token(obj_token)
            .type(obj_type)
            .file_extension(ext)
            .build()
        )
        .build()
    )
    return client.drive.v1.export_task.create(req, build_option(user_access_token))


def wait_export_ready(client, user_access_token: str, ticket: str, token: str) -> str:
    from lark_oapi.api.drive.v1 import GetExportTaskRequest

    for _ in range(POLL_MAX_TIMES):
        req = GetExportTaskRequest.builder().ticket(ticket).token(token).build()
        resp = client.drive.v1.export_task.get(req, build_option(user_access_token))
        if not resp.success():
            raise RuntimeError(f"export_task.get 失败: code={resp.code}, msg={resp.msg}")
        job = resp.data.result
        if job.job_status == 1:
            time.sleep(POLL_INTERVAL_SEC)
            continue
        if job.job_status == 0:
            return job.file_token
        raise RuntimeError(f"导出失败: status={job.job_status}, err={job.job_error_msg}")
    raise TimeoutError("导出任务超时")


def inspect_redirect_location(url: str, headers: Dict[str, str], timeout: int = 60) -> Dict[str, str]:
    pre = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
    out: Dict[str, str] = {
        "api_url": url,
        "status_code": str(pre.status_code),
        "temp_url": "",
        "shareable_temp_url": "",
    }
    location = pre.headers.get("Location", "")
    if location:
        out["temp_url"] = location
        out["shareable_temp_url"] = location
        exp = re.search(r"(?:X-Amz-Expires|Expires)=([0-9]+)", location)
        if exp:
            out["temp_url_ttl_seconds"] = exp.group(1)
        return out

    # 某些场景不会在 302 Location 中返回，而是由服务端流程直接跟随跳转。
    # 这里做一次轻量探测，尽量提取最终可分享临时链接。
    probe = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
    try:
        final_url = probe.url or ""
        out["final_url_after_follow"] = final_url
        out["redirect_hops"] = str(len(probe.history))
        if final_url and final_url != url:
            out["temp_url"] = final_url
            out["shareable_temp_url"] = final_url
            exp = re.search(r"(?:X-Amz-Expires|Expires)=([0-9]+)", final_url)
            if exp:
                out["temp_url_ttl_seconds"] = exp.group(1)
        else:
            out["temp_url_unavailable_reason"] = (
                "未观察到可提取的重定向临时链接；该下载入口仍需携带 Authorization 才可访问"
            )
    finally:
        probe.close()
    return out


def resolve_download_link_from_wiki_link(
    wiki_link: str,
    user_access_token: str,
    export_ext: str,
) -> Dict[str, str]:
    client = build_lark_client()
    node_token = extract_node_token_from_link(wiki_link)
    obj = get_wiki_node_obj(client, user_access_token, node_token)
    obj_token, obj_type, title = obj["obj_token"], obj["obj_type"], obj["title"]

    common_headers = {"Authorization": f"Bearer {user_access_token}"}
    if obj_type in ONLINE_TYPES:
        create_resp = create_export_task(client, user_access_token, obj_token, obj_type, export_ext)
        if not create_resp.success():
            raise RuntimeError(f"export_task.create 失败: code={create_resp.code}, msg={create_resp.msg}")
        ticket = create_resp.data.ticket
        file_token = wait_export_ready(client, user_access_token, ticket, obj_token)
        download_url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks/file/{file_token}/download"
    elif obj_type in FILE_TYPES:
        download_url = f"https://open.feishu.cn/open-apis/drive/v1/files/{obj_token}/download"
    else:
        raise RuntimeError(f"暂不支持转换 obj_type={obj_type}")

    link_data = inspect_redirect_location(download_url, common_headers)
    link_data.update(
        {
            "obj_type": obj_type,
            "obj_token": obj_token,
            "title": title,
            "wiki_link": wiki_link,
        }
    )
    return link_data


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        TENANT_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        raise RuntimeError(
            f"获取 tenant_access_token 失败: code={data.get('code')} msg={data.get('msg')}"
        )
    return data["tenant_access_token"]


def refresh_user_access_token(tenant_access_token: str, user_refresh_token: str) -> str:
    headers = {
        "Authorization": f"Bearer {tenant_access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post(
        USER_REFRESH_URL,
        headers=headers,
        json={"refresh_token": user_refresh_token},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"刷新 user_access_token 失败: code={data.get('code')} msg={data.get('msg')}"
        )
    token = data.get("data", {}).get("access_token")
    if not token:
        raise RuntimeError("刷新 user_access_token 失败: 响应中缺少 data.access_token")
    return token


def extract_recall_items(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = body.get("data", {}).get("data", {}).get("data")
    if not isinstance(items, list):
        return []
    return items


def enrich_item_with_download_link(
    item: Dict[str, Any],
    user_access_token: str,
    export_ext: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    copied = dict(item)
    link = copied.get("sourceValue", {}).get("meta", {}).get("link", "")
    if not link or "/wiki/" not in link:
        copied["downloadLink"] = {"error": "no_wiki_link"}
        return copied, None
    info = resolve_download_link_from_wiki_link(
        wiki_link=link,
        user_access_token=user_access_token,
        export_ext=export_ext,
    )
    copied["downloadLink"] = info
    return copied, None


def enrich_with_retry(items: List[Dict[str, Any]], user_access_token: str, export_ext: str) -> Tuple[List[Dict[str, Any]], str]:
    enriched: List[Dict[str, Any]] = []
    current_token = user_access_token
    refreshed = False
    for item in items:
        try:
            new_item, _ = enrich_item_with_download_link(item, current_token, export_ext)
            enriched.append(new_item)
            continue
        except Exception as e:
            if refreshed or not AUTO_REFRESH_USER_TOKEN:
                item_copy = dict(item)
                item_copy["downloadLink"] = {"error": str(e)}
                enriched.append(item_copy)
                continue

            if (
                not APP_ID.strip()
                or not APP_SECRET.strip()
                or not USER_REFRESH_TOKEN.strip()
                or APP_ID.startswith("请填写")
                or APP_SECRET.startswith("请填写")
                or USER_REFRESH_TOKEN.startswith("请填写")
            ):
                item_copy = dict(item)
                item_copy["downloadLink"] = {"error": f"{e}; 且无法自动刷新token(脚本顶部缺少 APP_ID/APP_SECRET/USER_REFRESH_TOKEN)"}
                enriched.append(item_copy)
                continue

            tenant_token = get_tenant_access_token(APP_ID, APP_SECRET)
            current_token = refresh_user_access_token(tenant_token, USER_REFRESH_TOKEN)
            refreshed = True
            try:
                new_item, _ = enrich_item_with_download_link(item, current_token, export_ext)
                enriched.append(new_item)
            except Exception as e2:
                item_copy = dict(item)
                item_copy["downloadLink"] = {"error": f"刷新后重试仍失败: {e2}"}
                enriched.append(item_copy)

    return enriched, current_token


def main() -> None:
    result = call_webhook(WEBHOOK_URL, BEARER_TOKEN, QUERY)
    print(f"HTTP {result['status_code']}")

    body = result.get("body")
    if isinstance(body, dict) and ENABLE_ENRICH_DOWNLOAD_LINK and webhook_is_success(result):
        if not USER_ACCESS_TOKEN.strip() or USER_ACCESS_TOKEN.startswith("请填写"):
            body["download_link_enrich_error"] = "缺少 USER_ACCESS_TOKEN（请在脚本顶部填写）"
        else:
            items = extract_recall_items(body)
            enriched_items, latest_user_token = enrich_with_retry(items, USER_ACCESS_TOKEN, EXPORT_EXT)
            body["data"]["data"]["data"] = enriched_items
            if latest_user_token != USER_ACCESS_TOKEN:
                body["token_refresh"] = {
                    "refreshed": True,
                    "new_user_access_token_prefix": latest_user_token[:12],
                }
            else:
                body["token_refresh"] = {"refreshed": False}

    print(json.dumps(result["body"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
