from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.normalization import is_valid_isbn, normalize_isbn
from app.schemas.author import AuthorRead
from app.schemas.common import OrmModel, PaginatedResponse


class BookSortField(StrEnum):
    TITLE = "title"
    PUBLICATION_YEAR = "publication_year"
    CREATED_AT = "created_at"


class SortDirection(StrEnum):
    asc = "asc"
    desc = "desc"


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    isbn: str | None = Field(default=None, max_length=32)
    publication_year: int | None = Field(default=None, ge=1)
    author_id: UUID

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            msg = "Title cannot be empty."
            raise ValueError(msg)
        return value

    @field_validator("publication_year")
    @classmethod
    def not_future_year(cls, value: int | None) -> int | None:
        if value is not None and value > datetime.now(UTC).year:
            msg = "Publication year cannot be in the future."
            raise ValueError(msg)
        return value

    @field_validator("isbn")
    @classmethod
    def valid_isbn(cls, value: str | None) -> str | None:
        normalized = normalize_isbn(value)
        if normalized is not None and not is_valid_isbn(normalized):
            msg = "ISBN must be a valid ISBN-10 or ISBN-13."
            raise ValueError(msg)
        return value


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    isbn: str | None = Field(default=None, max_length=32)
    publication_year: int | None = Field(default=None, ge=1)
    author_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "Title cannot be empty."
            raise ValueError(msg)
        return value

    @field_validator("publication_year")
    @classmethod
    def not_future_year(cls, value: int | None) -> int | None:
        if value is not None and value > datetime.now(UTC).year:
            msg = "Publication year cannot be in the future."
            raise ValueError(msg)
        return value

    @field_validator("isbn")
    @classmethod
    def valid_isbn(cls, value: str | None) -> str | None:
        normalized = normalize_isbn(value)
        if normalized is not None and not is_valid_isbn(normalized):
            msg = "ISBN must be a valid ISBN-10 or ISBN-13."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BookUpdate":
        if not self.model_fields_set:
            msg = "At least one field must be provided."
            raise ValueError(msg)
        if "title" in self.model_fields_set and self.title is None:
            msg = "Title cannot be null."
            raise ValueError(msg)
        if "author_id" in self.model_fields_set and self.author_id is None:
            msg = "Author cannot be null."
            raise ValueError(msg)
        return self


class BookRead(OrmModel):
    id: UUID
    title: str
    isbn: str | None
    publication_year: int | None
    author_id: UUID
    author: AuthorRead
    created_at: datetime
    updated_at: datetime


class BookListResponse(PaginatedResponse[BookRead]):
    pass
