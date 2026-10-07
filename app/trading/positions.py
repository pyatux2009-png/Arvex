import uuid
from typing import Dict, Any, Optional

class PositionManager:
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}

    def create_position(self, symbol: str, buy_exchange: str, sell_exchange: str, amount: float) -> str:
        pos_id = str(uuid.uuid4())
        self.positions[pos_id] = {
            "position_id": pos_id,
            "symbol": symbol,
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "amount": amount,
            "status": "NEW",
            "buy_fill": 0.0,
            "sell_fill": 0.0,
            "buy_price": 0.0,
            "sell_price": 0.0,
            "net_profit_usd": 0.0
        }
        return pos_id

    def set_position_status(self, position_id: str, status: str):
        if position_id in self.positions:
            self.positions[position_id]["status"] = status

    def update_leg_fill(self, position_id: str, leg: str, filled_amount: float, avg_price: float):
        if position_id in self.positions:
            if leg == "buy":
                self.positions[position_id]["buy_fill"] = filled_amount
                self.positions[position_id]["buy_price"] = avg_price
            elif leg == "sell":
                self.positions[position_id]["sell_fill"] = filled_amount
                self.positions[position_id]["sell_price"] = avg_price

    def close_position(self, position_id: str, net_profit_usd: float) -> Optional[Dict[str, Any]]:
        if position_id in self.positions:
            self.positions[position_id]["status"] = "FILLED"
            self.positions[position_id]["net_profit_usd"] = net_profit_usd
            return self.positions[position_id]
        return None