import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest
from app.schemas.author import AuthorCreate
from app.schemas.book import BookCreate


def test_request_schemas_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AuthorCreate(first_name="Ursula", last_name="Le Guin", normalized_first_name="ursula")

    with pytest.raises(ValidationError):
        LoginRequest(email="reader@example.com", password="secret", admin=True)  # noqa: S106

    with pytest.raises(ValidationError):
        BookCreate(
            title="A Wizard of Earthsea",
            author_id="00000000-0000-0000-0000-000000000000",
            extra="nope",
        )
