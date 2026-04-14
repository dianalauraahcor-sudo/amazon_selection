import re
from statistics import median
from ..state import GraphState


def _price(item: dict) -> float | None:
    p = item.get("price") or {}
    if isinstance(p, dict):
        v = p.get("value")
        if v: return float(v)
    return None


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("¥", "").replace("元", "")
                      .replace("约", "").replace("~", "").replace("个", "").replace("单", "").strip())
    except (ValueError, TypeError):
        return None


def _rank_bucket(reviews_total: int) -> str:
    if reviews_total > 50000: return "★★★★★"
    if reviews_total > 20000: return "★★★★"
    if reviews_total > 5000: return "★★★"
    if reviews_total > 1000: return "★★"
    return "★"


def _parse_market_text(texts: list) -> dict:
    """Extract structured metrics from market analysis text lines."""
    info = {}
    for t in texts:
        t = str(t)
        # Match key-value patterns like "类目月总销量\t88267" or "品牌集中度\t37.8%"
        if "类目月总销量" in t or "月总销量" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["monthly_total_sales"] = int(v)
        elif "类目月总销售额" in t or "月总销售额" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["monthly_total_revenue"] = v
        elif "样本平均价格" in t or "平均价格" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["avg_price"] = round(v, 2)
        elif "样本价格中位数" in t or "价格中位数" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["median_price"] = round(v, 2)
        elif "样本平均评分" in t or "平均评分" in t or "平均星级" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["avg_rating"] = round(v, 2)
        elif "样本平均评论数" in t or "平均评论数" in t:
            v = _safe_float(t.split("\t")[-1] if "\t" in t else t)
            if v:
                info["avg_reviews"] = int(v)
        elif "品牌集中度" in t:
            m = re.search(r"([\d.]+)%", t)
            if m:
                info["brand_concentration"] = f"{m.group(1)}%"
        elif "卖家集中度" in t:
            m = re.search(r"([\d.]+)%", t)
            if m:
                info["seller_concentration"] = f"{m.group(1)}%"
        elif "中国卖家占比" in t:
            m = re.search(r"([\d.]+)%", t)
            if m:
                info["cn_seller_pct"] = f"{m.group(1)}%"
        elif "新品占比" in t:
            m = re.search(r"([\d.]+)%", t)
            if m:
                info["new_product_pct"] = f"{m.group(1)}%"
        elif "FBA卖家占比" in t or "FBA占比" in t:
            m = re.search(r"([\d.]+)%", t)
            if m:
                info["fba_pct"] = f"{m.group(1)}%"
        elif "Top10月均销量" in t or "Top10月销" in t:
            m = re.search(r"~?([\d,]+)", t)
            if m:
                info["top10_monthly_sales"] = m.group(1).replace(",", "")
        elif "头部品牌" in t:
            # e.g. "头部品牌TOP5\tDEWALT/HOTLIGH/Zetunlo/..."
            parts = t.split("\t")
            if len(parts) >= 2:
                info["top_brands_text"] = parts[-1]
    return info


