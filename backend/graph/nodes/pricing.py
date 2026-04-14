from ..state import GraphState


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def pricing_node(state: GraphState) -> GraphState:
    cb = state.get("on_progress")
    if cb: cb("pricing", 65)

    margin = state.get("target_margin", 0.30)
    fee = state.get("fee_rate", 0.30)
    excel_profit = state.get("profit_calc", [])
    out = {}

    if excel_profit:
        # ── Use pre-analyzed profit data from Excel ──
        for row in excel_profit:
            # Try to identify the row label (product name or shipping method)
            label = ""
            for k in ("运输方式", "产品", "款式"):
                if row.get(k):
                    label = str(row[k]).strip()
                    break
            if not label:
                # Use first non-numeric value as label
                for v in row.values():
                    if v and isinstance(v, str) and len(v) > 1:
                        label = v[:30]
                        break
            if not label:
                continue

            # Support both original column names and transposed profit format
            sell_price_usd = _safe_float(
                row.get("售价\nUSD") or row.get("售价USD") or row.get("售价($)")
            )
            sell_price_cny = _safe_float(row.get("售价\nCNY") or row.get("售价CNY"))
            gross_profit_cny = _safe_float(
                row.get("毛利润\nCNY") or row.get("毛利润CNY") or row.get("毛利润")
            )
            margin_val = _safe_float(row.get("毛利率"))
            fba_total = _safe_float(
                row.get("FBA总成本\nUSD") or row.get("FBA总成本USD") or row.get("FBA总成本")
            )
            fba_fee_val = _safe_float(row.get("FBA配送费\nUSD") or row.get("FBA配送费USD"))
            fba_commission = _safe_float(row.get("FBA佣金\nUSD") or row.get("FBA佣金USD"))
            shipping_cost = _safe_float(
                row.get("头程运费\nCNY") or row.get("头程运费CNY") or row.get("头程运费")
            )
            product_cost = _safe_float(
                row.get("产品成本\nCNY") or row.get("产品成本CNY") or row.get("产品成本")
                or row.get("产品成本CNY")
            )
            ad_cost = _safe_float(row.get("广告\nUSD") or row.get("广告USD"))

            # Compute derived fields if raw data available but totals missing
            if sell_price_usd and product_cost and not gross_profit_cny:
                # Estimate: gross_profit = sell_price - product_cost/7.2 - shipping - fba
                cost_usd = (product_cost / 7.2) + (shipping_cost or 0) + (fba_total or 0)
                ad = sell_price_usd * _safe_float(row.get("广告费率") or 0) if row.get("广告费率") else 0
                other = _safe_float(row.get("其他费用")) or 0
                gross_usd = sell_price_usd - cost_usd - ad - other
                gross_profit_cny = round(gross_usd * 7.2, 2)
                margin_val = round(gross_usd / sell_price_usd, 4) if sell_price_usd else None

            out[label] = {
                "sell_price_usd": sell_price_usd,
                "sell_price_cny": sell_price_cny,
                "gross_profit_cny": gross_profit_cny,
                "margin_rate": f"{margin_val:.1%}" if margin_val and isinstance(margin_val, (int, float)) and margin_val < 1 else str(margin_val) if margin_val else None,
                "fba_total_usd": fba_total,
                "fba_delivery_usd": fba_fee_val,
                "fba_commission_usd": fba_commission,
                "shipping_cost_cny": shipping_cost,
                "product_cost_cny": product_cost,
                "ad_cost_usd": ad_cost,
                # Compatibility fields for report
                "median_price": sell_price_usd,
                "entry_price": sell_price_usd,
                "entry_range": f"${round(sell_price_usd*0.95,2)} – ${round(sell_price_usd*1.05,2)}" if sell_price_usd else "—",
                "target_cost_max": round(product_cost / 7.2, 2) if product_cost else None,  # CNY to USD approx
                "expected_gross_per_unit": round(gross_profit_cny / 7.2, 2) if gross_profit_cny else None,
                "source": "Excel 利润核算",
            }
    else:
        # ── Fallback: compute from market median price ──
        for kw, m in state.get("market", {}).items():
            med = m.get("price_median")
            if not med:
                out[kw] = {"note": "数据不足"}
                continue
            entry = round(med * 0.92, 2)
            cost_cap = round(entry * (1 - margin - fee), 2)
            gross = round(entry * margin, 2)
            out[kw] = {
                "median_price": med,
                "entry_price": entry,
                "entry_range": f"${round(entry*0.95,2)} – ${round(entry*1.05,2)}",
                "target_cost_max": cost_cap,
                "expected_gross_per_unit": gross,
                "fba_fee_rate": f"{int(fee*100)}%",
                "target_margin": f"{int(margin*100)}%",
                "source": "基于中位价估算",
            }

    if cb: cb("pricing", 70)
    return {"pricing": out}
