import aiohttp
from typing import Any, Dict, Optional

class ExchangeHTTPError(RuntimeError):
    pass

async def request_json(method: str, url: str, *, params: Optional[Dict[str, Any]]=None,
                       data: Optional[str]=None, headers: Optional[Dict[str,str]]=None,
                       timeout: float=10.0) -> Any:
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
        async with session.request(method, url, params=params, data=data, headers=headers) as r:
            text = await r.text()
            if r.status >= 400:
                raise ExchangeHTTPError(f"HTTP {r.status}: {text[:500]}")
            try:
                return await r.json(content_type=None)
            except Exception as exc:
                raise ExchangeHTTPError(f"Invalid JSON from exchange: {text[:500]}") from exc
