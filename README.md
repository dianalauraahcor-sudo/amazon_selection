# 亚马逊 AI 智能选品分析系统

基于 LangGraph 工作流 + Excel 数据源 + Kimi LLM，自动生成 DOCX 选品评估报告。

## 系统架构

用户上传卖家精灵/Jungle Scout 导出的 Excel 文件作为数据库，输入目标 ASIN 和关键词，系统从 Excel 中检索数据，经 7 节点工作流分析后生成选品报告。

```
用户上传 Excel（数据库）+ 输入 ASIN/关键词/利润率
        │
        ▼
  ┌─────────────┐
  │  Excel 解析  │  parser.py: 自动识别文件类型，解析产品数据和评论数据
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  数据检索    │  crawl.py: 按 ASIN 查找产品，按关键词匹配搜索结果
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  市场分析    │  market.py: 价格分布、热度评级、销量带、品牌集中度
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  竞争评估    │  competition.py: 竞品评分、月销估算、竞争力矩阵
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  价格测算    │  pricing.py: 入场价、成本上限、单件毛利
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  差评挖掘    │  bad_reviews.py: LLM 提炼 TOP10 痛点（需要评论数据）
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  方向规划    │  directions.py: LLM 生成 3 个差异化上新方向
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  生成报告    │  docx_writer.py: 输出 DOCX 选品评估报告
  └─────────────┘
```

---

## Excel 解析机制

### 文件类型自动识别

系统通过检查每个 sheet 的列头关键词自动判断文件类型，无需用户手动指定：

| 文件类型 | 识别规则 | 示例文件 |
|---------|---------|---------|
| **产品数据** | 列头含 `ASIN` + (`月销量` 或 `Monthly Sales`) + (`价格` 或 `Price`) 且列数 > 15 | `BSR(Job-Site-Lighting)-100.xlsx`、`割草机-市场分析.xlsx` |
| **评论数据** | 列头含 `ASIN` + (`内容` 或 `Content`) + (`星级` 或 `Rating`)，且不含 `月销量` | `B0CYWSWZ71-US-Reviews-20260409.xlsx` |
| **跳过** | sheet 名为 `Note`、`说明`、`Brands`、`Sellers`，或不满足以上规则 | 卖家精灵的说明页、品牌/卖家汇总页 |

### 列名标准化

支持卖家精灵中文版和英文版两种导出格式，通过映射表统一为内部字段名：

```
中文列头                    英文列头                    内部字段名
─────────────────────────────────────────────────────────────────
ASIN                       ASIN                       asin
品牌                       Brand                      brand
商品标题                    Product Title              title
产品卖点                    Bullet Points              bullet_points
价格($)                    Price($)                   price
月销量                      Monthly Sales              monthly_sales
月销售额($)                 Monthly revenue($)         monthly_revenue
评分数                      Reviews                    ratings_total
评分                       Rating                     rating
大类BSR                    Category BSR               main_bsr
小类BSR                    Sub-Category BSR           sub_bsr
类目路径                    Category Path              category_path
上架时间                    —                          launch_date
配送方式                    —                          fulfillment
卖家所属地                   —                          seller_location
FBA($)                     —                          fba_fee
毛利率                      —                          margin
```

评论文件列名映射：

```
中文列头          内部字段名
───────────────────────────
内容              body（评论英文原文）
内容(翻译)        body_cn（中文翻译）
星级              rating（1-5）
VP评论            verified_purchase（Y/N）
评论链接           review_url
```

### 解析流程

```
parse_all_files(file_paths)
  │
  ├── 遍历每个文件 → classify_and_parse_file(path)
  │     │
  │     ├── openpyxl 打开文件（read_only 模式，跳过 ~$ 临时文件）
  │     │
  │     ├── 遍历每个 sheet：
  │     │     ├── _get_headers(): 扫描前 5 行找到列头行（含 ASIN 或 # 的行）
  │     │     ├── _is_review_sheet(): 判断是否为评论 sheet
  │     │     ├── _is_product_sheet(): 判断是否为产品 sheet
  │     │     │
  │     │     ├── 产品 sheet → _parse_product_rows():
  │     │     │     列头标准化 → 逐行读取 → 数值字段强转 float → 以 ASIN 为 key 存入字典
  │     │     │
  │     │     └── 评论 sheet → _parse_review_rows():
  │     │           列头标准化 → 逐行读取 → 提取 ASIN（sheet名 > 数据行 > 文件名）→ 按 ASIN 分组
  │     │
  │     └── 返回 {products: {asin: {...}}, reviews: {asin: [...]}, file_type, sheets_parsed}
  │
  └── 合并所有文件：产品数据按 ASIN 去重（后文件覆盖前文件），评论数据追加
      返回 {excel_data, reviews_by_asin, stats}
```

