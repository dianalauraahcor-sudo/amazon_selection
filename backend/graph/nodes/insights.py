"""Generate strategic insights by LLM — synthesize market/competition/pricing/pain data.
All insights must be 100% grounded in provided data, no fabrication."""
import json, re
from ..state import GraphState
from ...llm import chat as _llm


SYSTEM = """你是一名资深亚马逊跨境电商选品顾问，拥有10年品类操盘经验。
你的读者是准备入场的卖家决策者，他们需要的是精炼、可执行的结论。

核心原则：
1. 严格基于给定数据推理，禁止编造
2. 每条洞察必须包含具体数字。差的写法："市场增长中"。好的写法："rechargeable work light月搜38369、转化4.17%，高于类目均值，供需缺口明显"
3. 每条洞察必须有明确结论。差的写法："这个价格带值得关注"。好的写法："$29-35价格带暂无4.6星以上爆款，存在高评分+低价穿透窗口"
4. 引用竞品时必须带ASIN或品牌名+具体数据。差的写法："头部竞品月销较高"。好的写法："B0CYWSWZ71(Zetunlo)月销2790但依赖有线，充电版空白"
5. 只写值得说的洞察，不凑数。一条有深度的结论胜过五条废话
6. 数据不足就直接说，不要勉强凑结论"""

SCHEMA = """输出 JSON 对象：
{
  "executive_summary": "给决策者的一段话总结(150-200字)，涵盖这个品类值不值得做、主要机会在哪、最大风险是什么。不要分段标记，自然行文。",

  "market_insights": [
    "写出你从数据中发现的最值得关注的市场信号，不限条数，每条一两句话。",
    "比如：某个关键词搜索量大但竞品少、某个价格带是空白、新品增长信号等。",
    "不重要的维度不要写，没有发现就不写。"
  ],

  "competition_insights": [
    "按竞争激烈程度给出判断，不限条数，每条一两句话。",
    "比如：某个细分赛道竞争激烈（评论>500，头部占位），某个细分赛道有机会（新品多，评论少）。",
    "重点是告诉卖家哪里能打、哪里要避开。"
  ],

  "pricing_insights": [
    "给出可直接执行的定价策略建议，不限条数。",
    "比如：推荐入场价区间及理由、Coupon策略、新品期定价策略、大促定价技巧等。",
    "不要分析成本结构，卖家自己清楚成本。"
  ],

  "keyword_strategy": [
    "基于关键词数据给出投放策略建议，1-3条。",
    "比如：核心词/长尾词分层、预算分配、CPC出价建议等。",
    "没有关键词数据时此字段返回空数组。"
  ],

  "category_summary": "类目总结(200-300字)，综合评估该类目的机会等级(高/中/低)，明确推荐进入的细分方向、建议价格带、最佳上架时机。像给老板写决策备忘录。没有足够数据时写空字符串。"
}
只输出 JSON，不要解释、不要 markdown 代码块。"""


