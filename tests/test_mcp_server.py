"""资讯大数据 MCP 服务离线测试。"""

import asyncio
import importlib.util
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


SERVER_PATH = Path(__file__).parents[1] / "server" / "mcp_server.py"
SPEC = importlib.util.spec_from_file_location("information_mcp_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class GatewayTests(TestCase):
    def test_missing_credentials_prevents_http_request(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(server.requests, "post") as post,
        ):
            result = server.call_api("product", {})
        self.assertEqual(result, {"error": "INTEGRATOR_ID 未配置"})
        post.assert_not_called()

    def test_gateway_message_becomes_actionable_error(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"code": 400, "msgCN": "参数错误"}
        credentials = {
            "INTEGRATOR_ID": "integrator",
            "SECRET_ID": "secret-id",
            "SECRET_KEY": "secret-key",
        }
        with (
            patch.dict(os.environ, credentials, clear=True),
            patch.object(server.requests, "post", return_value=response),
        ):
            result = server.call_api("product", {})
        self.assertEqual(result, {"error": "参数错误", "code": 400})


class ToolTests(TestCase):
    def test_registered_tool_names(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {
                "information_search",
                "information_company_news",
                "information_industry_news",
                "information_topic",
                "information_monitor",
            },
        )
        for tool in tools:
            self.assertEqual(tool.outputSchema.get("type"), "object")
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)

    def test_search_scene_tools_reuse_news_search(self) -> None:
        for function in (
            server.information_search,
            server.information_industry_news,
            server.information_topic,
        ):
            with self.subTest(function=function.__name__):
                upstream = {
                    "resultList": [{"index": index} for index in range(45)]
                }
                with patch.object(
                    server,
                    "call_api",
                    return_value=upstream,
                ) as call:
                    result = function(
                        "人工智能",
                        pubDateBegin="2026-01-01",
                        pageIndex=2,
                        pageSize=20,
                    )
                self.assertEqual(result["total"], 45)
                self.assertEqual(
                    result["resultList"],
                    [{"index": index} for index in range(20, 40)],
                )
                call.assert_called_once_with(
                    server.PRODUCT_IDS["news_search"],
                    {
                        "matchKeyword": "人工智能",
                        "pubDateBegin": "2026-01-01",
                        "pubDateEnd": None,
                    },
                )

    def test_search_pagination_validation(self) -> None:
        with patch.object(server, "call_api") as call:
            result = server.information_search("人工智能", pageSize=51)
        self.assertEqual(result["parameter"], "pageSize")
        call.assert_not_called()

    def test_search_content_is_opt_in_and_bounded(self) -> None:
        upstream = {
            "resultList": [
                {
                    "informationTitle": "标题",
                    "informationText": "正文" * 1000,
                }
            ]
        }
        with patch.object(server, "call_api", return_value=upstream):
            compact = server.information_search("主题", pageSize=1)
        self.assertNotIn("informationText", compact["resultList"][0])

        with patch.object(server, "call_api", return_value=upstream):
            detailed = server.information_search(
                "主题",
                pageSize=1,
                includeContent=True,
                contentMaxChars=100,
            )
        item = detailed["resultList"][0]
        self.assertEqual(len(item["informationText"]), 100)
        self.assertTrue(item["informationTextTruncated"])

        with patch.object(server, "call_api") as call:
            invalid = server.information_search(
                "主题",
                includeContent=True,
                contentMaxChars=99,
            )
        self.assertEqual(invalid["parameter"], "contentMaxChars")
        call.assert_not_called()

    def test_company_news_maps_detail_parameters(self) -> None:
        with patch.object(server, "call_api", return_value={}) as call:
            server.information_company_news(
                "企业A",
                sentimentLabel="0",
            )
        call.assert_called_once_with(
            server.PRODUCT_IDS["company_news_details"],
            {
                "matchKeyword": "企业A",
                "keywordType": "name",
                "pageIndex": 1,
                "pageSize": 50,
                "sentimentLabel": "0",
            },
        )

    def test_monitor_selects_one_view(self) -> None:
        with patch.object(server, "call_api", return_value={}) as call:
            server.information_monitor("企业A")
        call.assert_called_once_with(
            server.PRODUCT_IDS["company_news_statistics"],
            {"matchKeyword": "企业A", "keywordType": "name"},
        )

        with patch.object(server, "call_api", return_value={}) as call:
            server.information_monitor("企业A", view="details")
        call.assert_called_once_with(
            server.PRODUCT_IDS["company_news_details"],
            {
                "matchKeyword": "企业A",
                "keywordType": "name",
                "pageIndex": 1,
                "pageSize": 50,
                "sentimentLabel": None,
            },
        )

    def test_pagination_validation(self) -> None:
        with patch.object(server, "call_api") as call:
            result = server.information_company_news("企业A", pageSize=100)
        self.assertEqual(result["parameter"], "pageSize")
        call.assert_not_called()
