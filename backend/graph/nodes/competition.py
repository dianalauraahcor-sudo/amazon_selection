from ..state import GraphState


def _g(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict): return default
        d = d.get(k)
    return d if d is not None else default


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("~", "")
                      .replace("约", "").replace("¥", "").strip())
    except (ValueError, TypeError):
        return None


def _competitiveness(rating, reviews_total, monthly_sales):
    """Score competitiveness on 1-5 star scale using rating, reviews, and sales."""
    score = 0
    # Rating contribution: 4.0→1, 4.5→2, 4.7→3 (max 3)
    if rating:
        score += max(0, (float(rating) - 3.5)) * 3  # 4.5 → 3.0, 4.7 → 3.6
    # Reviews contribution: 100→1, 500→2, 1000→3, 5000→4 (max 4)
    if reviews_total:
        r = int(reviews_total)
        if r >= 5000: score += 4
        elif r >= 1000: score += 3
        elif r >= 500: score += 2
        elif r >= 100: score += 1
    # Monthly sales contribution: 500→1, 1000→2, 3000→3, 5000→4 (max 4)
    if monthly_sales:
        s = float(monthly_sales)
        if s >= 5000: score += 4
        elif s >= 3000: score += 3
        elif s >= 1000: score += 2
        elif s >= 500: score += 1
    # Normalize to 1-5 stars (max raw score ~11)
    stars = max(1, min(5, round(score / 2.2)))
    return "★" * stars


def competition_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb: cb("competition", 55)

    excel_comp = state.get("competitor_analysis", {})
    rows = []

    target_asins = set(a.strip() for a in state.get("asins", []) if a.strip())

    if excel_comp:
        import re as _re
        # ── Use pre-analyzed competitor matrix from Excel ──
        # Only include target ASINs the user specified
        filtered_comp = {a: m for a, m in excel_comp.items() if a in target_asins} if target_asins else excel_comp
        for asin, metrics in filtered_comp.items():
            # Price: try multiple column name variants
            price = _safe_float(
                metrics.get("价格") or metrics.get("价格（$）") or metrics.get("价格($)")
                or metrics.get("当前价格($)") or metrics.get("当前价格")
            )
            # Monthly sales: try multiple variants, strip non-numeric suffixes
            monthly_sales_raw = (
                metrics.get("月销量") or metrics.get("月均销量") or metrics.get("月均销量(估算)")
            )
            monthly_sales = None
            if monthly_sales_raw:
                # Extract first number from strings like "2,790单 (JS实测)" or "~5,000单"
                ms = _re.search(r"[\d,]+", str(monthly_sales_raw).replace("~", ""))
                if ms:
                    monthly_sales = _safe_float(ms.group(0))
            # Monthly revenue
            monthly_revenue = _safe_float(
                metrics.get("月销售额") or metrics.get("月均销售额") or metrics.get("月均销售额($)")
            )
            # Rating: may be "4.6★★★★" or "4.4(235)" format
            rating_raw = str(metrics.get("评分") or "")
            rating = None
            reviews_total = None
            if rating_raw:
                m = _re.match(r"([\d.]+)", rating_raw)
                if m:
                    rating = float(m.group(1))
                m2 = _re.search(r"\((\d+)\)", rating_raw)
                if m2:
                    reviews_total = int(m2.group(1))
            # Reviews: try dedicated column if not in rating field
            if reviews_total is None:
                reviews_raw = metrics.get("评论数")
                if reviews_raw:
                    reviews_total_f = _safe_float(str(reviews_raw).replace("条", "").split("（")[0].split("(")[0])
                    if reviews_total_f:
                        reviews_total = int(reviews_total_f)

            # Competitiveness: factor in reviews, sales, and rating
            comp_star = _competitiveness(rating, reviews_total, monthly_sales)

            rows.append({
                "asin": asin,
                "title": str(metrics.get("核心卖点") or metrics.get("产品类型") or "")[:60],
                "brand": metrics.get("品牌") or "—",
                "price": price,
                "rating": rating,
                "reviews_total": int(reviews_total) if reviews_total else None,
                "est_monthly_sales": int(monthly_sales) if monthly_sales else None,
                "monthly_revenue": monthly_revenue,
                "competitiveness": comp_star,
                # Excel enriched fields
                "store": metrics.get("店铺") or metrics.get("卖家"),
                "launch_date": metrics.get("上架时间"),
                "category": metrics.get("类目") or metrics.get("产品类型"),
            })
    # ── Also add products NOT covered by competitor analysis ──
    covered_asins = {r["asin"] for r in rows}
    excel_data = state.get("excel_data", {})
    if not excel_comp or covered_asins:
        for p in state.get("products", []):
            prod = p.get("product") or {}
            asin = prod.get("asin") or p.get("asin")
            if asin in covered_asins:
                continue
            price = _g(prod, "price", "value") or _g(prod, "buybox_winner", "price", "value")
            rating = prod.get("rating")
            reviews_total = prod.get("ratings_total") or prod.get("reviews_total")
            bought_past_month = prod.get("bought_past_month")
            est_monthly = bought_past_month or (int(reviews_total) * 2 if reviews_total else None)
            # Try to get extra fields from raw excel_data
            raw = excel_data.get(asin, {})
            rows.append({
                "asin": asin,
                "title": (raw.get("product_type") or raw.get("产品类型") or prod.get("title") or "")[:60],
                "brand": prod.get("brand") or "—",
                "price": price,
                "rating": rating,
                "reviews_total": int(reviews_total) if reviews_total else None,
                "est_monthly_sales": int(est_monthly) if est_monthly else None,
                "competitiveness": _competitiveness(rating, reviews_total, est_monthly),
                "launch_date": raw.get("launch_date") or raw.get("上架时间"),
                "category": raw.get("product_subtype") or raw.get("product_type") or raw.get("产品类型") or raw.get("类型细分"),
            })
            covered_asins.add(asin)

    # heat matrix per keyword
    heat = {}
    for kw, m in state.get("market", {}).items():
        heat[kw] = {
            "热度": m.get("rating", "—"),
            "价格区间": f"${m.get('price_min', '-')}-${m.get('price_max', '-')}" if m.get("price_min") else f"均价 ${m.get('price_median', '-')}",
            "竞争激烈度": "★★★★" if (m.get("review_sum_top20") or 0) > 20000 else "★★★",
        }

    if cb: cb("competition", 60)
    return {"competition": {"rows": rows, "heat": heat}}