def insights_node(state: GraphState) -> dict:
    cb = state.get("on_progress")
    if cb: cb("insights", 87)

    market = state.get("market", {})
    competition = state.get("competition", {})
    pricing = state.get("pricing", {})
    bad_reviews = state.get("bad_reviews", {})
    market_analysis = state.get("market_analysis", [])
    category_trends = state.get("category_trends", [])
    source_conclusions = state.get("source_conclusions", [])
    keyword_analysis = state.get("keyword_analysis", [])

    # Build rich data context
    sections = []

    if market:
        sections.append(f"# 市场数据\n{json.dumps(market, ensure_ascii=False, default=str)[:3000]}")

    market_overview = state.get("market_overview", {})
    if market_overview:
        sections.append(f"# 市场概览指标\n{json.dumps(market_overview, ensure_ascii=False, default=str)}")

    market_trends = state.get("market_trends", [])
    if market_trends:
        trends_text = json.dumps(market_trends[:12], ensure_ascii=False, default=str)[:3000]
        sections.append(f"# 月度趋势数据\n{trends_text}")

    comp_rows = competition.get("rows", [])
    if comp_rows:
        comp_brief = [{"asin": r.get("asin"), "brand": r.get("brand"), "price": r.get("price"),
                        "rating": r.get("rating"), "monthly_sales": r.get("est_monthly_sales"),
                        "monthly_revenue": r.get("monthly_revenue"),
                        "rank": r.get("rank"), "store": r.get("store"),
                        "fulfillment": r.get("fulfillment"),
                        "competitiveness": r.get("competitiveness")}
                       for r in comp_rows[:10]]
        sections.append(f"# 竞品数据（{len(comp_rows)}个）\n{json.dumps(comp_brief, ensure_ascii=False, default=str)}")

    if pricing:
        sections.append(f"# 定价与利润\n{json.dumps(pricing, ensure_ascii=False, default=str)[:2000]}")

    top10 = bad_reviews.get("top10", [])
    if top10:
        pain_brief = [{"issue": p.get("issue"), "freq": p.get("frequency"),
                        "severity": p.get("severity"), "dimension": p.get("dimension"),
                        "suggestion": p.get("suggestion")}
                       for p in top10]
        sections.append(f"# TOP差评痛点（{len(top10)}项）\n{json.dumps(pain_brief, ensure_ascii=False)}")

    if market_analysis:
        ma_text = "\n".join(str(t) for t in market_analysis[:20])[:3000]
        sections.append(f"# Excel市场深度分析\n{ma_text}")

    if category_trends:
        sections.append(f"# 类目趋势\n" + "\n".join(str(t) for t in category_trends[:10]))

    if source_conclusions:
        sections.append(f"# Excel已有结论（仅供参考）\n" + "\n".join(str(c) for c in source_conclusions[:10]))

    if keyword_analysis:
        kw_brief = json.dumps(keyword_analysis[:15], ensure_ascii=False, default=str)[:3000]
        sections.append(f"# 关键词分析数据\n{kw_brief}")

    # Inject competitor deep analysis data
    comp_analysis = state.get("competitor_analysis", {})
    if comp_analysis:
        comp_deep = []
        for asin, metrics in comp_analysis.items():
            brand = metrics.get("品牌") or asin
            entry = f"## {brand} ({asin})"
            for field in ["产品类型", "供电方式", "亮度", "防水等级",
                          "好评关键词Top3", "差评关键词Top3", "关键改进机会",
                          "核心竞争壁垒", "最大弱项", "我方差异化方向",
                          "建议进入价格带", "主要买家群体", "核心购买动机",
                          "价格敏感度", "消费场景", "市场进入难度"]:
                val = metrics.get(field)
                if val:
                    entry += f"\n{field}: {str(val)[:200]}"
            comp_deep.append(entry)
        sections.append(f"# 竞品深度分析（{len(comp_analysis)}个）\n" + "\n\n".join(comp_deep))

    if not sections:
        return {"insights": _empty_insights()}

    user_msg = (
        f"# 任务\n基于以下数据，生成深度选品战略洞察。请确保每条洞察有实质内容，不要泛泛而谈。\n\n"
        + "\n\n".join(sections)
        + f"\n\n# 输出格式\n{SCHEMA}"
    )

    raw = _llm(user_msg, max_tokens=3000, temperature=0.3, system=SYSTEM) or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)

    insights = {}
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            insights = json.loads(m.group(0))
        except Exception as e:
            print("[insights JSON parse fail]", e, raw[:200])

    if not insights or not insights.get("executive_summary"):
        insights = _empty_insights()

    if cb: cb("insights", 89)
    return {"insights": insights}


def _empty_insights() -> dict:
    return {
        "executive_summary": "",
        "market_insights": [],
        "competition_insights": [],
        "pricing_insights": [],
        "keyword_strategy": [],
        "category_summary": "",
    }