def _parse_market_dicts(rows: list) -> tuple:
    """Extract overview + monthly trends from table-format market analysis (list of dicts).

    Returns (overview_dict, trends_list).
    """
    overview = {}
    trends = []

    # Check if we have the standard header-based monthly table format
    # Typical keys: 月份, 样本商品数, 月总销量, 月均销量, 月总销售额($), 平均价格($), 平均星级, 品牌集中度, etc.
    _monthly_keys = {"月份", "月总销量", "月均销量", "月总销售额", "平均价格"}

    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = set(row.keys())

        # ── Monthly data row (has 月份 field) ──
        month_val = row.get("月份")
        if month_val and str(month_val).strip():
            trend_row = {"月份": str(month_val).strip()}
            for k, v in row.items():
                if k == "月份":
                    continue
                trend_row[k] = v
            trends.append(trend_row)

            # Also extract overview from the first (or most recent) data row
            if not overview.get("monthly_total_sales"):
                v = _safe_float(row.get("月总销量"))
                if v:
                    overview["monthly_total_sales"] = int(v)
                v = _safe_float(row.get("月总销售额($)") or row.get("月总销售额"))
                if v:
                    overview["monthly_total_revenue"] = v
                v = _safe_float(row.get("平均价格($)") or row.get("平均价格"))
                if v:
                    overview["avg_price"] = round(v, 2)
                v = _safe_float(row.get("平均星级") or row.get("平均评分"))
                if v:
                    overview["avg_rating"] = round(v, 2)
                v = _safe_float(row.get("平均评分数") or row.get("平均评论数"))
                if v:
                    overview["avg_reviews"] = int(v)

                # Concentration metrics (may be decimal 0.xx or percentage string)
                for field, key in [
                    ("brand_concentration", "品牌集中度"),
                    ("seller_concentration", "卖家集中度"),
                    ("product_concentration", "商品集中度"),
                ]:
                    raw = row.get(key)
                    if raw is not None:
                        fv = _safe_float(raw)
                        if fv is not None:
                            if fv < 1:
                                overview[field] = f"{round(fv * 100, 1)}%"
                            else:
                                overview[field] = f"{round(fv, 1)}%"

                # New product ratio
                raw_new = row.get("新品占比")
                if raw_new is not None:
                    fv = _safe_float(raw_new)
                    if fv is not None:
                        if fv < 1:
                            overview["new_product_pct"] = f"{round(fv * 100, 1)}%"
                        else:
                            overview["new_product_pct"] = f"{round(fv, 1)}%"

                # Sample count (may contain text like "商品：100\n品牌：74")
                sample_raw = row.get("样本商品数")
                if sample_raw:
                    s = str(sample_raw)
                    m = re.search(r"商品[：:]?\s*(\d+)", s)
                    if m:
                        overview["sample_count"] = int(m.group(1))
                        m2 = re.search(r"品牌[：:]?\s*(\d+)", s)
                        if m2:
                            overview["brand_count"] = int(m2.group(1))
                        m3 = re.search(r"卖家[：:]?\s*(\d+)", s)
                        if m3:
                            overview["seller_count"] = int(m3.group(1))
                    else:
                        v = _safe_float(s)
                        if v:
                            overview["sample_count"] = int(v)

        # ── Category sub-segment rows (样品分类 format) ──
        elif row.get("样品分类") or row.get("样本分类"):
            label = str(row.get("样品分类") or row.get("样本分类", "")).strip()
            if label == "全部商品" and not overview.get("monthly_total_sales"):
                v = _safe_float(row.get("月总销量"))
                if v:
                    overview["monthly_total_sales"] = int(v)
                v = _safe_float(row.get("月总销售额($)") or row.get("月总销售额"))
                if v:
                    overview["monthly_total_revenue"] = v
                v = _safe_float(row.get("平均价格($)") or row.get("平均价格"))
                if v:
                    overview["avg_price"] = round(v, 2)

    return overview, trends


