from typing import TypedDict, List, Dict, Any, Optional, Callable


class GraphState(TypedDict, total=False):
    # inputs
    category: str
    asins: List[str]
    keywords: List[str]
    target_margin: float
    fee_rate: float
    # Excel data source
    excel_data: Dict[str, Dict[str, Any]]         # {asin: {product_data}} parsed from Excel
    # Excel analysis sheets (directly from uploaded Excel)
    market_analysis: List[Dict[str, Any]]          # 市场分析 sheet data
    competitor_analysis: Dict[str, Dict[str, Any]] # 竞品对比矩阵 {asin: {metrics}}
    profit_calc: List[Dict[str, Any]]              # 利润核算 sheet data
    keyword_analysis: List[Dict[str, Any]]         # 关键词分析 data
    category_trends: List[str]                     # 类目趋势文本
    source_conclusions: List[str]                  # 结论建议文本
    # raw data (populated by crawl node from excel_data)
    products: List[Dict[str, Any]]
    reviews_by_asin: Dict[str, List[Dict[str, Any]]]
    search_by_keyword: Dict[str, Dict[str, Any]]
    # analysis
    market: Dict[str, Any]
    market_trends: List[Dict[str, Any]]           # 月度趋势数据
    market_overview: Dict[str, Any]               # 市场概览（集中度、总量等）
    competition: Dict[str, Any]
    pricing: Dict[str, Any]
    bad_reviews: Dict[str, Any]
    insights: Dict[str, Any]                      # LLM 生成的洞察
    directions: Dict[str, Any]
    conclusion: List[Dict[str, Any]]
    # output
    report_path: Optional[str]
    # traceability
    warnings: List[str]
    data_stats: Dict[str, Any]                    # {total_products, total_reviews, ...}
    # progress callback
    on_progress: Optional[Callable[[str, int], None]]
