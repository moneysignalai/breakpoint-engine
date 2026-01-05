import pytest
from src.config import get_settings


def test_massive_api_base_url_takes_priority(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MASSIVE_API_BASE_URL", "https://api.primary.test")
    monkeypatch.delenv("MASSIVE_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.MASSIVE_API_BASE_URL == "https://api.primary.test"
    get_settings.cache_clear()


def test_massive_base_url_alias_used_when_primary_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MASSIVE_API_BASE_URL", raising=False)
    monkeypatch.setenv("MASSIVE_BASE_URL", "https://api.alias.test")
    monkeypatch.delenv("BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.MASSIVE_API_BASE_URL == "https://api.alias.test"
    get_settings.cache_clear()


def test_massive_base_url_defaults_to_polygon(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MASSIVE_API_BASE_URL", raising=False)
    monkeypatch.delenv("MASSIVE_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.MASSIVE_API_BASE_URL == "https://api.polygon.io"
    get_settings.cache_clear()
