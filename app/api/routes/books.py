from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.book import (
    BookCreate,
    BookListResponse,
    BookRead,
    BookSortField,
    BookUpdate,
    SortDirection,
)
from app.schemas.common import MessageResponse, PaginationMeta
from app.services.book_service import BookService

router = APIRouter(prefix="/books", tags=["Books"])


@router.post(
    "",
    response_model=BookRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a book",
    responses={404: {"description": "Author not found"}, 409: {"description": "Duplicate book"}},
)
async def create_book(
    payload: BookCreate, session: DbSession, _current_user: CurrentUser
) -> BookRead:
    book = await BookService(session).create(payload)
    return BookRead.model_validate(book)


@router.get("/{book_id}", response_model=BookRead, summary="Retrieve a book")
async def get_book(book_id: UUID, session: DbSession) -> BookRead:
    book = await BookService(session).get(book_id)
    return BookRead.model_validate(book)


@router.get(
    "",
    response_model=BookListResponse,
    summary="List books with pagination, filtering, search, and deterministic sorting",
)
async def list_books(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    author_id: UUID | None = None,
    publication_year: int | None = Query(default=None, ge=1),
    title_search: str | None = Query(default=None, min_length=1, max_length=200),
    sort: BookSortField = BookSortField.CREATED_AT,
    direction: SortDirection = SortDirection.asc,
) -> BookListResponse:
    books, total = await BookService(session).list_books(
        limit=limit,
        offset=offset,
        author_id=author_id,
        publication_year=publication_year,
        title_search=title_search,
        sort=sort,
        direction=direction,
    )
    return BookListResponse(
        items=[BookRead.model_validate(book) for book in books],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(books) < total,
        ),
    )


@router.patch(
    "/{book_id}",
    response_model=BookRead,
    summary="Update a book",
    responses={
        404: {"description": "Book or author not found"},
        409: {"description": "Duplicate book"},
    },
)
async def update_book(
    book_id: UUID,
    payload: BookUpdate,
    session: DbSession,
    _current_user: CurrentUser,
) -> BookRead:
    book = await BookService(session).update(book_id, payload)
    return BookRead.model_validate(book)


@router.delete("/{book_id}", response_model=MessageResponse, summary="Delete a book")
async def delete_book(
    book_id: UUID, session: DbSession, _current_user: CurrentUser
) -> MessageResponse:
    await BookService(session).delete(book_id)
    return MessageResponse(message="deleted")
