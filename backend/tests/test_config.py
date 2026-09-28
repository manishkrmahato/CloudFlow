from pydantic import ValidationError
import pytest

from app.config import Settings


def test_production_requires_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="JWT_SECRET must be configured in production"):
        Settings(_env_file=None)
