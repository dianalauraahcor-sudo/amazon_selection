"""Crawl node — look up product & review data from uploaded Excel (replaces API calls)."""
from ..state import GraphState


def _to_api_product(asin: str, p: dict) -> dict:
    """Convert Excel product dict to API-compatible format consumed by downstream nodes."""
    return {
        "product": {
            "asin": asin,
            "title": p.get("title") or p.get("title_cn") or "",
            "brand": p.get("brand") or "—",
            "price": {"value": p.get("price")},
            "rating": p.get("rating"),
            "ratings_total": p.get("ratings_total"),
            "reviews_total": p.get("ratings_total"),
            "bought_past_month": p.get("monthly_sales"),
            "bullet_points": p.get("bullet_points") or p.get("bullet_points_cn") or "",
            "top_reviews": [],  # reviews come from reviews_by_asin
            # Extra fields from Excel (available for enriched analysis)
            "monthly_revenue": p.get("monthly_revenue"),
            "main_bsr": p.get("main_bsr"),
            "sub_bsr": p.get("sub_bsr"),
            "fulfillment": p.get("fulfillment"),
            "seller_location": p.get("seller_location"),
            "launch_date": p.get("launch_date"),
            "margin": p.get("margin"),
            "fba_fee": p.get("fba_fee"),
            "category_path": p.get("category_path"),
        },
    }


def _to_search_result(asin: str, p: dict) -> dict:
    """Convert Excel product dict to search-result format for market node."""
    return {
        "asin": asin,
        "title": p.get("title") or p.get("title_cn") or "",
        "brand": p.get("brand") or "—",
        "price": {"value": p.get("price")},
        "rating": p.get("rating"),
        "ratings_total": p.get("ratings_total"),
        "bought_past_month": p.get("monthly_sales"),
    }


def crawl_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb:
        cb("crawl", 5)

    excel_data = state.get("excel_data", {})
    warnings = list(state.get("warnings", []))

    products = []
    reviews_by_asin = dict(state.get("reviews_by_asin", {}))
    search_by_keyword = {}

    # ── Phase 1: look up user-provided ASINs from Excel ──
    # Also check competitor_analysis for ASINs not in product sheets
    competitor_analysis = state.get("competitor_analysis", {})
    found_asins = set()
    missing_asins = []
    for asin in state.get("asins", []):
        asin = asin.strip()
        if not asin:
            continue
        if asin in excel_data:
            products.append(_to_api_product(asin, excel_data[asin]))
            found_asins.add(asin)
        elif asin in competitor_analysis:
            # Build a minimal product from competitor analysis data
            m = competitor_analysis[asin]
            synth = {
                "title": m.get("产品类型") or m.get("核心卖点") or "",
                "brand": m.get("品牌") or "—",
                "price": m.get("当前价格($)") or m.get("价格") or m.get("价格($)"),
                "rating": m.get("评分"),
                "ratings_total": m.get("评论数"),
                "monthly_sales": m.get("月均销量(估算)") or m.get("月销量"),
            }
            products.append(_to_api_product(asin, synth))
            found_asins.add(asin)
        else:
            missing_asins.append(asin)

    if missing_asins:
        warnings.append(f"以下 ASIN 在上传数据中未找到: {', '.join(missing_asins)}")

    if cb:
        cb("crawl", 12)

    # ── Phase 2: keyword search in Excel product titles / categories ──
    competitor_analysis = state.get("competitor_analysis", {})
    for kw in state.get("keywords", []):
        kw_lower = kw.lower()
        kw_words = kw_lower.split()
        matched_asins = set()
        matches = []
        # Search in product sheet data (excel_data)
        for asin, p in excel_data.items():
            text = " ".join([
                str(p.get("title") or ""),
                str(p.get("title_cn") or ""),
                str(p.get("category_path") or ""),
                str(p.get("sub_category") or ""),
                str(p.get("main_category") or ""),
                str(p.get("product_type") or ""),
                str(p.get("product_subtype") or ""),
                str(p.get("bullet_points") or ""),
            ]).lower()
            if all(w in text for w in kw_words):
                matches.append(_to_search_result(asin, p))
                matched_asins.add(asin)
        # Search in competitor analysis data
        for asin, metrics in competitor_analysis.items():
            if asin in matched_asins:
                continue
            text = " ".join([
                str(metrics.get("产品类型") or ""),
                str(metrics.get("核心卖点") or ""),
                str(metrics.get("品牌") or ""),
                str(metrics.get("类目") or ""),
                str(metrics.get("产品标题") or ""),
                str(metrics.get("标题") or ""),
            ]).lower()
            if all(w in text for w in kw_words):
                import re as _re
                price = None
                price_raw = metrics.get("价格") or metrics.get("当前价格($)") or metrics.get("价格($)")
                if price_raw:
                    m = _re.search(r"[\d.]+", str(price_raw).replace(",", ""))
                    if m:
                        price = float(m.group(0))
                rating_raw = str(metrics.get("评分") or "")
                rating = None
                ratings_total = None
                if rating_raw:
                    m = _re.match(r"([\d.]+)", rating_raw)
                    if m:
                        rating = float(m.group(1))
                    m2 = _re.search(r"\((\d+)\)", rating_raw)
                    if m2:
                        ratings_total = int(m2.group(1))
                if ratings_total is None:
                    rt = metrics.get("评论数")
                    if rt:
                        try:
                            ratings_total = int(float(str(rt).replace(",", "").replace("条", "")))
                        except (ValueError, TypeError):
                            pass
                ms_raw = metrics.get("月销量") or metrics.get("月均销量") or metrics.get("月均销量(估算)")
                monthly_sales = None
                if ms_raw:
                    m = _re.search(r"[\d,]+", str(ms_raw).replace("~", ""))
                    if m:
                        try:
                            monthly_sales = int(float(m.group(0).replace(",", "")))
                        except (ValueError, TypeError):
                            pass
                matches.append({
                    "asin": asin,
                    "title": str(metrics.get("核心卖点") or metrics.get("产品类型") or ""),
                    "brand": str(metrics.get("品牌") or "—"),
                    "price": {"value": price},
                    "rating": rating,
                    "ratings_total": ratings_total,
                    "bought_past_month": monthly_sales,
                })
                matched_asins.add(asin)
        search_by_keyword[kw] = {"search_results": matches}
        if not matches:
            warnings.append(f"关键词 '{kw}' 在上传数据中未匹配到任何产品")

    if cb:
        cb("crawl", 18)

    if cb:
        cb("crawl", 25)
    return {
        "products": products,
        "reviews_by_asin": reviews_by_asin,
        "search_by_keyword": search_by_keyword,
        "warnings": warnings,
    }