### 多文件合并

用户可以同时上传多个文件（产品数据 + 评论数据混合上传），系统自动识别并合并：

- **产品数据**：以 ASIN 为 key 合并，同一 ASIN 在多个文件中出现时后者覆盖前者
- **评论数据**：以 ASIN 为 key 追加，不同文件的同一 ASIN 评论合并为一个列表
- **统计信息**：记录产品文件数、评论文件数、总产品数、总评论数

---

## 工作流各节点如何使用 Excel 数据

### 节点 1：数据检索（crawl.py）

crawl 节点是 Excel 数据进入工作流的入口，负责将 Excel 数据转换为下游节点所需的格式。

**Phase 1 — ASIN 查找**：遍历用户输入的 ASIN 列表，在 `excel_data` 字典中直接查找。找到的产品转换为标准格式（含 title、brand、price、rating、ratings_total、monthly_sales、bullet_points 等字段）。找不到的 ASIN 记入 warnings。

**Phase 2 — 关键词搜索**：遍历用户输入的关键词，在所有产品的 title、title_cn、category_path、sub_category、main_category 中做子串匹配。匹配到的产品构造为搜索结果格式，供 market 节点计算价格分布和市场规模。

**输出**：
- `products[]` — 用户指定 ASIN 对应的产品列表（严格按用户输入，不自动补充）
- `search_by_keyword{}` — 每个关键词对应的搜索匹配结果
- `reviews_by_asin{}` — 直接透传 Excel 解析的评论数据

### 节点 2：市场分析（market.py）

**数据来源**：`search_by_keyword`（crawl 节点从 Excel 关键词匹配生成）

**计算逻辑**：
- 从每个关键词的匹配产品中提取价格列表，计算 **最低价、最高价、中位价**
- 统计 Top20 产品评论总量，评估 **市场热度等级**（★ 到 ★★★★★）
- 根据评论量推断 **销量区间**（月销 <1000 / 1000-5000 / 5000+）
- 提取 Top10 产品的 **品牌集中度**

**输出**：每个关键词的市场概况（价格区间、中位价、热度评级、销量带、趋势判断）

### 节点 3：竞争评估（competition.py）

**数据来源**：`products`（crawl 节点从 Excel ASIN 查找生成）、`market`

**计算逻辑**：
- 逐个竞品计算竞争力得分：`rating + min(5, reviews_total / 5000)`
- 月销估算：优先取 Excel 中的 `bought_past_month`（月销量），无则用 `reviews_total × 2`
- 每个关键词的竞争热度矩阵：热度、价格区间、竞争激烈度

**输出**：竞品排名表（ASIN、标题、品牌、价格、评分、评论数、月销、竞争力星级）

### 节点 4：价格测算（pricing.py）

**数据来源**：`market`（基于 Excel 产品价格计算的中位价）

**计算逻辑**：
- 建议入场价 = 中位价 × 92%
- 目标成本上限 = 入场价 × (1 - 目标利润率 - FBA费率)
- 单件预期毛利 = 入场价 × 目标利润率

**输出**：每个关键词的定价建议（中位价、入场价、价格区间、成本上限、毛利）

### 节点 5：差评挖掘（bad_reviews.py）

**数据来源**：`reviews_by_asin`（Excel 评论文件解析）、`products`（Excel 产品卖点）

**处理逻辑**：
1. 从所有评论中筛选 1-3 星差评（`rating <= 3`）
2. 去重后拼接为文本，截取前 18000 字符
3. 调用 **Kimi LLM** 提炼 TOP10 痛点，每个痛点包含：
   - 痛点命名（8-16字中文）
   - 出现频次、维度（质量耐久/核心功能/使用体验等）、严重度
   - 典型英文原句引用
   - 根因推断、改良建议
4. LLM 不可用时，退化为关键词频次统计

**无评论数据时**：如果用户未上传评论 Excel，`reviews_by_asin` 为空，差评数量为 0，将退化为基于关键词频次的模板输出。报告中会明确标注"无评论数据"。

**输出**：TOP10 痛点列表、按关键词分组的差评摘录

### 节点 6：方向规划（directions.py）

**数据来源**：`market`、`pricing`、`bad_reviews`（全部源自 Excel）

**处理逻辑**：
1. 将市场数据（价格、销量带、趋势）、定价数据（入场价、成本上限）、TOP10 痛点压缩为结构化上下文
2. 调用 **Kimi LLM** 生成 3 个差异化上新方向（gold/silver/bronze），每个方向包含：
   - 方向命名、定位、目标人群、目标价格、月销目标
   - 数据/差评依据（必须引用实际数据）
   - 5-7 条可执行改良点（指向具体零部件/材料/工艺）
   - 风险提示

