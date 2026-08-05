
import pytest
from services.account_service import AccountService

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
    def get_account(self):
        if self.exc:
            raise self.exc
        return self.response

@pytest.mark.parametrize("response", [None, {}, {"balance": None}, {"bad": "data"}])
def test_account_service_varied_responses(response):
    service = AccountService(mt5=DummyMT5(response=response))
    result = service.get_account()
    assert result == response

def test_account_service_connection_unavailable():
    service = AccountService(mt5=DummyMT5(exc=ConnectionError("Connection unavailable")))
    with pytest.raises(ConnectionError):
        service.get_account()

def test_account_service_unexpected_exception():
    service = AccountService(mt5=DummyMT5(exc=RuntimeError("Boom")))
    with pytest.raises(RuntimeError):
        service.get_account()
