from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseExchange(ABC):
    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pass