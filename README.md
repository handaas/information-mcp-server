# 资讯大数据服务

[该 MCP 服务提供全域资讯搜索、企业资讯、行业资讯、主题跟踪和企业动态监控能力，帮助用户开展行业研究、热点追踪、企业舆情和品牌声誉管理。](https://www.handaas.com/)

## 主要功能

- 🔍 全域资讯关键词检索
- 🏢 企业新闻舆情查询
- 🏭 行业与赛道资讯检索
- 🎯 政策、技术、品牌和事件主题跟踪
- 📊 企业资讯明细与情感统计监控

## 服务设计说明

- 服务按实际业务场景提供 5 个 Tool，不按上游 API 数量平铺工具。
- 搜索、行业和主题 Tool 复用同一个全域资讯搜索 Product ID，但保留不同场景语义。
- 上游资讯搜索结果由 MCP 层通过 `pageIndex` 和 `pageSize` 分页，默认每页 20 条，最大 50 条。
- 搜索结果默认不返回长正文；设置 `includeContent=true` 后，可通过 `contentMaxChars` 限制每条正文长度。
- `information_monitor` 通过 `view` 选择明细或统计，单次只访问一个 Product ID。
- 所有翻页响应的业务外层只包含 `total` 与 `resultList`。

## 环境要求

- Python 3.10+
- 依赖包：python-dotenv、requests、mcp

## 本地快速启动

### 1. 进入项目目录

```bash
cd information-mcp-server
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv mcp_env
source mcp_env/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
INTEGRATOR_ID=your_integrator_id
SECRET_ID=your_secret_id
SECRET_KEY=your_secret_key
HANDAAS_REQUEST_TIMEOUT=30
```

`HANDAAS_REQUEST_TIMEOUT` 为可选配置，单位为秒，默认值为 30。

### 4. 启动 Streamable HTTP 服务

```bash
python server/mcp_server.py streamable-http
```

服务默认地址为 `http://localhost:8000/mcp`。

也可以使用启动脚本：

```bash
./start_mcp_server.sh streamable-http
```

支持 `stdio`、`sse` 和 `streamable-http` 三种启动方式。

### 5. Cursor / Cherry Studio MCP 配置

```json
{
  "mcpServers": {
    "information-mcp-server": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## STDIO 版安装部署

将 `{workdir}` 替换为 `information-mcp-server` 的绝对路径：

```json
{
  "mcpServers": {
    "information-mcp-server": {
      "command": "{workdir}/mcp_env/bin/python",
      "args": [
        "{workdir}/server/mcp_server.py",
        "stdio"
      ]
    }
  }
}
```

`INTEGRATOR_ID`、`SECRET_ID` 和 `SECRET_KEY` 需要登录 [HandaaS](https://www.handaas.com/) 注册并开通对接器后获取。真实凭据只应保存在本地 `.env` 或部署密钥中。

## 可用工具与 Product ID

| MCP Tool | 功能或视图 | Product ID |
|---|---|---|
| `information_search` | 全域资讯关键词与日期检索 | `6a60928a935bb6a5c6bbd68f` |
| `information_company_news` | 企业新闻舆情明细 | `66b485eadaf8c77fb249a455` |
| `information_industry_news` | 行业或赛道资讯检索 | `6a60928a935bb6a5c6bbd68f` |
| `information_topic` | 政策、技术、品牌或事件主题跟踪 | `6a60928a935bb6a5c6bbd68f` |
| `information_monitor` | `view=details` 企业资讯明细 | `66b485eadaf8c77fb249a455` |
| `information_monitor` | `view=statistics` 企业资讯情感统计 | `66b338e274bf098447db7efd` |

### 1. information_search

**功能**：按关键词搜索新闻资讯标题和正文。

**主要参数**：

- `matchKeyword`（必需）：搜索关键词。
- `pubDateBegin`、`pubDateEnd`（可选）：发布时间起始和截止条件。
- `pageIndex`（可选）：MCP 返回页码，从 1 开始。
- `pageSize`（可选）：每页数量，默认 20，最大 50。
- `includeContent`（可选）：是否返回资讯正文，默认 `false`。
- `contentMaxChars`（可选）：返回正文时每条最多保留的字符数，默认 1000，范围为 100–5000。

**返回**：`total` 和 `resultList`；结果可包含标题、来源、发布时间、资讯链接和按需截断的正文。

### 2. information_company_news

**功能**：查询指定企业的新闻舆情明细。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `keywordType`（可选）：企业标识类型，支持 `name`、`nameId`、`regNumber`、`socialCreditCode`。
- `pageIndex`（可选）：页码，从 1 开始。
- `pageSize`（可选）：每页数量，默认 50，最大 50。
- `sentimentLabel`（可选）：`0` 负面、`1` 正面、`2` 中性、`3` 未知。

**返回**：`total` 和 `resultList`；结果可包含新闻简介、链接、来源、标题、发布时间、相关企业和情感标签。

### 3. information_industry_news

**功能**：按行业、赛道或产业关键词检索资讯，用于行业研究和市场动态分析。

**主要参数**：

- `matchKeyword`（必需）：行业、赛道或产业关键词。
- `pubDateBegin`、`pubDateEnd`（可选）：发布时间范围。
- `pageIndex`、`pageSize`（可选）：页码和每页数量，`pageSize` 最大为 50。
- `includeContent`、`contentMaxChars`（可选）：正文返回开关和正文长度上限。

**返回**：`total` 和 `resultList`。

### 4. information_topic

**功能**：跟踪政策、技术、品牌或热点事件等明确主题。

**主要参数**：

- `matchKeyword`（必需）：具体主题或事件关键词。
- `pubDateBegin`、`pubDateEnd`（可选）：主题观察时间范围。
- `pageIndex`、`pageSize`（可选）：页码和每页数量，`pageSize` 最大为 50。
- `includeContent`、`contentMaxChars`（可选）：正文返回开关和正文长度上限。

**返回**：`total` 和 `resultList`。

### 5. information_monitor

**功能**：监控企业资讯动态，可选择新闻事件明细或情感统计视图。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `view`（可选）：`details` 新闻事件明细；`statistics` 情感分布和趋势。默认 `statistics`。
- `keywordType`（可选）：企业标识类型。
- `pageIndex`、`pageSize`（可选）：仅 `details` 视图使用，`pageSize` 最大为 50。
- `sentimentLabel`（可选）：仅 `details` 视图使用的情感筛选。

**返回**：明细视图返回 `total` 和 `resultList`；统计视图返回情感分布和趋势业务字段。

## 使用场景

1. **资讯检索**：按关键词聚合全域新闻标题、来源、时间和链接。
2. **行业研究**：跟踪行业、赛道和产业相关动态。
3. **主题跟踪**：持续观察政策、技术、品牌和热点事件。
4. **企业舆情**：查询企业相关新闻并按情感类别筛选。
5. **动态监控**：分析企业资讯情感分布和变化趋势。
6. **品牌声誉管理**：结合新闻明细和情感统计识别声誉风险。

## 使用注意事项

1. **场景选择**：企业舆情使用 `information_company_news` 或 `information_monitor`；行业研究使用 `information_industry_news`。
2. **分页限制**：`pageIndex` 从 1 开始，`pageSize` 必须在 1 到 50 之间。
3. **正文控制**：默认不返回 `informationText`；需要正文时显式设置 `includeContent=true`。
4. **正文长度**：`contentMaxChars` 必须在 100 到 5000 之间。
5. **情感标签**：`0` 表示负面、`1` 表示正面、`2` 表示中性、`3` 表示未知。
6. **合法空结果**：关键词、时间或情感条件无匹配时可能返回 `total=0` 和空 `resultList`。

## 使用提问示例

### information_search（资讯全文检索）

1. 搜索人工智能相关新闻，只看标题和来源。
2. 搜索新能源汽车资讯，并返回两条短正文。

### information_company_news（企业资讯查询）

1. 查询小米科技有限责任公司最近的企业新闻。
2. 查看珠海格力电器股份有限公司的负面舆情。

### information_industry_news（行业资讯检索）

1. 检索低空经济行业的最新资讯。
2. 人形机器人赛道最近有哪些行业动态？

### information_topic（资讯主题跟踪）

1. 持续跟踪人工智能大模型这一技术主题。
2. 跟踪消费品以旧换新政策相关事件。

### information_monitor（企业资讯动态监控）

1. 监控小米科技有限责任公司的舆情情感分布和趋势。
2. 查看北京京东世纪贸易有限公司的最新资讯事件明细。

## 测试验证

```bash
python -m py_compile server/mcp_server.py
python -m unittest discover -s tests -v
```

单元测试使用 Mock HTTP 响应，不调用真实 HandaaS 资讯接口。
