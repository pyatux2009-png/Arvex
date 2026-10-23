from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "args"),
    [
        (routes.start_engine, ()),
        (routes.stop_engine, ()),
        (routes.set_capital, ({"capital_usd": 10},)),
    ],
)
async def test_live_mutating_endpoints_fail_closed_without_configured_token(
    monkeypatch, endpoint, args
):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=True))
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        await endpoint(*args, x_api_token=None)

    assert exc.value.status_code == 503
    assert "LIVE_API_TOKEN" in exc.value.detail


@pytest.mark.asyncio
async def test_live_engine_start_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=True))
    monkeypatch.setenv("LIVE_API_TOKEN", "a-long-test-secret")

    with pytest.raises(HTTPException) as exc:
        await routes.start_engine(x_api_token="wrong-secret")

    assert exc.value.status_code == 401


def test_paper_mode_does_not_require_live_api_token(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(live_trading=False))
    monkeypatch.delenv("LIVE_API_TOKEN", raising=False)

    routes._require_live_api_token(None)
