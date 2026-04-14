"""Aggregate critical reviews and use Kimi to extract TOP10 pain points."""
import json, re
from collections import Counter
from ..state import GraphState
from ...llm import chat



SYSTEM = """你是一名资深亚马逊选品分析师，从英文差评中提炼产品痛点。

核心原则：
1. 严格基于评论原文，禁止编造
2. 痛点命名要精准具体（"电池续航不足2小时"而非"电池问题"）
3. 改良建议要具体到零部件/材料/工艺，工厂能看懂
4. 有多少真实痛点写多少，不凑数"""

SCHEMA_HINT = """输出 JSON 对象：

{
  "overall_summary": "差评整体分析(100字左右)：最严重的问题、共性根因、对选品的启示。",

  "items": [
    {
      "rank": 序号,
      "issue": "精准命名痛点(8-16字)",
      "frequency": 出现次数,
      "dimension": "质量耐久" | "核心功能" | "使用体验" | "物流包装" | "外观做工" | "售后保修",
      "severity": "高" | "中" | "低",
      "typical_quote": "最具代表性的英文原句(不超30词)",
      "root_cause": "根本原因分析，说清楚即可，不限字数",
      "suggestion": "改良建议，具体到零部件/工艺，不限字数",
      "feasibility": "低" | "中" | "高"
    }
  ]
}
按 frequency 从高到低排序。只输出 JSON。"""

FEW_SHOT = """示例(供格式参考):
{
  "overall_summary": "23条差评中过热问题最突出(7次)，其次是做工粗糙(5次)。共性根因是散热设计不足+ABS外壳导热差。选品时优先解决散热。",
  "items": [
    {"rank":1,"issue":"开机10分钟即过热","frequency":7,"dimension":"质量耐久","severity":"高",
     "typical_quote":"After 10 minutes the housing got too hot to touch safely",
     "root_cause":"ABS外壳导热系数仅0.2W/mK，散热鳍片面积不足，连续工作时内部温度超65°C",
     "suggestion":"外壳改铝合金+鳍片面积增30%，成本+$1.5，过热投诉预计降80%",
     "feasibility":"中"}
  ]
}"""


def _llm_summarize(text_blob: str, keywords: list[str]) -> dict:
    """Returns {"overall_summary": str, "items": list} or empty."""
    if not text_blob.strip():
        return {}
    user_msg = (
        f"# 任务\n品类关键词: {', '.join(keywords)}\n"
        f"以下是 {text_blob.count('---')+1} 条 1-4 星评论原文(用 --- 分隔)。\n"
        f"请系统分析这些差评，提炼高频痛点并给出整体总结。\n\n"
        f"# 输出格式\n{SCHEMA_HINT}\n\n{FEW_SHOT}\n\n"
        f"# 评论原文\n{text_blob[:20000]}"
    )
    raw = chat(user_msg, max_tokens=4000, temperature=0.2, system=SYSTEM)
    if not raw:
        return {}
    # strip code fences if any
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    # Try parsing as dict first (new format with overall_summary + items)
    m_obj = re.search(r"\{.*\}", raw, re.S)
    if m_obj:
        try:
            result = json.loads(m_obj.group(0))
            if isinstance(result, dict) and "items" in result:
                return result
        except Exception:
            pass
    # Fallback: try parsing as array (old format)
    m_arr = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(m_arr.group(0)) if m_arr else []
        return {"overall_summary": "", "items": items}
    except Exception as e:
        print("[bad_reviews JSON parse fail]", e, raw[:200])
        return {}


def _fallback(reviews: list[dict]) -> list[dict]:
    words = Counter()
    keywords = ["broken", "stopped", "battery", "dim", "leak", "cheap", "flicker",
                "short", "weak", "heavy", "instructions", "charge", "hot", "loose",
                "rust", "plastic", "small", "noise", "expensive", "warranty"]
    for r in reviews:
        body = (r.get("body") or "").lower()
        for k in keywords:
            if k in body: words[k] += 1
    top = words.most_common(10)
    return [
        {"rank": i+1, "issue": k, "frequency": c, "dimension": "—",
         "severity": "中", "typical_quote": "", "root_cause": "—", "suggestion": "—"}
        for i, (k, c) in enumerate(top)
    ]


