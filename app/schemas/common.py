from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    error: dict[str, object]
    request_id: str


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_next: bool


class PaginatedResponse[T](BaseModel):
    items: list[T]
    pagination: PaginationMeta


class IdResponse(BaseModel):
    id: UUID


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    message: str = Field(examples=["ok"])
