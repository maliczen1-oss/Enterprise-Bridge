
import pytest
from services.position_service import PositionService

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
    def get_positions(self):
        if self.exc:
            raise self.exc
        return self.response

@pytest.mark.parametrize("response", [None, [], [{"ticket": None}], [{"bad": "data"}]])
def test_position_service_varied_responses(response):
    service = PositionService(mt5=DummyMT5(response=response))
    result = service.get_positions()
    assert result == response

def test_position_service_broker_unavailable():
    service = PositionService(mt5=DummyMT5(exc=OSError("Broker unavailable")))
    with pytest.raises(OSError):
        service.get_positions()

def test_position_service_timeout():
    service = PositionService(mt5=DummyMT5(exc=TimeoutError("Timeout")))
    with pytest.raises(TimeoutError):
        service.get_positions()