def _structured_fallback(reviews: list[dict], comp_analysis: dict) -> list[dict]:
    """Build meaningful pain points from competitor analysis + keyword counting."""
    items = []
    rank = 0

    # First: extract structured pain points from competitor analysis
    for asin, metrics in comp_analysis.items():
        neg_kw = metrics.get("差评关键词Top3") or metrics.get("差评关键词") or ""
        improvement = metrics.get("关键改进机会") or ""
        weakness = metrics.get("最大弱项") or ""
        brand = metrics.get("品牌") or asin

        if neg_kw:
            # Parse "Too Heavy(太重) / Need Power Outlet(依赖插座) / Pricey(价格偏高)"
            for part in str(neg_kw).split("/"):
                part = part.strip()
                if not part:
                    continue
                rank += 1
                # Count frequency in reviews
                search_terms = []
                if "(" in part:
                    eng = part[:part.index("(")].strip().lower()
                    search_terms = eng.split()
                else:
                    search_terms = part.lower().split()[:2]
                freq = 0
                for r in reviews:
                    body = (r.get("body") or "").lower()
                    if any(t in body for t in search_terms if len(t) > 3):
                        freq += 1
                items.append({
                    "rank": rank,
                    "issue": part,
                    "frequency": freq,
                    "dimension": "竞品分析",
                    "severity": "中",
                    "typical_quote": "",
                    "root_cause": weakness if rank <= 3 else "—",
                    "suggestion": improvement if rank <= 3 else "—",
                })
                if rank >= 10:
                    break
        if rank >= 10:
            break

    # If not enough from competitor analysis, supplement with keyword counting
    if rank < 10:
        words = Counter()
        kw_map = {
            "battery": "电池续航问题", "charge": "充电问题", "heavy": "重量过重",
            "dim": "亮度不足", "hot": "过热问题", "broken": "损坏/故障",
            "loose": "松动/不牢固", "noise": "噪音问题", "leak": "漏水/漏电",
            "expensive": "价格偏高", "cheap": "做工廉价", "instructions": "说明书缺失",
            "flicker": "频闪问题", "weak": "结构脆弱", "stopped": "停止工作",
        }
        for r in reviews:
            body = (r.get("body") or "").lower()
            for k in kw_map:
                if k in body:
                    words[k] += 1
        existing_issues = {it["issue"].lower() for it in items}
        for k, c in words.most_common(15):
            if rank >= 10:
                break
            if k not in existing_issues:
                rank += 1
                items.append({
                    "rank": rank, "issue": kw_map[k], "frequency": c,
                    "dimension": "评论统计", "severity": "中",
                    "typical_quote": "", "root_cause": "—", "suggestion": "—",
                })

    return items[:10]


