from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import OrmModel, StrictRequest


class AuthorBase(StrictRequest):
    first_name: str = Field(min_length=1, max_length=200)
    last_name: str = Field(min_length=1, max_length=200)


class AuthorCreate(AuthorBase):
    pass


class AuthorUpdate(StrictRequest):
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "AuthorUpdate":
        if self.first_name is None and self.last_name is None:
            msg = "At least one field must be provided."
            raise ValueError(msg)
        return self


class AuthorRead(OrmModel):
    id: UUID
    first_name: str
    last_name: str
    created_at: datetime
    updated_at: datetime
