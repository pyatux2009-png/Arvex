from typing import Dict, Any

class InventoryManager:
    def __init__(self):
        self.inventory: Dict[str, float] = {}

    def update_balance(self, asset: str, amount: float):
        self.inventory[asset] = self.inventory.get(asset, 0.0) + amount

    def get_balance(self, asset: str) -> float:
        return self.inventory.get(asset, 0.0)