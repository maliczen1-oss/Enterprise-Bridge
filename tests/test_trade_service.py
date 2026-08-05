
import pytest
from services.trade_service import TradeService

class DummyMT5:
    def __init__(self, exc=None):
        self.exc = exc
    def trade(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        raise NotImplementedError("Trading disabled")

def test_trade_service_disabled():
    service = TradeService(mt5=DummyMT5())
    with pytest.raises(NotImplementedError):
        service.trade("EURUSD", 1.0)

def test_trade_service_broker_unavailable():
    service = TradeService(mt5=DummyMT5(exc=OSError("Broker unavailable")))
    with pytest.raises(OSError):
        service.trade("EURUSD", 1.0)

def test_trade_service_unexpected_exception():
    service = TradeService(mt5=DummyMT5(exc=RuntimeError("Unexpected")))
    with pytest.raises(RuntimeError):
        service.trade("EURUSD", 1.0)
