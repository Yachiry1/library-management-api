import pytest
from pydantic import ValidationError

from app.schemas.book import BookUpdate


def test_book_update_allows_clearing_nullable_fields() -> None:
    assert BookUpdate(isbn=None).isbn is None
    assert BookUpdate(publication_year=None).publication_year is None


def test_book_update_rejects_empty_payload_and_null_required_fields() -> None:
    with pytest.raises(ValidationError):
        BookUpdate()
    with pytest.raises(ValidationError):
        BookUpdate(title=None)
    with pytest.raises(ValidationError):
        BookUpdate(author_id=None)
