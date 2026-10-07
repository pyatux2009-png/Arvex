from abc import ABC, abstractmethod
from typing import Dict, Any

class MarketDataProvider(ABC):
    @abstractmethod
    async def get_order_book(self, symbol: str) -> Dict[str, Any]:
        pass