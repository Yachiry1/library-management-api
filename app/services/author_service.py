from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AppError,
    DuplicateResourceError,
    NotFoundError,
    app_error_from_integrity_error,
)
from app.core.normalization import clean_display_text, normalize_author_name
from app.db.session import service_transaction
from app.models.author import Author
from app.models.book import Book


class AuthorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, first_name: str, last_name: str) -> Author:
        clean_first = clean_display_text(first_name)
        clean_last = clean_display_text(last_name)
        normalized_first, normalized_last = normalize_author_name(clean_first, clean_last)
        author = Author(
            first_name=clean_first,
            last_name=clean_last,
            normalized_first_name=normalized_first,
            normalized_last_name=normalized_last,
        )
        try:
            async with service_transaction(self.session):
                self.session.add(author)
                await self.session.flush()
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc
        return author

    async def get(self, author_id: UUID) -> Author:
        author = await self.session.get(Author, author_id)
        if author is None:
            raise NotFoundError("Author")
        return author

    async def list(self, *, limit: int, offset: int) -> tuple[list[Author], int]:
        count = await self.session.scalar(select(func.count()).select_from(Author))
        result = await self.session.execute(
            select(Author)
            .order_by(Author.last_name.asc(), Author.first_name.asc(), Author.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(count or 0)

    async def update(
        self, author_id: UUID, *, first_name: str | None, last_name: str | None
    ) -> Author:
        try:
            async with service_transaction(self.session):
                author = await self.session.get(Author, author_id)
                if author is None:
                    raise NotFoundError("Author")
                next_first = (
                    clean_display_text(first_name) if first_name is not None else author.first_name
                )
                next_last = (
                    clean_display_text(last_name) if last_name is not None else author.last_name
                )
                normalized_first, normalized_last = normalize_author_name(next_first, next_last)
                author.first_name = next_first
                author.last_name = next_last
                author.normalized_first_name = normalized_first
                author.normalized_last_name = normalized_last
                await self.session.flush()
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc
        return author

    async def delete(self, author_id: UUID) -> None:
        try:
            async with service_transaction(self.session):
                author = await self.session.get(Author, author_id)
                if author is None:
                    raise NotFoundError("Author")
                book_count = await self.session.scalar(
                    select(func.count()).select_from(Book).where(Book.author_id == author_id)
                )
                if book_count:
                    raise DuplicateResourceError(
                        "author_has_books",
                        "Author cannot be deleted while books exist.",
                    )
                await self.session.delete(author)
                await self.session.flush()
        except IntegrityError as exc:
            app_error = app_error_from_integrity_error(exc)
            if app_error.error.code == "database_conflict":
                raise AppError(
                    "author_has_books",
                    "Author cannot be deleted while books exist.",
                    status_code=409,
                ) from exc
            raise app_error from exc
