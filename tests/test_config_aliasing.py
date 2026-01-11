import pytest
from src.config import get_settings


def test_massive_api_base_url_takes_priority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MASSIVE_API_BASE_URL", "https://api.primary.test")
    monkeypatch.delenv("BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.MASSIVE_API_BASE_URL == "https://api.primary.test"
    get_settings.cache_clear()


def test_massive_base_url_defaults_to_massive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MASSIVE_API_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.MASSIVE_API_BASE_URL == "https://api.massive.com"
    get_settings.cache_clear()
