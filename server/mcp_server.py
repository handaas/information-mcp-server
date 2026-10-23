"""HandaaS 资讯大数据 MCP 服务。"""

import json
import os
import sys
from hashlib import md5
from typing import Any, Literal
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


load_dotenv()

mcp = FastMCP(
    "资讯热点跟踪",
    instructions=(
        "面向企业简称解析、资讯搜索、企业资讯、行业主题研究和企业舆情动态监控。"
        "搜索类工具复用全域资讯搜索，企业监控工具复用舆情明细或统计接口。"
    ),
    dependencies=["python-dotenv", "requests"],
)

GATEWAY_BASE_URL = "https://console.handaas.com/api/v1/integrator/call_api"
DEFAULT_TIMEOUT_SECONDS = 30.0

PRODUCT_IDS = {
    "enterprise_search": "675cea1f0e009a9ea37edaa1",
    "news_search": "6a60928a935bb6a5c6bbd68f",
    "company_news_details": "66b485eadaf8c77fb249a455",
    "company_news_statistics": "66b338e274bf098447db7efd",
}

KeywordType = Literal["name", "nameId", "regNumber", "socialCreditCode"]
SentimentLabel = Literal["0", "1", "2", "3"]
READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _request_timeout() -> float:
    """读取请求超时配置，非法值回退为默认值。"""
    raw_value = os.environ.get("HANDAAS_REQUEST_TIMEOUT", "")
    try:
        value = float(raw_value) if raw_value else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def _credential(name: str) -> str | None:
    """读取并清理认证配置。"""
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("your_"):
        return None
    return value


def _build_signature(call_params: dict[str, str], secret_key: str) -> str:
    """按 HandaaS Integrator Gateway 规则生成 MD5 签名。"""
    plain_text = "".join(str(call_params[key]) for key in sorted(call_params))
    return md5(f"{plain_text}{secret_key}".encode("utf-8")).hexdigest()


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    """移除未提供的可选参数。"""
    return {key: value for key, value in params.items() if value is not None}


def _pagination_error(page_index: int, page_size: int) -> dict[str, Any] | None:
    """校验 HandaaS 分页公共约束。"""
    if page_index < 1:
        return {"error": "pageIndex 必须大于等于 1", "parameter": "pageIndex"}
    if page_size < 1 or page_size > 50:
        return {
            "error": "pageSize 必须在 1 到 50 之间",
            "parameter": "pageSize",
        }
    return None


def _content_limit_error(content_max_chars: int) -> dict[str, Any] | None:
    """校验资讯正文截断长度。"""
    if content_max_chars < 100 or content_max_chars > 5000:
        return {
            "error": "contentMaxChars 必须在 100 到 5000 之间",
            "parameter": "contentMaxChars",
        }
    return None


