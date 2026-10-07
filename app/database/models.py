class TradeModel:
    """
    Trade Model matching the unified state machine:
    NEW, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED, UNKNOWN, RECOVERING, RECOVERED, FAILED, UNRESOLVED
    """
    def __init__(self, trade_id: str, status: str = "NEW"):
        self.trade_id = trade_id
        self.status = status