def bad_reviews_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb: cb("bad_reviews", 78)

    # Use all uploaded reviews (user uploaded them intentionally)
    all_reviews: list[dict] = []
    for asin, revs in state.get("reviews_by_asin", {}).items():
        for r in revs:
            try:
                rating = float(r.get("rating") or 5)
            except Exception:
                rating = 5
            # Only 1-3 star reviews count as 差评
            if rating <= 3 and (r.get("body") or "").strip():
                all_reviews.append(r)

    # build blob: include rating + body, dedupe by first 80 chars
    seen = set()
    pieces = []
    for r in all_reviews:
        body = (r.get("body") or "").strip()
        key = body[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        pieces.append(f"[{r.get('rating','?')}★] {body[:600]}")
    blob = "\n---\n".join(pieces[:200])

    # Enrich blob with structured review data from competitor analysis
    comp_analysis = state.get("competitor_analysis", {})
    comp_review_context = []
    for asin, metrics in comp_analysis.items():
        neg_kw = metrics.get("差评关键词Top3") or metrics.get("差评关键词")
        pos_kw = metrics.get("好评关键词Top3") or metrics.get("好评关键词")
        improvement = metrics.get("关键改进机会")
        brand = metrics.get("品牌") or asin
        if neg_kw:
            comp_review_context.append(f"[{brand}({asin})] 差评关键词: {neg_kw}")
        if improvement:
            comp_review_context.append(f"[{brand}({asin})] 改进机会: {improvement}")

    enriched_blob = blob
    if comp_review_context:
        enriched_blob += "\n\n# 竞品分析师整理的差评关键词与改进机会\n" + "\n".join(comp_review_context)

    print(f"[bad_reviews] blob length: {len(enriched_blob)}, reviews: {len(pieces)}")
    llm_result = _llm_summarize(enriched_blob, state.get("keywords", []))

    # Retry with shorter blob if first attempt failed
    if not (llm_result and llm_result.get("items")) and len(enriched_blob) > 10000:
        print("[bad_reviews] first LLM attempt failed, retrying with shorter blob")
        shorter_blob = "\n---\n".join(pieces[:80])
        if comp_review_context:
            shorter_blob += "\n\n# 竞品差评关键词\n" + "\n".join(comp_review_context)
        llm_result = _llm_summarize(shorter_blob, state.get("keywords", []))

    if llm_result and llm_result.get("items"):
        top10 = llm_result["items"]
        overall_summary = llm_result.get("overall_summary", "")
    else:
        print("[bad_reviews] LLM failed, using structured fallback from competitor analysis")
        top10 = _structured_fallback(all_reviews, comp_analysis)
        overall_summary = ""

    # group raw samples by keyword for the report (cross-keyword dedup)
    print("[bad_reviews] === PATCHED VERSION: cross-keyword dedup active ===")
    by_kw = {}
    global_seen_asins = set()  # 跨关键词去重：同一ASIN的评论只出现在第一个匹配的关键词下
    search_by_kw = state.get("search_by_keyword", {})
    for kw in state.get("keywords", []):
        bullets = []
        kw_asins = set()
        sr = search_by_kw.get(kw, {}).get("search_results", [])
        for item in sr:
            if item.get("asin"):
                kw_asins.add(item["asin"])

        for p in state.get("products", []):
            prod = p.get("product") or {}
            asin = prod.get("asin")
            if not asin or asin not in kw_asins or asin in global_seen_asins:
                continue
            global_seen_asins.add(asin)
            revs = state.get("reviews_by_asin", {}).get(asin) or []
            def _rating_of(r):
                try:
                    return float(r.get("rating") or 5)
                except Exception:
                    return 5.0
            low = [r for r in revs if (r.get("body") or "").strip() and _rating_of(r) <= 3]
            for r in low[:3]:
                bullets.append(f"[{asin}|{r.get('rating','?')}★] " + r["body"][:160])
        by_kw[kw] = bullets[:6]

    # Collect competitor selling points vs pain points for report
    comp_comparison = []
    for asin, metrics in comp_analysis.items():
        brand = metrics.get("品牌") or asin
        product_type = metrics.get("产品类型") or ""
        selling_points = [metrics.get(f"卖点{i}") for i in range(1, 6)]
        selling_points = [s for s in selling_points if s]
        pos_kw = metrics.get("好评关键词Top3") or ""
        neg_kw = metrics.get("差评关键词Top3") or ""
        improvement = metrics.get("关键改进机会") or ""
        weakness = metrics.get("最大弱项") or ""
        if selling_points or neg_kw:
            comp_comparison.append({
                "asin": asin,
                "brand": brand,
                "product_type": product_type,
                "selling_points": selling_points,
                "positive_keywords": pos_kw,
                "negative_keywords": neg_kw,
                "improvement": improvement,
                "weakness": weakness,
            })

    if cb: cb("bad_reviews", 85)
    return {"bad_reviews": {
        "overall_summary": overall_summary,
        "top10": top10,
        "by_keyword": by_kw,
        "comp_comparison": comp_comparison,
        "total_critical": len(all_reviews),
        "unique_used": len(pieces),
    }}