def call_api(product_id: str, params: dict[str, Any]) -> Any:
    """
    调用 HandaaS Integrator Gateway，并返回响应中的 data。

    不向调用方泄露密钥、签名、网关响应正文或底层网络异常详情。
    """
    integrator_id = _credential("INTEGRATOR_ID")
    secret_id = _credential("SECRET_ID")
    secret_key = _credential("SECRET_KEY")

    if not integrator_id:
        return {"error": "INTEGRATOR_ID 未配置"}
    if not secret_id:
        return {"error": "SECRET_ID 未配置"}
    if not secret_key:
        return {"error": "SECRET_KEY 未配置"}
    if not product_id:
        return {"error": "Product ID 不能为空"}

    call_params = {
        "product_id": product_id,
        "secret_id": secret_id,
        "params": json.dumps(
            _compact_params(params),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    call_params["signature"] = _build_signature(call_params, secret_key)
    url = f"{GATEWAY_BASE_URL}/{quote(integrator_id, safe='')}"

    try:
        response = requests.post(
            url,
            data=call_params,
            timeout=_request_timeout(),
        )
    except requests.RequestException:
        return {"error": "HandaaS 网关请求失败，请稍后重试"}

    if response.status_code != 200:
        return {
            "error": "HandaaS 网关返回非成功状态",
            "statusCode": response.status_code,
        }

    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return {"error": "HandaaS 网关返回了无法解析的响应"}

    if not isinstance(payload, dict):
        return {"error": "HandaaS 网关返回格式异常"}
    if "data" in payload:
        return payload["data"]

    message = payload.get("msgCN") or payload.get("message") or "HandaaS 网关未返回 data"
    error = {"error": message}
    if payload.get("code") is not None:
        error["code"] = payload["code"]
    return error


def _search_news(
    match_keyword: str,
    pub_date_begin: str | None,
    pub_date_end: str | None,
    page_index: int,
    page_size: int,
    include_content: bool,
    content_max_chars: int,
) -> Any:
    """复用全域资讯搜索 API，并在 MCP 层限制返回页大小。"""
    if error := _pagination_error(page_index, page_size):
        return error
    if include_content and (
        error := _content_limit_error(content_max_chars)
    ):
        return error
    result = call_api(
        PRODUCT_IDS["news_search"],
        {
            "matchKeyword": match_keyword,
            "pubDateBegin": pub_date_begin,
            "pubDateEnd": pub_date_end,
        },
    )
    if not isinstance(result, dict) or "error" in result:
        return result
    result_list = result.get("resultList")
    if not isinstance(result_list, list):
        return result
    total = result.get("total", result.get("dataTotal", len(result_list)))
    start = (page_index - 1) * page_size
    page = []
    for raw_item in result_list[start : start + page_size]:
        if not isinstance(raw_item, dict):
            page.append(raw_item)
            continue
        item = dict(raw_item)
        content = item.get("informationText")
        if not include_content:
            item.pop("informationText", None)
        elif isinstance(content, str) and len(content) > content_max_chars:
            item["informationText"] = content[:content_max_chars]
            item["informationTextTruncated"] = True
        page.append(item)
    return {
        "total": total,
        "resultList": page,
    }


def _company_news_details(
    match_keyword: str,
    keyword_type: KeywordType,
    page_index: int,
    page_size: int,
    sentiment_label: SentimentLabel | None,
) -> Any:
    """复用企业新闻舆情明细 API。"""
    if error := _pagination_error(page_index, page_size):
        return error
    return call_api(
        PRODUCT_IDS["company_news_details"],
        {
            "matchKeyword": match_keyword,
            "keywordType": keyword_type,
            "pageIndex": page_index,
            "pageSize": page_size,
            "sentimentLabel": sentiment_label,
        },
    )


def _company_news_statistics(
    match_keyword: str,
    keyword_type: KeywordType,
) -> Any:
    """复用企业新闻舆情统计 API。"""
    return call_api(
        PRODUCT_IDS["company_news_statistics"],
        {"matchKeyword": match_keyword, "keywordType": keyword_type},
    )


@mcp.tool(title="关键词查询企业", annotations=READ_ONLY_TOOL)
def information_enterprise_search(
    matchKeyword: str,
    pageIndex: int = 1,
    pageSize: int = 10,
) -> dict[str, Any]:
    """
    按企业简称、品牌、产品或其他关键词查询候选企业。

    用户只提供简称时先调用本工具，再将候选企业的全称、企业 ID
    或统一社会信用代码传给企业资讯或动态监控 Tool。

    返回:
    - total: 候选企业总数。
    - resultList: 企业名称、企业 ID、统一社会信用代码及基础信息。
    """
    if error := _pagination_error(pageIndex, pageSize):
        return error
    return call_api(
        PRODUCT_IDS["enterprise_search"],
        {
            "matchKeyword": matchKeyword,
            "pageIndex": pageIndex,
            "pageSize": pageSize,
        },
    )


@mcp.tool(title="资讯全文检索", annotations=READ_ONLY_TOOL)
def information_search(
    matchKeyword: str,
    pubDateBegin: str | None = None,
    pubDateEnd: str | None = None,
    pageIndex: int = 1,
    pageSize: int = 20,
    includeContent: bool = False,
    contentMaxChars: int = 1000,
) -> dict[str, Any]:
    """
    按关键词搜索新闻资讯标题和正文。

    参数:
    - matchKeyword: 搜索关键词。
    - pubDateBegin: 发布时间起始日期。
    - pubDateEnd: 发布时间截止日期。
    - pageIndex: MCP 返回页码，从 1 开始。
    - pageSize: MCP 每页返回数量，最大 50。
    - includeContent: 是否返回资讯正文，默认否；标题、链接、来源和时间始终返回。
    - contentMaxChars: 返回正文时每条最多保留字符数，默认 1000，最大 5000。

    返回:
    - total: 上游匹配结果总数。
    - resultList: 当前页的标题、正文、来源、发布时间和资讯链接。
    """
    return _search_news(
        matchKeyword,
        pubDateBegin,
        pubDateEnd,
        pageIndex,
        pageSize,
        includeContent,
        contentMaxChars,
    )


@mcp.tool(title="企业资讯查询", annotations=READ_ONLY_TOOL)
def information_company_news(
    matchKeyword: str,
    keywordType: KeywordType = "name",
    pageIndex: int = 1,
    pageSize: int = 50,
    sentimentLabel: SentimentLabel | None = None,
) -> dict[str, Any]:
    """
    查询指定企业的新闻舆情明细。

    参数:
    - matchKeyword: 企业名称、企业 ID、注册号或统一社会信用代码。
    - keywordType: matchKeyword 的主体类型。
    - pageIndex/pageSize: 页码和每页数量，pageSize 最大 50。
    - sentimentLabel: 0=负面、1=正面、2=中性、3=未知。

    返回:
    - total: 新闻总数。
    - resultList: 新闻简介、链接、来源、标题、发布时间、相关企业和情感标签。
    """
    return _company_news_details(
        matchKeyword,
        keywordType,
        pageIndex,
        pageSize,
        sentimentLabel,
    )


@mcp.tool(title="行业资讯检索", annotations=READ_ONLY_TOOL)
def information_industry_news(
    matchKeyword: str,
    pubDateBegin: str | None = None,
    pubDateEnd: str | None = None,
    pageIndex: int = 1,
    pageSize: int = 20,
    includeContent: bool = False,
    contentMaxChars: int = 1000,
) -> dict[str, Any]:
    """
    按行业、赛道或产业关键词检索资讯，用于行业研究和市场动态。

    不用于按企业标识查询舆情；企业新闻请使用 information_company_news。
    """
    return _search_news(
        matchKeyword,
        pubDateBegin,
        pubDateEnd,
        pageIndex,
        pageSize,
        includeContent,
        contentMaxChars,
    )


@mcp.tool(title="资讯主题跟踪", annotations=READ_ONLY_TOOL)
def information_topic(
    matchKeyword: str,
    pubDateBegin: str | None = None,
    pubDateEnd: str | None = None,
    pageIndex: int = 1,
    pageSize: int = 20,
    includeContent: bool = False,
    contentMaxChars: int = 1000,
) -> dict[str, Any]:
    """
    跟踪政策、技术、品牌、热点事件等明确主题。

    与 information_industry_news 的区别是本工具聚焦具体主题或事件，
    而不是宽泛行业；日期可限定观察窗口。
    """
    return _search_news(
        matchKeyword,
        pubDateBegin,
        pubDateEnd,
        pageIndex,
        pageSize,
        includeContent,
        contentMaxChars,
    )


@mcp.tool(title="企业资讯动态监控", annotations=READ_ONLY_TOOL)
def information_monitor(
    matchKeyword: str,
    view: Literal["details", "statistics"] = "statistics",
    keywordType: KeywordType = "name",
    pageIndex: int = 1,
    pageSize: int = 50,
    sentimentLabel: SentimentLabel | None = None,
) -> dict[str, Any]:
    """
    监控企业资讯动态，可选择明细或情感趋势统计视图。

    参数:
    - view: details=新闻事件明细；statistics=情感分布与趋势。
    - 其他参数与 information_company_news 相同。

    说明:
    - 单次调用只访问所选视图对应的一个 Product ID，避免隐式双倍调用。
    """
    if view == "details":
        return _company_news_details(
            matchKeyword,
            keywordType,
            pageIndex,
            pageSize,
            sentimentLabel,
        )
    return _company_news_statistics(matchKeyword, keywordType)


def main(argv: list[str] | None = None) -> int:
    """启动 MCP 服务。"""
    arguments = sys.argv[1:] if argv is None else argv
    transport = arguments[0] if arguments else "stdio"
    if transport not in {"stdio", "sse", "streamable-http"}:
        print(
            "启动方式必须是 stdio、sse 或 streamable-http",
            file=sys.stderr,
        )
        return 2
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
