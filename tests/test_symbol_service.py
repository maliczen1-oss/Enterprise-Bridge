
import pytest
from services.symbol_service import SymbolService

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
    def get_symbols(self):
        if self.exc:
            raise self.exc
        return self.response

@pytest.mark.parametrize("response", [None, [], [{"name": None}], [{"bad": "data"}]])
def test_symbol_service_varied_responses(response):
    service = SymbolService(mt5=DummyMT5(response=response))
    result = service.get_symbols()
    assert result == response

def test_symbol_service_alias_handling():
    service = SymbolService(mt5=DummyMT5(response=[{"name": "EURUSD", "alias": "EuroDollar"}]))
    result = service.get_symbols()
    assert result[0]["alias"] == "EuroDollar"

def test_symbol_service_broker_unavailable():
    service = SymbolService(mt5=DummyMT5(exc=OSError("Broker unavailable")))
    with pytest.raises(OSError):
        service.get_symbols()
