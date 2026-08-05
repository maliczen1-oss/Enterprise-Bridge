
import pytest
from services.history_service import HistoryService

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
    def get_history(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return self.response

@pytest.mark.parametrize("response", [None, [], [{"date": None}], [{"bad": "data"}]])
def test_history_service_varied_responses(response):
    service = HistoryService(mt5=DummyMT5(response=response))
    result = service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert result == response

def test_history_service_future_date():
    service = HistoryService(mt5=DummyMT5(response=[]))
    result = service.get_history("EURUSD", "2099-01-01", "2099-01-02")
    assert result == []

def test_history_service_connection_unavailable():
    service = HistoryService(mt5=DummyMT5(exc=ConnectionError("Connection unavailable")))
    with pytest.raises(ConnectionError):
        service.get_history("EURUSD", "2020-01-01", "2020-01-02")
