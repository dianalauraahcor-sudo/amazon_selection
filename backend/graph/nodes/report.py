"""Report node: LLM generates Markdown report → convert to DOCX.
Falls back to hardcoded docx_writer if LLM fails."""
import json
from ..state import GraphState
from ...llm import chat as _llm


SYSTEM = """你是一名资深亚马逊跨境电商选品分析师，拥有10年品类操盘经验。
你的任务是根据提供的分析数据，撰写一份专业的 Amazon 选品评估报告。

写作原则：
1. 严格基于给定数据，不编造任何数字或事实
2. 用具体数据说话，关键数字用 **加粗** 标注
3. 根据数据特点决定每个章节的篇幅——重要的多写，不重要的少写
4. 像给老板写决策备忘录，不是写学术论文
5. 每个结论都要有数据支撑
6. 表格只在数据对比时使用，不要为了用表格而用表格
7. 中文撰写，产品名和专业术语保留英文

内容质量要求（参考标杆报告的写法）：

市场分析：不要只列数字，要给出判断。
  好的写法："camping lights（ABA排名17,180）是三类词中搜索量最高，市场规模最大"
  差的写法："camping lights 搜索量 17,180"

竞争评估：按竞争烈度分级，用标记区分。
  好的写法："🔴 有线三脚架工作灯（$40–$60）：竞争激烈，头部ASIN评论数高（777–1187），新入局需强差异化"
  差的写法："有线三脚架工作灯竞争比较激烈"

定价建议：要有定价逻辑，说清楚为什么定这个价。
  好的写法："低于CAVN($70)，高于Rylpoint($50)，抢占$55-62甜蜜价格带，预估利润率35-45%"
  差的写法："建议定价$55-62"

差评分析：要有具体投诉内容 + 涉及的ASIN。
  好的写法："① 做工&耐久性：塑料铰链/调节套管易断裂，开箱即损坏（涉及 B0B6BCSKBV, B0DHZVRHBV）"
  差的写法："部分产品质量不好"

改良建议：要具体到零部件、参数、成本。
  好的写法："三脚架腿管加厚至1.2mm，支撑测试需通过15kg压力无弯折"
  差的写法："改进三脚架稳定性"

产品方向：每个方向要有目标价、月销目标、具体下一步行动。
  好的写法："方向一：高性能无线充电露营工作两用灯 | 目标价$55-62 | 月销目标300+（90天内）| 下一步：1688找10000mAh三头灯供应商"
  差的写法："建议做充电露营灯"

结论表：用优先级标记（🥇🥈🥉），每行包含方向、切入理由、目标定价、下一步。"""


REPORT_STRUCTURE = """
# 输出格式要求
使用 Markdown 格式，严格遵循以下规则：
1. 章节标题用 # （一级标题），子章节用 ## （二级标题）
2. 表格用 Markdown 表格语法：| 列1 | 列2 |
3. 列表用 - 开头
4. 重要数据用 **加粗**
5. 需要高亮的总结段落用 > 引用语法
6. 不要使用代码块，不要用 ```markdown``` 包裹
7. 直接输出 Markdown 内容，不要加任何前缀说明

# 报告结构（按此顺序，根据数据调整各章节篇幅）

# 执行摘要
> 用一段话总结：这个品类值不值得做、主要机会在哪、最大风险是什么。要有具体数据支撑。

# 一、类目市场概览
## 1.1 市场基本面
用表格展示核心指标（关键词/月总销量/样本月销量区间/竞品定价区间/市场规模评级★），并给出判断性结论。
## 1.2 市场集中度与竞争格局
品牌集中度、卖家集中度、新品占比等，分析垄断程度，判断新卖家是否有机会。
## 1.3 市场趋势
基于月度数据分析趋势走向，指出值得关注的细分赛道和增长信号。

# 二、关键词分析
用表格展示核心关键词（关键词/月搜索量/CPC/转化率/竞争程度/搜索趋势），给出投放策略建议。

# 三、竞品深度分析
## 3.1 竞品矩阵
用表格展示（ASIN/品牌/价格/评分⭐/评论数/月销量/竞争力），竞争力用🔴强 🟡中 🟢新品标记。
## 3.2 竞争分级结论
按产品细分类型分组，用🔴🟡🟢标记每组竞争烈度，说明原因（评论数、头部占位等）。
## 3.3 竞品卖点 vs 差评对比
用表格对比（产品类型/宣传卖点（正面）/实际差评痛点（负面）），找出宣传与现实的落差。

# 四、差评痛点分析
## 4.1 差评整体概况
差评的维度分布和整体特征，一段话概括。
## 4.2 TOP 痛点详解
用表格展示（差评主题/具体投诉内容/涉及ASIN），投诉内容要具体到现象（如"塑料铰链断裂""遥控距离<1米"），不要泛泛而谈。每个痛点用①②③编号。
## 4.3 根因分析与改良建议
逐一分析每个痛点的根因，给出具体改良建议（精确到零部件、参数、材质）。

# 五、利润测算与定价策略
## 5.1 定价建议
用表格展示（产品方向/市场均价/推荐入场价/定价逻辑/预估利润率），定价逻辑要说清楚对标哪个竞品、为什么定这个价。
## 5.2 定价策略
给出Coupon策略、新品期定价、大促定价等具体可执行的定价技巧。

# 六、产品上新方向
每个方向独立展示，包含：
- 方向名称（首选/次选/机会观察）+ 一句话定位
- 目标价 + 月销目标（含时间框架，如"300+（90天内）"）
- 针对差评痛点的改进（用表格：针对差评痛点的改进/差异化新增功能）
- 风险提示
- 下一步行动（具体到供应链动作）

# 七、综合结论与行动优先级
> 一段话给出最终推荐
用表格总结（优先级🥇🥈🥉/方向/切入理由/目标定价/建议下一步）
"""


