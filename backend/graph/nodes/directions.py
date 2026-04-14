"""Generate 3 product launch directions using Kimi - evidence-based."""
import json, re
from ..state import GraphState
from ...llm import chat as _llm


SYSTEM = """你是一名拥有10年经验的亚马逊跨境品类操盘手。
你要给卖家设计可立即让工厂打样的差异化新品方向。

核心原则：
1. 严格基于给定数据推理，禁止编造数字
2. 禁止空泛词（"也许""可能""高质量""性价比高"）
3. 每个方向必须落在可执行的价格带内
4. 改良点要具体到零部件和工艺，工厂看得懂
5. 数据不足就减少方向数量，不猜测"""

SCHEMA = """输出 JSON 数组(2-3 个方向)，按优先级 gold→silver→bronze 排列。每项字段:
{
  "name": "差异化方向命名(8-16字，含核心卖点)",
  "positioning": "一两句话说清楚：卖给谁、解决什么痛点、和竞品有什么不同",
  "target_user": "目标人群",
  "target_price": 数字USD,
  "monthly_sales_target": "月销目标，参考竞品实际数据",
  "market_opportunity": "为什么这个方向有机会(两三句话)",
  "evidence": ["支撑这个方向的关键数据点，自然表达即可"],
  "improvements": ["关键改良点，写清零部件+变更+成本影响，只写最重要的"],
  "cost_estimate": "成本和毛利预估，一句话",
  "risks": ["主要风险"],
  "next_step": "建议的下一步行动(一句话，如「1688找xx供应商，重点对比xx结构」)",
  "priority": "gold" | "silver" | "bronze"
}
只输出 JSON 数组，不要解释、不要 markdown 代码块。"""

FEW_SHOT_DIR = """示例(供格式参考，与本次任务无关):
[{"name":"4000mAh·双模充电·IP67户外工作灯","positioning":"针对户外施工和露营场景，解决现有产品续航不足和防水差的核心痛点。通过大容量电池+Type-C/太阳能双模充电，覆盖8小时以上连续使用需求，填补$30-50价格带的IP67防水空白。","target_user":"美西户外施工队和露营爱好者","target_price":39.99,"monthly_sales_target":"800-1200","market_opportunity":"当前$30-50价格带仅有3款IP67产品，月总销量5200件，但差评集中在续航(频次7)和防水(频次5)，存在明显改良空间。","evidence":["竞品B0CYWSWZ71月销4876件但评分4.3，7条差评提到过热","$30-50价格带IP67产品仅3款，市场渗透率12%","差评中电池续航问题频次最高(7次)"],"improvements":["电池容量从2000mAh升至4000mAh，成本+$3","增加Type-C快充口(2小时充满)，成本+$0.8","外壳从ABS改为PC+铝合金，成本+$2","密封圈升级为双层硅胶O-ring(IP67)，成本+$0.5","增加磁吸底座(N52钕磁铁)，成本+$1.2"],"cost_estimate":"产品成本预估$14(1688报价含电池)，FBA成本$7.5，售价$39.99，毛利率约32%","risks":["大容量电池增加重量150g，可能影响便携性评分","IP67认证需3-4周检测周期，延迟上架时间"],"priority":"gold"}]"""


