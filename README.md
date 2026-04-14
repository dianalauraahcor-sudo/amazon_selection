# Amazon AI Selection Analysis System

Amazon product selection analysis system based on **LangGraph workflow + Excel data + Kimi LLM**, automatically generating professional DOCX selection evaluation reports.

Upload seller sprite / Jungle Scout exported Excel files, input target ASINs and keywords, the system retrieves data from Excel, analyzes through an 8-node workflow pipeline, and generates a comprehensive selection report.

## Features

- Multi-file upload: supports product data + review data mixed upload, automatic identification and merging
- Intelligent Excel parsing: auto-recognizes seller sprite Chinese/English export formats, standardizes column names
- 8-node LangGraph workflow with parallel execution (market/competition/reviews run concurrently)
- LLM-powered analysis: pain point extraction, strategic insights, differentiated product direction planning
- Professional DOCX report generation with data traceability
- Real-time progress tracking via polling API
- Single-page frontend with file upload, progress display, and result visualization

## Architecture

```
User uploads Excel + inputs ASIN/Keywords/Margin
                │
                ▼
        ┌──────────────┐
        │  Excel Parse  │  parser.py
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  Data Crawl   │  crawl.py — ASIN lookup + keyword search from Excel
        └──────┬───────┘
               │
       ┌───────┼───────┐        (parallel)
       ▼       ▼       ▼
   ┌────────┐┌──────┐┌──────────┐
   │ Market ││Compet││Bad Review│
   │Analysis││ition ││ Mining   │
   └───┬────┘└──┬───┘└────┬─────┘
       │        │         │
       ▼        │         │
   ┌────────┐   │         │
   │Pricing │   │         │
   └───┬────┘   │         │
       └────────┼─────────┘
                ▼
        ┌──────────────┐
        │   Insights    │  LLM strategic synthesis
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  Directions   │  LLM generates 3 product directions
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ DOCX Report   │  docx_writer.py
        └──────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Kimi API Key (optional, for LLM-powered analysis)

### Installation

```bash
git clone https://github.com/dianalauraahcor-sudo/amazon_selection.git
cd amazon_selection
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and fill in your API key:
```
KIMI_API_KEY=your_moonshot_api_key_here
```

### Run

```bash
py -m uvicorn backend.main:app --reload --port 8000
```

Or on Windows double-click `run_backend.bat`.

Open http://localhost:8000, upload Excel files, input ASINs and keywords, start analysis, download DOCX report.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Upload Excel files (multi-file), returns filename list |
| POST | `/analyze` | Submit analysis task (ASIN + keywords + filenames), returns `job_id` |
| GET | `/status/{job_id}` | Query progress (node name + percentage) |
| GET | `/result/{job_id}` | Get JSON result |
| GET | `/report/{job_id}` | Download DOCX report |

### POST `/analyze` Request Body

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

## Workflow Nodes

| Node | File | Description |
|------|------|-------------|
| **Data Crawl** | `crawl.py` | Looks up ASINs in Excel data, performs keyword search across product titles/categories |
| **Market Analysis** | `market.py` | Price distribution, market heat rating, sales volume bands, brand concentration |
| **Competition** | `competition.py` | Competitor scoring, monthly sales estimation, competitive matrix |
| **Pricing** | `pricing.py` | Entry price, cost ceiling, per-unit margin calculation |
| **Bad Reviews** | `bad_reviews.py` | LLM extracts TOP10 pain points from 1-3 star reviews with root cause and improvement suggestions |
| **Insights** | `insights.py` | LLM synthesizes all data into strategic insights with executive summary |
| **Directions** | `directions.py` | LLM generates 3 differentiated product directions (gold/silver/bronze) |
| **Report** | `report.py` | Orchestrates DOCX report generation via `docx_writer.py` |

## Excel Format Support

### Product Data
Columns must contain `ASIN` + (`Monthly Sales` or `月销量`) + (`Price` or `价格`), with 15+ columns.

| Chinese Header | English Header | Internal Field |
|---------------|----------------|----------------|
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

### Review Data
Columns must contain `ASIN` + (`Content` or `内容`) + (`Rating` or `星级`).

| Chinese Header | Internal Field |
|---------------|----------------|
| 内容 | body |
| 内容(翻译) | body_cn |
| 星级 | rating |
| VP评论 | verified_purchase |

## DOCX Report Structure

| Chapter | Data Source | Content |
|---------|-----------|---------|
| Cover | data_stats, warnings | Data source description, missing data warnings |
| 1. Market Overview | market node | Price/volume/heat comparison by keyword |
| 2. Competition Index | competition node | Competitor matrix + keyword competition cards |
| 3. Entry Price | pricing node | Pricing table (median/entry/cost ceiling/margin) |
| 4. Pain Points TOP10 | bad_reviews node | Pain point table with frequency/severity/quotes/suggestions |
| 5. Review Excerpts | bad_reviews node | Raw negative reviews grouped by keyword |
| 6. Product Directions | directions node | 3 directions with positioning/audience/improvements/risks |
| Conclusion | directions node | Action priority ranking |

## Project Structure

```
amazon_selection/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── jobs.py                  # Background task management
│   ├── schemas.py               # Pydantic request/response models
│   ├── llm.py                   # Kimi (Moonshot) LLM client
│   ├── excel_parser/
│   │   ├── parser.py            # Excel parsing (file type detection + column standardization)
│   │   └── schemas.py           # Excel field schemas
│   ├── graph/
│   │   ├── state.py             # GraphState TypedDict definition
│   │   ├── workflow.py          # LangGraph StateGraph (8 nodes, parallel branches)
│   │   └── nodes/
│   │       ├── crawl.py         # Data retrieval from Excel
│   │       ├── market.py        # Market analysis
│   │       ├── competition.py   # Competition evaluation
│   │       ├── pricing.py       # Pricing calculation
│   │       ├── bad_reviews.py   # Negative review mining (LLM)
│   │       ├── insights.py      # Strategic insights (LLM)
│   │       ├── directions.py    # Product direction planning (LLM)
│   │       └── report.py        # Report generation entry
│   └── report/
│       ├── docx_writer.py       # DOCX report generation with professional styling
│       ├── analytics.py         # Pure data analytics (no LLM, no side effects)
│       └── output/              # Generated reports directory
├── web/
│   └── index.html               # Single-page frontend
├── uploads/                     # Uploaded files (temporary)
├── tests/
│   └── test_product_schema.py
├── requirements.txt
├── .env.example
└── run_backend.bat
```

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Workflow**: LangGraph (StateGraph with parallel conditional edges)
- **LLM**: Kimi / Moonshot API (OpenAI-compatible)
- **Excel**: openpyxl (read-only mode)
- **Report**: python-docx
- **Frontend**: Vanilla HTML + Tailwind CSS (single file)

## Notes

- Without `KIMI_API_KEY`, pain points TOP10 and product directions fall back to keyword frequency-based template output
- All analysis data comes 100% from uploaded Excel files, no external data APIs are called
- Reports clearly label data sources and sample sizes; missing data is marked explicitly
- Report output directory: `backend/report/output/`