def _build_data_context(state: GraphState) -> str:
    """Pack all analysis results into a text context for the LLM."""
    sections = []

    def _dump(label, key, max_len=3000):
        data = state.get(key)
        if data:
            text = json.dumps(data, ensure_ascii=False, default=str)[:max_len]
            sections.append(f"## {label}\n{text}")

    _dump("市场数据（按关键词维度）", "market", 3000)
    _dump("市场概览指标", "market_overview", 2000)
    _dump("月度趋势数据", "market_trends", 3000)
    _dump("竞品分析", "competition", 4000)
    _dump("定价与利润分析", "pricing", 3000)
    _dump("利润核算原始数据", "profit_calc", 3000)
    _dump("差评分析", "bad_reviews", 4000)
    _dump("战略洞察", "insights", 3000)
    _dump("选品方向", "directions", 3000)
    _dump("综合结论", "conclusion", 2000)
    _dump("关键词分析数据", "keyword_analysis", 3000)

    # Text-based data
    category_trends = state.get("category_trends", [])
    if category_trends:
        sections.append("## 类目趋势\n" + "\n".join(str(t) for t in category_trends[:10]))

    source_conclusions = state.get("source_conclusions", [])
    if source_conclusions:
        sections.append("## Excel原始结论（仅供参考）\n" + "\n".join(str(c) for c in source_conclusions[:10]))

    # Competitor deep analysis
    comp_analysis = state.get("competitor_analysis", {})
    if comp_analysis:
        comp_parts = []
        for asin, metrics in list(comp_analysis.items())[:8]:
            brand = metrics.get("品牌") or asin
            entry = f"### {brand} ({asin})"
            for field in ["产品类型", "核心卖点", "好评关键词Top3", "差评关键词Top3",
                          "关键改进机会", "最大弱项", "核心竞争壁垒",
                          "建议进入价格带", "主要买家群体"]:
                val = metrics.get(field)
                if val:
                    entry += f"\n{field}: {str(val)[:200]}"
            comp_parts.append(entry)
        sections.append("## 竞品深度分析\n" + "\n\n".join(comp_parts))

    return "\n\n".join(sections)


def _generate_report_markdown(state: GraphState) -> str:
    """Call LLM to generate a full Markdown report."""
    data_context = _build_data_context(state)
    if not data_context.strip():
        return ""

    user_prompt = (
        "# 任务\n"
        "根据以下分析数据，撰写完整的 Amazon 选品评估报告。\n\n"
        f"# 分析数据\n{data_context}\n\n"
        f"{REPORT_STRUCTURE}"
    )

    print(f"[report] Calling LLM with prompt length: {len(user_prompt)} chars, system: {len(SYSTEM)} chars")
    markdown = _llm(user_prompt, max_tokens=8000, temperature=0.4, system=SYSTEM) or ""
    print(f"[report] LLM returned {len(markdown)} chars")

    # Clean up common LLM output artifacts
    markdown = markdown.strip()
    if markdown.startswith("```markdown"):
        markdown = markdown[len("```markdown"):].strip()
    if markdown.startswith("```"):
        markdown = markdown[3:].strip()
    if markdown.endswith("```"):
        markdown = markdown[:-3].strip()

    return markdown


def report_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb:
        cb("report", 95)

    # Use docx_writer directly — content quality comes from
    # specialized LLM nodes (bad_reviews, insights, directions),
    # not from a single generic LLM call. Saves ~40-60 seconds.
    from ...report.docx_writer import build_report
    path = build_report(state)

    if cb:
        cb("report", 100)

    return {"report_path": path, "report_markdown": ""}
