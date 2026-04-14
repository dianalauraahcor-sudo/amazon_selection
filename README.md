# 亚马逊 AI 智能选品分析系统

基于 **LangGraph 工作流 + Excel 数据源 + Kimi LLM**，自动生成专业 DOCX 选品评估报告。

上传卖家精灵 / Jungle Scout 导出的 Excel 文件，输入目标 ASIN 和关键词，系统从 Excel 中检索数据，经 8 节点工作流分析后生成完整选品报告。

## 功能特性

- **多文件上传**：支持产品数据 + 评论数据混合上传，自动识别文件类型并合并
- **智能 Excel 解析**：自动识别卖家精灵中文版/英文版导出格式，统一标准化列名
- **8 节点 LangGraph 工作流**：市场分析、竞争评估、差评挖掘三条分支并行执行，提升效率
- **LLM 深度分析**：痛点提炼、战略洞察生成、差异化上新方向规划
- **专业 DOCX 报告**：带数据溯源标注的结构化报告，标注数据来源和样本量
- **实时进度追踪**：前端轮询展示当前节点和完成百分比
- **单页前端**：文件上传、参数输入、进度展示、结果可视化一体化界面

## 系统架构

```
用户上传 Excel + 输入 ASIN/关键词/利润率
                │
                ▼
        ┌──────────────┐
        │  Excel 解析   │  parser.py — 自动识别文件类型，解析产品/评论数据
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   数据检索    │  crawl.py — 按 ASIN 查找产品，按关键词匹配搜索结果
        └──────┬───────┘
               │
       ┌───────┼───────┐        （并行执行）
       ▼       ▼       ▼
   ┌────────┐┌──────┐┌──────────┐
   │市场分析││竞争  ││差评挖掘  │
   │        ││评估  ││          │
   └───┬────┘└──┬───┘└────┬─────┘
       │        │         │
       ▼        │         │
   ┌────────┐   │         │
   │价格测算│   │         │
   └───┬────┘   │         │
       └────────┼─────────┘
                ▼
        ┌──────────────┐
        │   战略洞察    │  insights.py — LLM 综合所有数据生成战略洞察
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   方向规划    │  directions.py — LLM 生成 3 个差异化上新方向
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  生成报告     │  docx_writer.py — 输出专业 DOCX 选品评估报告
        └──────────────┘
```

## 快速开始

### 环境要求

- Python 3.10+
- Kimi API Key（可选，用于 LLM 分析）

### 安装

```bash
git clone https://github.com/dianalauraahcor-sudo/amazon_selection.git
cd amazon_selection
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env` 填入 API Key：
```
KIMI_API_KEY=你的_moonshot_api_key
```

### 运行

```bash
py -m uvicorn backend.main:app --reload --port 8000
```

或在 Windows 上双击 `run_backend.bat`。

打开 http://localhost:8000 ，上传 Excel 文件 → 输入 ASIN 和关键词 → 启动分析 → 下载 DOCX 报告。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传 Excel 文件（支持多文件），返回文件名列表 |
| POST | `/analyze` | 提交分析任务（ASIN + 关键词 + 文件名），返回 `job_id` |
| GET | `/status/{job_id}` | 查询进度（节点名 + 百分比） |
| GET | `/result/{job_id}` | 获取 JSON 结果 |
| GET | `/report/{job_id}` | 下载 DOCX 报告 |

### POST `/analyze` 请求体示例

```json
{
  "category": "LED work light",
  "asins": ["B088XWTWPM", "B013LDN6BC"],
  "keywords": ["LED work light", "portable light"],
  "target_margin": 0.30,
  "fee_rate": 0.30,
  "excel_filenames": ["abc123_products.xlsx", "def456_reviews.xlsx"]
}
```

## 工作流节点说明

| 节点 | 文件 | 功能 |
|------|------|------|
| **数据检索** | `crawl.py` | 从 Excel 中按 ASIN 查找产品，按关键词在标题/类目中搜索匹配 |
| **市场分析** | `market.py` | 价格分布、市场热度评级、销量带划分、品牌集中度 |
| **竞争评估** | `competition.py` | 竞品评分、月销估算、竞争力矩阵 |
| **价格测算** | `pricing.py` | 建议入场价、成本上限、单件毛利计算 |
| **差评挖掘** | `bad_reviews.py` | LLM 从 1-3 星差评中提炼 TOP10 痛点，含根因分析和改良建议 |
| **战略洞察** | `insights.py` | LLM 综合全部数据生成战略洞察和决策者摘要 |
| **方向规划** | `directions.py` | LLM 生成 3 个差异化上新方向（金/银/铜牌优先级） |
| **生成报告** | `report.py` | 调用 `docx_writer.py` 生成 DOCX 报告 |

## Excel 格式支持

