import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_DEV_JWT_SECRET, Settings


def test_jwt_secret_is_required_by_default() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_explicit_local_insecure_secret_mode() -> None:
    settings = Settings(
        _env_file=None,
        environment="local",
        allow_insecure_dev_secret=True,
    )

    assert settings.jwt_secret_key == INSECURE_DEV_JWT_SECRET


def test_insecure_secret_mode_is_not_allowed_outside_local_or_test() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            allow_insecure_dev_secret=True,
        )
