from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, nulls_last, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError, app_error_from_integrity_error
from app.core.normalization import clean_display_text, normalize_isbn, normalize_title
from app.db.session import service_transaction
from app.models.author import Author
from app.models.book import Book
from app.schemas.book import BookCreate, BookSortField, BookUpdate, SortDirection


class BookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: BookCreate) -> Book:
        clean_title = clean_display_text(payload.title)
        book = Book(
            title=clean_title,
            normalized_title=normalize_title(clean_title),
            isbn=normalize_isbn(payload.isbn),
            publication_year=payload.publication_year,
            author_id=payload.author_id,
        )
        try:
            async with service_transaction(self.session):
                await self._ensure_author_exists(payload.author_id)
                self.session.add(book)
                await self.session.flush()
                await self.session.refresh(book, attribute_names=["author"])
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc
        return book

    async def get(self, book_id: UUID) -> Book:
        result = await self.session.execute(
            select(Book).options(joinedload(Book.author)).where(Book.id == book_id)
        )
        book = result.scalar_one_or_none()
        if book is None:
            raise NotFoundError("Book")
        return book

    async def list_books(
        self,
        *,
        limit: int,
        offset: int,
        author_id: UUID | None,
        publication_year: int | None,
        title_search: str | None,
        sort: BookSortField,
        direction: SortDirection,
    ) -> tuple[list[Book], int]:
        filters = self._filters(
            author_id=author_id,
            publication_year=publication_year,
            title_search=title_search,
        )
        count_stmt = select(func.count()).select_from(Book).where(*filters)
        total = int(await self.session.scalar(count_stmt) or 0)

        item_stmt = (
            select(Book)
            .options(joinedload(Book.author))
            .where(*filters)
            .order_by(*self._order_by(sort, direction))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(item_stmt)
        return list(result.scalars().all()), total

    async def update(self, book_id: UUID, payload: BookUpdate) -> Book:
        try:
            async with service_transaction(self.session):
                result = await self.session.execute(
                    select(Book).options(joinedload(Book.author)).where(Book.id == book_id)
                )
                book = result.scalar_one_or_none()
                if book is None:
                    raise NotFoundError("Book")

                if "author_id" in payload.model_fields_set and payload.author_id is not None:
                    await self._ensure_author_exists(payload.author_id)
                    book.author_id = payload.author_id
                if "title" in payload.model_fields_set and payload.title is not None:
                    clean_title = clean_display_text(payload.title)
                    book.title = clean_title
                    book.normalized_title = normalize_title(clean_title)
                if "isbn" in payload.model_fields_set:
                    book.isbn = normalize_isbn(payload.isbn)
                if "publication_year" in payload.model_fields_set:
                    book.publication_year = payload.publication_year

                await self.session.flush()
                await self.session.refresh(book, attribute_names=["author"])
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc
        return book

    async def delete(self, book_id: UUID) -> None:
        async with service_transaction(self.session):
            book = await self.session.get(Book, book_id)
            if book is None:
                raise NotFoundError("Book")
            await self.session.delete(book)

    async def _ensure_author_exists(self, author_id: UUID) -> None:
        exists = await self.session.scalar(select(Author.id).where(Author.id == author_id))
        if exists is None:
            raise NotFoundError("Author")

    def _filters(
        self,
        *,
        author_id: UUID | None,
        publication_year: int | None,
        title_search: str | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if author_id is not None:
            filters.append(Book.author_id == author_id)
        if publication_year is not None:
            filters.append(Book.publication_year == publication_year)
        if title_search:
            term = normalize_title(title_search)
            filters.append(Book.normalized_title.ilike(f"%{term}%"))
        return filters

    def _order_by(self, sort: BookSortField, direction: SortDirection) -> list[Any]:
        column = {
            BookSortField.TITLE: Book.normalized_title,
            BookSortField.PUBLICATION_YEAR: Book.publication_year,
            BookSortField.CREATED_AT: Book.created_at,
        }[sort]
        ordered = column.desc() if direction == SortDirection.desc else column.asc()
        if sort == BookSortField.PUBLICATION_YEAR:
            ordered = nulls_last(ordered)
        id_order = Book.id.desc() if direction == SortDirection.desc else Book.id.asc()
        return [ordered, id_order]
