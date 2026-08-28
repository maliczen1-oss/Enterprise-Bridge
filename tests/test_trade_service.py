
import pytest

from core.exceptions import NotImplementedException
from services.trade_service import TradeService


@pytest.mark.asyncio
async def test_open_trade_is_certifiably_disabled():
    with pytest.raises(NotImplementedException, match="disabled"):
        await TradeService().open_trade({"symbol": "EURUSD", "type": "BUY", "volume": 0.1})


@pytest.mark.asyncio
async def test_modify_trade_is_certifiably_disabled():
    with pytest.raises(NotImplementedException, match="disabled"):
        await TradeService().modify_trade(ticket=123, stop_loss=1.0, take_profit=2.0)


@pytest.mark.asyncio
async def test_close_trade_is_certifiably_disabled():
    with pytest.raises(NotImplementedException, match="disabled"):
        await TradeService().close_trade(ticket=123)
