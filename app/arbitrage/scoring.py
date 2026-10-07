def evaluate_risk_level(net_profit_pct: float, age_seconds: float, liquidity_depth: float) -> str:
    if age_seconds > 2.0 or liquidity_depth < 10.0:
        return "BLOCKED"
    if net_profit_pct > 0.5:
        return "SAFE_CANDIDATE"
    elif net_profit_pct > 0.2:
        return "NORMAL"
    elif net_profit_pct > 0.0:
        return "RISKY"
    return "BLOCKED"