**输出**：3 个产品上新方向 + 综合结论与行动优先级

### 节点 7：生成报告（report.py → docx_writer.py）

汇总所有节点输出，生成结构化 DOCX 报告：

| 报告章节 | 数据来源 | 内容 |
|---------|---------|------|
| 封面 | data_stats, warnings | 数据来源说明（N 个产品、N 条评论）、数据缺失警告 |
| 一、市场规模 | market 节点 | 关键词维度的价格/销量/热度对比表 + 关键洞察 |
| 二、竞争指数 | competition 节点 | 竞品矩阵表 + 关键词竞争热度卡片 |
| 三、推荐入场价 | pricing 节点 | 定价建议表（中位价/入场价/成本上限/毛利） |
| 四、差评 TOP10 | bad_reviews 节点 | 痛点表（频次/维度/严重度/原句/建议）+ 根因推断 |
| 五、差评原句摘录 | bad_reviews 节点 | 按关键词分组的原始差评引用 |
| 六、产品上新方向 | directions 节点 | 3 个方向详情（定位/人群/改良点/风险） |
| 综合结论 | directions 节点 | 行动优先级排序表 |

**数据溯源保障**：
- 封面标注"数据来源: 上传 Excel（N 个产品，N 条评论）"
- 无评论时章节标题改为"市场痛点推断（无评论数据）"
- ASIN 未找到等问题在封面显示警告

---

## 安装

```bash
cd "C:\Users\18782\Desktop\新建文件夹 (4)\amazon_selection"
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env 填入 KIMI_API_KEY（用于差评分析和方向生成）
```

## 运行

```bash
# 启动后端
py -m uvicorn backend.main:app --reload --port 8000
```

打开 http://localhost:8000 ，上传 Excel 文件 → 输入 ASIN 和关键词 → 启动分析 → 下载 DOCX 报告。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传 Excel 文件（支持多文件），返回文件名列表 |
| POST | `/analyze` | 提交分析任务（ASIN + 关键词 + 文件名），返回 `job_id` |
| GET | `/status/{job_id}` | 查询进度（节点名 + 百分比） |
| GET | `/result/{job_id}` | 获取 JSON 结果 |
| GET | `/report/{job_id}` | 下载 DOCX 报告 |

## 目录结构

```
amazon_selection/
├── backend/
│   ├── main.py                  FastAPI 入口（/upload + /analyze + /status + /result + /report）
│   ├── jobs.py                  后台任务管理（Excel 解析 + 工作流调度）
│   ├── llm.py                   Kimi LLM 客户端
│   ├── excel_parser/
│   │   ├── __init__.py
│   │   └── parser.py            Excel 智能解析（文件类型识别 + 列名标准化 + 产品/评论提取）
│   ├── graph/
│   │   ├── state.py             GraphState 定义（excel_data, warnings, data_stats 等字段）
│   │   ├── workflow.py          LangGraph StateGraph（7 节点串行流水线）
│   │   └── nodes/
│   │       ├── crawl.py         数据检索（从 Excel 按 ASIN/关键词查找）
│   │       ├── market.py        市场分析（价格分布、热度、销量带）
│   │       ├── competition.py   竞争评估（竞品评分、月销、竞争力矩阵）
│   │       ├── pricing.py       价格测算（入场价、成本上限、毛利）
│   │       ├── bad_reviews.py   差评挖掘（LLM 提炼 TOP10 痛点）
│   │       ├── directions.py    方向规划（LLM 生成 3 个上新方向）
│   │       └── report.py        报告生成入口
│   └── report/
│       ├── docx_writer.py       DOCX 报告生成（样式 + 数据溯源标注）
│       └── output/              生成的报告存放目录
├── web/
│   └── index.html               前端页面（文件上传 + ASIN/关键词输入 + 进度展示 + 结果展示）
├── uploads/                     上传文件临时存放
├── requirements.txt
├── .env.example
├── run_backend.bat
└── run_frontend.bat
```

## 支持的 Excel 格式

- **卖家精灵中文版**导出（BS100、NS100、市场分析等 sheet，中文列头）
- **卖家精灵英文版**导出（US sheet，英文列头如 Product Title、Monthly Sales）
- **卖家精灵评论导出**（每个 ASIN 一个文件，含评论原文和星级）
- 其他工具导出的 Excel，只要列头包含 ASIN + 价格/销量关键词即可被识别

## 备注

- 没有 KIMI_API_KEY 时，差评 TOP10 与上新方向会退化为基于关键词频次的模板输出
- 所有分析数据 100% 来自用户上传的 Excel，不调用任何外部数据 API
- 报告中明确标注数据来源和样本量，无数据时标注"无评论数据"而非虚构
- 报告输出目录：`backend/report/output/`
