"""Pure data analytics computed from excel_data for report enrichment.
No LLM calls, no side effects — just aggregation on product dicts."""

from datetime import datetime, timedelta
from statistics import median
from collections import Counter
from typing import Any, Dict, List, Optional


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(
            str(v).replace(",", "").replace("$", "").replace("¥", "")
            .replace("%", "").replace("元", "").replace("约", "")
            .replace("~", "").replace("个", "").replace("单", "").strip()
        )
    except (ValueError, TypeError):
        return None


def _products_list(excel_data: dict) -> list:
    """Convert excel_data {asin: {...}} to list, filtering empty entries."""
    return [p for p in excel_data.values() if isinstance(p, dict) and p.get("asin")]


# ─────────────────────────────────────────────
# 1. Category Overview
# ─────────────────────────────────────────────
def compute_category_overview(excel_data: dict) -> dict:
    """Aggregate high-level category KPIs from all products."""
    products = _products_list(excel_data)
    if not products:
        return {}

    prices = [p for p in (_safe_float(x.get("price")) for x in products) if p and p > 0]
    ratings = [p for p in (_safe_float(x.get("rating")) for x in products) if p and 0 < p <= 5]
    reviews = [p for p in (_safe_float(x.get("ratings_total")) for x in products) if p is not None]
    sales = [p for p in (_safe_float(x.get("monthly_sales")) for x in products) if p is not None]
    revenues = [p for p in (_safe_float(x.get("monthly_revenue")) for x in products) if p is not None]

    # FBA ratio
    fba_count = sum(1 for x in products if "FBA" in str(x.get("fulfillment", "")).upper())
    # Chinese seller ratio
    cn_keywords = ("CN", "China", "中国", "深圳", "广州", "东莞", "义乌", "杭州", "上海", "北京", "福建", "浙江", "广东")
    cn_count = sum(1 for x in products if any(kw in str(x.get("seller_location", "")) for kw in cn_keywords))
    # New product ratio (launched within 12 months)
    now = datetime.now()
    new_count = 0
    for x in products:
        ld = x.get("launch_date")
        if ld:
            try:
                if isinstance(ld, datetime):
                    dt = ld
                else:
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y", "%Y-%m"):
                        try:
                            dt = datetime.strptime(str(ld).strip()[:10], fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        continue
                if (now - dt).days < 365:
                    new_count += 1
            except Exception:
                pass

    n = len(products)
    return {
        "total_products": n,
        "total_gmv": round(sum(revenues), 0) if revenues else None,
        "total_sales": round(sum(sales), 0) if sales else None,
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "median_price": round(median(prices), 2) if prices else None,
        "min_price": round(min(prices), 2) if prices else None,
        "max_price": round(max(prices), 2) if prices else None,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "avg_reviews": round(sum(reviews) / len(reviews), 0) if reviews else None,
        "fba_pct": round(fba_count / n * 100, 1) if n else 0,
        "cn_seller_pct": round(cn_count / n * 100, 1) if n else 0,
        "new_product_pct": round(new_count / n * 100, 1) if n else 0,
    }


# ─────────────────────────────────────────────
# 2. Brand Concentration
# ─────────────────────────────────────────────
def compute_brand_concentration(excel_data: dict) -> dict:
    """Top brands by product count and revenue, plus CR5."""
    products = _products_list(excel_data)
    if not products:
        return {}

    brand_data: Dict[str, dict] = {}
    for p in products:
        brand = str(p.get("brand") or "Unknown").strip()
        if brand in ("—", "", "None"):
            brand = "Unknown"
        if brand not in brand_data:
            brand_data[brand] = {"count": 0, "prices": [], "revenue": 0, "sales": 0}
        brand_data[brand]["count"] += 1
        price = _safe_float(p.get("price"))
        if price:
            brand_data[brand]["prices"].append(price)
        rev = _safe_float(p.get("monthly_revenue"))
        if rev:
            brand_data[brand]["revenue"] += rev
        sal = _safe_float(p.get("monthly_sales"))
        if sal:
            brand_data[brand]["sales"] += sal

    n = len(products)
    # Sort by count descending
    sorted_brands = sorted(brand_data.items(), key=lambda x: x[1]["revenue"] or x[1]["count"], reverse=True)

    top10 = []
    for brand, d in sorted_brands[:10]:
        avg_p = round(sum(d["prices"]) / len(d["prices"]), 2) if d["prices"] else None
        top10.append({
            "brand": brand,
            "count": d["count"],
            "pct": round(d["count"] / n * 100, 1),
            "avg_price": avg_p,
            "total_revenue": round(d["revenue"], 0) if d["revenue"] else None,
            "total_sales": round(d["sales"], 0) if d["sales"] else None,
        })

    # CR5
    top5_count = sum(d["count"] for _, d in sorted_brands[:5])
    cr5 = round(top5_count / n * 100, 1) if n else 0

    # Seller location distribution
    loc_counter: Counter = Counter()
    for p in products:
        loc = str(p.get("seller_location") or "").strip()
        if not loc or loc in ("—", "None"):
            loc = "未知"
        # Simplify to country-level
        cn_keywords = ("CN", "China", "中国", "深圳", "广州", "东莞", "义乌", "杭州", "上海", "北京", "福建", "浙江", "广东")
        us_keywords = ("US", "USA", "United States", "美国")
        if any(kw in loc for kw in cn_keywords):
            loc_counter["中国"] += 1
        elif any(kw in loc for kw in us_keywords):
            loc_counter["美国"] += 1
        else:
            loc_counter[loc[:10]] += 1

    seller_distribution = [
        {"location": loc, "count": cnt, "pct": round(cnt / n * 100, 1)}
        for loc, cnt in loc_counter.most_common(5)
    ] if n else []

    return {
        "top10_brands": top10,
        "cr5": cr5,
        "concentration_level": "高度集中" if cr5 > 60 else "中度集中" if cr5 > 40 else "分散竞争",
        "seller_distribution": seller_distribution,
    }


# ─────────────────────────────────────────────
# 3. Price Distribution
# ─────────────────────────────────────────────
PRICE_TIERS = [
    (0, 15, "$0-15"),
    (15, 30, "$15-30"),
    (30, 50, "$30-50"),
    (50, 80, "$50-80"),
    (80, 120, "$80-120"),
    (120, 99999, "$120+"),
]


def compute_price_distribution(excel_data: dict) -> list:
    """Distribute products into price tiers with stats per tier."""
    products = _products_list(excel_data)
    if not products:
        return []

    n = len(products)
    result = []
    best_tier = None
    best_sales = -1

    for low, high, label in PRICE_TIERS:
        tier_products = [
            p for p in products
            if (price := _safe_float(p.get("price"))) is not None and low <= price < high
        ]
        count = len(tier_products)
        if count == 0:
            continue

        tier_sales = [s for s in (_safe_float(p.get("monthly_sales")) for p in tier_products) if s is not None]
        tier_ratings = [r for r in (_safe_float(p.get("rating")) for p in tier_products) if r and 0 < r <= 5]
        avg_sales = round(sum(tier_sales) / len(tier_sales), 0) if tier_sales else None
        avg_rating = round(sum(tier_ratings) / len(tier_ratings), 2) if tier_ratings else None

        # Representative brand (most common in tier)
        brands = [str(p.get("brand", "")) for p in tier_products if p.get("brand") and str(p.get("brand")) not in ("—", "", "None")]
        rep_brand = Counter(brands).most_common(1)[0][0] if brands else "—"

        total_tier_sales = sum(tier_sales) if tier_sales else 0
        if total_tier_sales > best_sales:
            best_sales = total_tier_sales
            best_tier = label

        result.append({
            "tier": label,
            "count": count,
            "pct": round(count / n * 100, 1),
            "avg_sales": avg_sales,
            "avg_rating": avg_rating,
            "representative_brand": rep_brand,
            "total_sales": round(total_tier_sales, 0) if total_tier_sales else None,
        })

    # Mark sweet spot
    for r in result:
        r["is_sweet_spot"] = (r["tier"] == best_tier)

    return result


# ─────────────────────────────────────────────
# 4. Rating Distribution
# ─────────────────────────────────────────────
RATING_BANDS = [
    (0, 3.0, "0-3.0"),
    (3.0, 3.5, "3.0-3.5"),
    (3.5, 4.0, "3.5-4.0"),
    (4.0, 4.5, "4.0-4.5"),
    (4.5, 5.01, "4.5-5.0"),
]


def compute_rating_distribution(excel_data: dict) -> list:
    """Distribute products by rating bands."""
    products = _products_list(excel_data)
    if not products:
        return []

    rated = [(p, _safe_float(p.get("rating"))) for p in products]
    rated = [(p, r) for p, r in rated if r is not None and 0 < r <= 5]
    if not rated:
        return []

    n = len(rated)
    result = []
    for low, high, label in RATING_BANDS:
        band = [(p, r) for p, r in rated if low <= r < high]
        count = len(band)
        if count == 0:
            continue
        prices = [pr for pr in (_safe_float(p.get("price")) for p, _ in band) if pr]
        sales = [s for s in (_safe_float(p.get("monthly_sales")) for p, _ in band) if s is not None]
        result.append({
            "band": label,
            "count": count,
            "pct": round(count / n * 100, 1),
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_sales": round(sum(sales) / len(sales), 0) if sales else None,
        })
    return result


# ─────────────────────────────────────────────
# 5. Review Count Distribution
# ─────────────────────────────────────────────
REVIEW_BANDS = [
    (0, 50, "0-50"),
    (50, 200, "50-200"),
    (200, 500, "200-500"),
    (500, 2000, "500-2000"),
    (2000, 5000, "2000-5000"),
    (5000, 999999, "5000+"),
]


def compute_review_distribution(excel_data: dict) -> list:
    """Distribute products by review count bands."""
    products = _products_list(excel_data)
    if not products:
        return []

    reviewed = [(p, _safe_float(p.get("ratings_total"))) for p in products]
    reviewed = [(p, int(r)) for p, r in reviewed if r is not None]
    if not reviewed:
        return []

    n = len(reviewed)
    result = []
    for low, high, label in REVIEW_BANDS:
        band = [(p, r) for p, r in reviewed if low <= r < high]
        count = len(band)
        if count == 0:
            continue
        prices = [pr for pr in (_safe_float(p.get("price")) for p, _ in band) if pr]
        sales = [s for s in (_safe_float(p.get("monthly_sales")) for p, _ in band) if s is not None]
        result.append({
            "band": label,
            "count": count,
            "pct": round(count / n * 100, 1),
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_sales": round(sum(sales) / len(sales), 0) if sales else None,
        })
    return result


# ─────────────────────────────────────────────
# 6. Launch Date Analysis
# ─────────────────────────────────────────────
def compute_launch_analysis(excel_data: dict) -> dict:
    """Analyze product age distribution."""
    products = _products_list(excel_data)
    if not products:
        return {}

    now = datetime.now()
    ages = []
    by_year: Counter = Counter()

    for p in products:
        ld = p.get("launch_date")
        if not ld:
            continue
        try:
            if isinstance(ld, datetime):
                dt = ld
            else:
                dt = None
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y", "%Y-%m"):
                    try:
                        dt = datetime.strptime(str(ld).strip()[:10], fmt)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    continue
            age_days = (now - dt).days
            if age_days < 0:
                continue
            ages.append(age_days)
            by_year[dt.year] += 1
        except Exception:
            pass

    if not ages:
        return {}

    new_count = sum(1 for a in ages if a < 365)
    return {
        "total_with_date": len(ages),
        "new_pct": round(new_count / len(ages) * 100, 1),
        "avg_age_days": round(sum(ages) / len(ages), 0),
        "by_year": sorted([{"year": y, "count": c} for y, c in by_year.items()], key=lambda x: x["year"], reverse=True),
    }


# ─────────────────────────────────────────────
# 7. Profit Scenarios
# ─────────────────────────────────────────────
def compute_profit_scenarios(pricing: dict, market: dict) -> list:
    """Normalize profit scenarios. If Excel profit data exists, return it;
    otherwise auto-generate 3 tiers from market median price."""
    scenarios = []

    # Check if pricing has Excel profit data
    excel_items = [(k, v) for k, v in pricing.items() if v.get("source") == "Excel 利润核算"]
    if excel_items:
        for label, p in excel_items:
            scenarios.append({
                "scenario": label,
                "sell_price": p.get("sell_price_usd"),
                "product_cost": p.get("product_cost_cny"),
                "shipping_cost": p.get("shipping_cost_cny"),
                "fba_cost": p.get("fba_total_usd"),
                "ad_cost": p.get("ad_cost_usd"),
                "gross_profit": p.get("gross_profit_cny"),
                "margin": p.get("margin_rate"),
                "source": "Excel",
            })
        return scenarios

    # Auto-generate 3 scenarios from median price
    medians = [v.get("price_median") for v in market.values() if v.get("price_median")]
    if not medians:
        return []

    med = median(medians)
    tiers = [
        ("低价走量款", 0.65, 0.08, "1500-2000"),
        ("主流利润款", 1.0, 0.10, "800-1200"),
        ("中高端差异款", 1.4, 0.12, "400-600"),
    ]

    for name, ratio, ad_rate, monthly_target in tiers:
        sell = round(med * ratio, 2)
        fba_est = round(sell * 0.30, 2)
        ad_est = round(sell * ad_rate, 2)
        product_cost_est = round(sell * 0.25, 2)
        gross = round(sell - fba_est - ad_est - product_cost_est, 2)
        margin = round(gross / sell * 100, 1) if sell else 0
        scenarios.append({
            "scenario": name,
            "sell_price": sell,
            "product_cost": product_cost_est,
            "shipping_cost": None,
            "fba_cost": fba_est,
            "ad_cost": ad_est,
            "gross_profit": gross,
            "margin": f"{margin}%",
            "monthly_target": monthly_target,
            "source": "基于中位价估算",
        })

    return scenarios


# ─────────────────────────────────────────────
# 8. Keyword Table
# ─────────────────────────────────────────────
# Common column name mappings for keyword analysis sheets
_KW_FIELD_MAP = {
    "关键词": "keyword", "搜索词": "keyword", "Keyword": "keyword",
    "月搜索量": "search_volume", "月搜索": "search_volume",
    "Monthly Search Volume": "search_volume", "搜索量": "search_volume",
    "月购买量": "purchase_volume", "Monthly Purchases": "purchase_volume",
    "转化率": "conversion_rate", "Conversion Rate": "conversion_rate",
    "点击集中度": "click_concentration",
    "CPC(精准)": "cpc_exact", "CPC精准": "cpc_exact",
    "CPC(广泛)": "cpc_broad", "CPC广泛": "cpc_broad",
    "竞争度": "competition", "Competition": "competition",
    "推荐星级": "stars", "推荐": "stars",
    "Top ASIN": "top_asin", "头部ASIN": "top_asin",
    "趋势": "trend", "Trend": "trend",
    "数据来源": "source",
}


def compute_keyword_table(keyword_analysis: list) -> list:
    """Normalize keyword analysis rows into a standard format."""
    if not keyword_analysis:
        return []

    result = []
    for row in keyword_analysis:
        if not isinstance(row, dict):
            continue
        normalized = {}
        for orig_key, val in row.items():
            mapped = _KW_FIELD_MAP.get(orig_key)
            if mapped:
                normalized[mapped] = val
            else:
                # Keep unmapped fields as-is
                normalized[orig_key] = val

        # Must have keyword field
        kw = normalized.get("keyword")
        if not kw or str(kw).strip() in ("", "None"):
            continue

        result.append(normalized)

    return result
