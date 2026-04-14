from langgraph.graph import StateGraph, END
from .state import GraphState
from .nodes.crawl import crawl_node
from .nodes.market import market_node
from .nodes.competition import competition_node
from .nodes.pricing import pricing_node
from .nodes.bad_reviews import bad_reviews_node
from .nodes.insights import insights_node
from .nodes.directions import directions_node
from .nodes.report import report_node


def _fan_out(state: GraphState) -> list[str]:
    """After crawl, fan out to parallel branches."""
    return ["market", "competition", "bad_reviews"]


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("crawl", crawl_node)
    g.add_node("market", market_node)
    g.add_node("competition", competition_node)
    g.add_node("pricing", pricing_node)
    g.add_node("bad_reviews", bad_reviews_node)
    g.add_node("insights", insights_node)
    g.add_node("directions", directions_node)
    g.add_node("report", report_node)

    g.set_entry_point("crawl")

    # After crawl: market, competition, bad_reviews run in parallel
    g.add_conditional_edges("crawl", _fan_out)

    # market → pricing (pricing needs market median price)
    g.add_edge("market", "pricing")

    # All parallel branches converge to insights
    g.add_edge("pricing", "insights")
    g.add_edge("competition", "insights")
    g.add_edge("bad_reviews", "insights")

    # insights → directions → report → END
    g.add_edge("insights", "directions")
    g.add_edge("directions", "report")
    g.add_edge("report", END)

    return g.compile()