### 产品数据
列头需包含 `ASIN` + (`月销量` 或 `Monthly Sales`) + (`价格` 或 `Price`)，且列数 > 15。

| 中文列头 | 英文列头 | 内部字段名 |
|---------|---------|-----------|
| ASIN | ASIN | asin |
| 品牌 | Brand | brand |
| 商品标题 | Product Title | title |
| 价格($) | Price($) | price |
| 月销量 | Monthly Sales | monthly_sales |
| 月销售额($) | Monthly revenue($) | monthly_revenue |
| 评分数 | Reviews | ratings_total |
| 评分 | Rating | rating |
| 大类BSR | Category BSR | main_bsr |
| 上架时间 | — | launch_date |
| FBA($) | — | fba_fee |
| 毛利率 | — | margin |

### 评论数据
列头需包含 `ASIN` + (`内容` 或 `Content`) + (`星级` 或 `Rating`)。

| 中文列头 | 内部字段名 |
|---------|-----------|
| 内容 | body（评论英文原文） |
| 内容(翻译) | body_cn（中文翻译） |
| 星级 | rating（1-5） |
| VP评论 | verified_purchase |

## 报告结构

| 报告章节 | 数据来源 | 内容 |
|---------|---------|------|
| 封面 | data_stats, warnings | 数据来源说明、数据缺失警告 |
| 一、市场规模 | market 节点 | 关键词维度的价格/销量/热度对比表 |
| 二、竞争指数 | competition 节点 | 竞品矩阵表 + 关键词竞争热度卡片 |
| 三、推荐入场价 | pricing 节点 | 定价建议表（中位价/入场价/成本上限/毛利） |
| 四、差评 TOP10 | bad_reviews 节点 | 痛点表（频次/维度/严重度/原句/建议）+ 根因推断 |
| 五、差评原句摘录 | bad_reviews 节点 | 按关键词分组的原始差评引用 |
| 六、产品上新方向 | directions 节点 | 3 个方向详情（定位/人群/改良点/风险） |
| 综合结论 | directions 节点 | 行动优先级排序表 |

## 项目结构

```
amazon_selection/
├── backend/
│   ├── main.py                  # FastAPI 入口（/upload + /analyze + /status + /result + /report）
│   ├── jobs.py                  # 后台任务管理（Excel 解析 + 工作流调度）
│   ├── schemas.py               # Pydantic 请求/响应模型
│   ├── llm.py                   # Kimi (Moonshot) LLM 客户端（OpenAI 兼容接口）
│   ├── excel_parser/
│   │   ├── parser.py            # Excel 智能解析（文件类型识别 + 列名标准化 + 产品/评论提取）
│   │   └── schemas.py           # Excel 字段定义
│   ├── graph/
│   │   ├── state.py             # GraphState 类型定义
│   │   ├── workflow.py          # LangGraph StateGraph（8 节点，含并行分支）
│   │   └── nodes/
│   │       ├── crawl.py         # 数据检索（从 Excel 按 ASIN/关键词查找）
│   │       ├── market.py        # 市场分析（价格分布、热度、销量带）
│   │       ├── competition.py   # 竞争评估（竞品评分、月销、竞争力矩阵）
│   │       ├── pricing.py       # 价格测算（入场价、成本上限、毛利）
│   │       ├── bad_reviews.py   # 差评挖掘（LLM 提炼 TOP10 痛点）
│   │       ├── insights.py      # 战略洞察（LLM 综合分析）
│   │       ├── directions.py    # 方向规划（LLM 生成 3 个上新方向）
│   │       └── report.py        # 报告生成入口
│   └── report/
│       ├── docx_writer.py       # DOCX 报告生成（专业样式 + 数据溯源标注）
│       ├── analytics.py         # 纯数据分析（无 LLM 调用，基于 Excel 数据聚合）
│       └── output/              # 生成的报告存放目录
├── web/
│   └── index.html               # 单页前端（文件上传 + 参数输入 + 进度展示 + 结果可视化）
├── uploads/                     # 上传文件临时存放
├── tests/
│   └── test_product_schema.py
├── requirements.txt
├── .env.example
└── run_backend.bat
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 工作流引擎 | LangGraph（StateGraph + 并行条件边） |
| LLM | Kimi / Moonshot API（OpenAI 兼容接口） |
| Excel 解析 | openpyxl（只读模式） |
| 报告生成 | python-docx |
| 前端 | 原生 HTML + Tailwind CSS（单文件） |

## 备注

- 没有 `KIMI_API_KEY` 时，差评 TOP10 与上新方向会退化为基于关键词频次的模板输出
- 所有分析数据 100% 来自用户上传的 Excel，不调用任何外部数据 API
- 报告中明确标注数据来源和样本量，无数据时标注"无评论数据"而非虚构
- 报告输出目录：`backend/report/output/`
