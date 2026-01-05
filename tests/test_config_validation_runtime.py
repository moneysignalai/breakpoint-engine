import pytest

from src.config import Settings
from src.utils.config_validation import validate_runtime_config


def test_config_validation_rejects_polygon_massive_mismatch():
    settings = Settings(
        MASSIVE_API_KEY="key",
        DATABASE_URL="sqlite://",
        DATA_PROVIDER="massive",
        MASSIVE_API_BASE_URL="https://api.polygon.io",
        MASSIVE_BARS_PATH_TEMPLATE="/markets/{symbol}/bars",
    )

    with pytest.raises(RuntimeError, match="Config mismatch"):
        validate_runtime_config(settings)


def test_config_validation_requires_api_key():
    settings = Settings(
        MASSIVE_API_KEY="",
        DATABASE_URL="sqlite://",
        MASSIVE_API_BASE_URL="https://api.massive.com",
    )

    with pytest.raises(RuntimeError, match="Missing MASSIVE_API_KEY"):
        validate_runtime_config(settings)


def test_config_validation_passes_for_valid_combo():
    settings = Settings(
        MASSIVE_API_KEY="key",
        DATABASE_URL="sqlite://",
        MASSIVE_API_BASE_URL="https://api.massive.com",
        MASSIVE_BARS_PATH_TEMPLATE="/markets/{symbol}/bars",
    )

    validate_runtime_config(settings)