def directions_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb: cb("directions", 90)

    market = state.get("market", {})
    pricing = state.get("pricing", {})
    bad = state.get("bad_reviews", {})
    top10 = bad.get("top10", [])
    keyword_data = state.get("keyword_analysis", [])
    profit_data = state.get("profit_calc", [])
    src_conclusions = state.get("source_conclusions", [])

    # Compact context to keep prompt focused
    market_brief = {k: {
        "price_median": v.get("price_median"),
        "sales_band": v.get("sales_band"),
        "rating": v.get("rating"),
        "trend": v.get("trend"),
        "return_rate": v.get("return_rate"),
        "brand_concentration": v.get("brand_concentration"),
    } for k, v in market.items()}

    pricing_brief = {k: {
        "entry_price": v.get("entry_price") or v.get("sell_price_usd"),
        "entry_range": v.get("entry_range"),
        "target_cost_max": v.get("target_cost_max"),
        "product_cost_cny": v.get("product_cost_cny"),
        "margin_rate": v.get("margin_rate"),
        "source": v.get("source"),
    } for k, v in pricing.items()}

    pain_brief = [
        {"issue": p.get("issue"), "freq": p.get("frequency"),
         "dim": p.get("dimension"), "severity": p.get("severity"),
         "suggestion": p.get("suggestion")}
        for p in top10[:10]
    ]

    # Build extra context from Excel analysis sheets
    extra_sections = ""
    if keyword_data:
        kw_brief = json.dumps(keyword_data[:10], ensure_ascii=False, default=str)[:2000]
        extra_sections += f"\n\n# 关键词数据（来自Excel）\n{kw_brief}"
    if src_conclusions:
        extra_sections += f"\n\n# 已有分析结论（来自Excel，仅供参考）\n" + "\n".join(src_conclusions[:10])

    # Inject competitor deep analysis for better direction design
    comp_analysis = state.get("competitor_analysis", {})
    if comp_analysis:
        comp_parts = []
        for asin, metrics in comp_analysis.items():
            brand = metrics.get("品牌") or asin
            parts = [f"## {brand}({asin})"]
            for field in ["产品类型", "卖点1", "卖点2", "卖点3",
                          "差评关键词Top3", "关键改进机会", "我方差异化方向",
                          "建议进入价格带", "核心竞争壁垒", "最大弱项",
                          "主要买家群体", "消费场景"]:
                val = metrics.get(field)
                if val:
                    parts.append(f"{field}: {str(val)[:150]}")
            comp_parts.append("\n".join(parts))
        extra_sections += f"\n\n# 竞品深度分析\n" + "\n\n".join(comp_parts)

    # Inject profit calculation data
    profit_calc = state.get("profit_calc", [])
    if profit_calc:
        extra_sections += f"\n\n# 利润测算方案\n{json.dumps(profit_calc[:5], ensure_ascii=False, default=str)[:1500]}"

    user_msg = (
        f"# 任务\n基于以下数据，输出 2-3 个差异化新品方向。每个方向需要有深度分析，不要泛泛而谈。\n\n"
        f"# 市场数据\n{json.dumps(market_brief, ensure_ascii=False, indent=2)}\n\n"
        f"# 价格与利润\n{json.dumps(pricing_brief, ensure_ascii=False, indent=2)}\n"
        f"利润率约束: {int(state.get('target_margin',0.3)*100)}% , FBA 费率: {int(state.get('fee_rate',0.3)*100)}%\n\n"
        f"# TOP差评痛点\n{json.dumps(pain_brief, ensure_ascii=False, indent=2)}\n"
        f"{extra_sections}\n\n"
        f"# 推理要求\n"
        f"1. 每个方向必须有差异(价格档/人群/卖点)，避免互相重叠\n"
        f"2. 所有数字必须来自上面的数据，不能虚构\n"
        f"3. target_price 必须落在市场入场价区间内\n"
        f"4. improvements 必须可被工厂理解为打样需求\n"
        f"5. gold=最优解，silver=稳健备选，bronze=高风险高回报\n\n"
        f"# 格式示例（仅供参考格式，内容基于你的数据）\n{FEW_SHOT_DIR}\n\n"
        f"# 输出格式\n{SCHEMA}"
    )

    raw = _llm(user_msg, max_tokens=3500, temperature=0.3, system=SYSTEM) or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    directions: list[dict] = []
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            directions = json.loads(m.group(0))
        except Exception as e:
            print("[directions JSON parse fail]", e, raw[:200])
            directions = []

    # fallback
    if not directions:
        kws = state["keywords"][:3] or ["主方向"]
        for i, kw in enumerate(kws):
            pr = pricing.get(kw, {})
            directions.append({
                "name": f"方向{i+1}: {kw} 升级款",
                "positioning": f"针对 {kw} 市场差评点优化",
                "target_user": "—",
                "target_price": pr.get("entry_price") or 0,
                "monthly_sales_target": "1000+",
                "evidence": [b.get("issue", "—") for b in top10[:3]],
                "improvements": [b.get("suggestion") or b.get("issue", "—") for b in top10[:6]] or ["—"],
                "risks": ["数据样本不足"],
                "priority": ["gold", "silver", "bronze"][i % 3],
            })

    conclusion = [
        {
            "medal": {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}.get(d.get("priority", "bronze"), "•"),
            "direction": d.get("name", "—"),
            "reason": d.get("positioning", "—"),
            "target_price": f"${d.get('target_price','—')}",
            "next_step": d.get("next_step") or "打样验证 → 1688 询价 → MOQ 测试单",
        }
        for d in directions
    ]
    if cb: cb("directions", 95)
    return {"directions": {"items": directions}, "conclusion": conclusion}
