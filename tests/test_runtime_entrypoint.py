from pathlib import Path


def test_bridge_module_entrypoint_exists_and_is_safe():
    source = (Path(__file__).parents[1] / "bridge" / "__main__.py").read_text(encoding="utf-8")
    assert '"bridge.app:app"' in source
    assert "from bridge.config import settings" in source


def test_authentication_uses_constant_time_comparison():
    source = (Path(__file__).parents[1] / "middleware" / "auth.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest(token, expected)" in source
