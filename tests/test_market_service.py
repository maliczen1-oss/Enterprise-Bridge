
import pytest
from services.market_service import MarketService

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
    def get_market_info(self):
        if self.exc:
            raise self.exc
        return self.response

@pytest.mark.parametrize("response", [None, {}, {"symbol": None}, {"bad": "data"}])
def test_market_service_varied_responses(response):
    service = MarketService(mt5=DummyMT5(response=response))
    result = service.get_market_info()
    assert result == response

def test_market_service_invalid_type():
    service = MarketService(mt5=DummyMT5(response="not-a-dict"))
    result = service.get_market_info()
    assert isinstance(result, str)

def test_market_service_unexpected_exception():
    service = MarketService(mt5=DummyMT5(exc=RuntimeError("Unexpected")))
    with pytest.raises(RuntimeError):
        service.get_market_info()