def market_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb: cb("market", 35)

    out = {}
    market_trends = []
    market_overview = {}

    # ── Parse Excel market analysis data (text or dict format) ──
    excel_market_data = state.get("market_analysis", [])
    excel_info = {}
    if excel_market_data and isinstance(excel_market_data, list):
        if isinstance(excel_market_data[0], str):
            # LED-style: list of text lines
            excel_info = _parse_market_text(excel_market_data)
        elif isinstance(excel_market_data[0], dict):
            # Table-style: list of dicts with column headers as keys
            excel_info, market_trends = _parse_market_dicts(excel_market_data)
    market_overview = dict(excel_info)  # copy for output

    # ── Compute from keyword search results (per-keyword dimension) ──
    for kw, sr in state.get("search_by_keyword", {}).items():
        results = sr.get("search_results", []) or []
        prices = [p for p in (_price(r) for r in results) if p]
        reviews_sum = sum((r.get("ratings_total") or 0) for r in results[:20])

        # Use Excel data as fallback when keyword search returns empty
        kw_data = {
            "result_count": len(results),
            "price_min": round(min(prices), 2) if prices else None,
            "price_max": round(max(prices), 2) if prices else None,
            "price_median": round(median(prices), 2) if prices else None,
            "top_brands": list({(r.get("brand") or "—") for r in results[:10]})[:5],
            "review_sum_top20": reviews_sum,
            "rating": _rank_bucket(reviews_sum),
            "trend": "↑ 上升" if reviews_sum > 10000 else "→ 平稳",
            "sales_band": (
                "月销 5000+" if reviews_sum > 30000
                else "月销 1000–5000" if reviews_sum > 8000
                else "月销 <1000"
            ),
        }

        # Enrich with Excel market data when available
        if excel_info:
            if not prices and excel_info.get("median_price"):
                kw_data["price_median"] = excel_info["median_price"]
            if not prices and excel_info.get("avg_price"):
                kw_data["price_min"] = round(excel_info["avg_price"] * 0.3, 2)
                kw_data["price_max"] = round(excel_info["avg_price"] * 3.0, 2)
            if excel_info.get("monthly_total_sales"):
                total = excel_info["monthly_total_sales"]
                kw_data["sales_band"] = (
                    f"月销 {total:,}" if total > 5000
                    else f"月销 {total:,}"
                )
                kw_data["result_count"] = kw_data["result_count"] or excel_info.get("avg_reviews", 0)
            if excel_info.get("avg_reviews"):
                avg_rev = excel_info["avg_reviews"]
                estimated_sum = avg_rev * min(len(results), 20) if results else avg_rev * 10
                if estimated_sum > reviews_sum:
                    kw_data["review_sum_top20"] = estimated_sum
                    kw_data["rating"] = _rank_bucket(estimated_sum)
                    kw_data["trend"] = "↑ 上升" if estimated_sum > 10000 else "→ 平稳"
            # Inject extra Excel metrics for downstream (insights node)
            for field in ("brand_concentration", "seller_concentration", "cn_seller_pct",
                          "new_product_pct", "fba_pct", "top10_monthly_sales",
                          "top_brands_text", "monthly_total_sales", "monthly_total_revenue",
                          "avg_price", "avg_rating", "avg_reviews"):
                if field in excel_info:
                    kw_data[field] = excel_info[field]

        out[kw] = kw_data

    # ── If no keywords provided, build market from target ASIN products ──
    if not out and state.get("products"):
        prices = [p for p in (_price(pr.get("product", {})) for pr in state["products"]) if p]
        reviews_sum = sum((pr.get("product", {}).get("ratings_total") or 0) for pr in state["products"])
        out["目标产品"] = {
            "result_count": len(state["products"]),
            "price_min": round(min(prices), 2) if prices else None,
            "price_max": round(max(prices), 2) if prices else None,
            "price_median": round(median(prices), 2) if prices else None,
            "top_brands": list({(pr.get("product", {}).get("brand") or "—") for pr in state["products"]})[:5],
            "review_sum_top20": reviews_sum,
            "rating": _rank_bucket(reviews_sum),
            "trend": "→ 平稳",
            "sales_band": f"样本 {len(state['products'])} 个产品",
        }
        # Also enrich with Excel data
        if excel_info:
            for field in ("brand_concentration", "seller_concentration", "cn_seller_pct",
                          "monthly_total_sales", "monthly_total_revenue", "avg_price",
                          "avg_rating", "avg_reviews", "top_brands_text"):
                if field in excel_info:
                    out["目标产品"][field] = excel_info[field]

    if cb: cb("market", 45)
    return {"market": out, "market_trends": market_trends, "market_overview": market_overview}
