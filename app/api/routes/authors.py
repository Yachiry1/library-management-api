from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.author import AuthorCreate, AuthorRead, AuthorUpdate
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationMeta
from app.services.author_service import AuthorService

router = APIRouter(prefix="/authors", tags=["Authors"])


@router.post(
    "",
    response_model=AuthorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an author",
    responses={409: {"description": "Duplicate author"}},
)
async def create_author(
    payload: AuthorCreate,
    session: DbSession,
    _current_user: CurrentUser,
) -> AuthorRead:
    author = await AuthorService(session).create(payload.first_name, payload.last_name)
    return AuthorRead.model_validate(author)


@router.get("/{author_id}", response_model=AuthorRead, summary="Retrieve an author")
async def get_author(author_id: UUID, session: DbSession) -> AuthorRead:
    author = await AuthorService(session).get(author_id)
    return AuthorRead.model_validate(author)


@router.get("", response_model=PaginatedResponse[AuthorRead], summary="List authors")
async def list_authors(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[AuthorRead]:
    authors, total = await AuthorService(session).list(limit=limit, offset=offset)
    return PaginatedResponse[AuthorRead](
        items=[AuthorRead.model_validate(author) for author in authors],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(authors) < total,
        ),
    )


@router.patch(
    "/{author_id}",
    response_model=AuthorRead,
    summary="Update an author",
    responses={409: {"description": "Duplicate author"}},
)
async def update_author(
    author_id: UUID,
    payload: AuthorUpdate,
    session: DbSession,
    _current_user: CurrentUser,
) -> AuthorRead:
    author = await AuthorService(session).update(
        author_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return AuthorRead.model_validate(author)


@router.delete(
    "/{author_id}",
    response_model=MessageResponse,
    summary="Delete an author",
    responses={409: {"description": "Author has books"}},
)
async def delete_author(
    author_id: UUID,
    session: DbSession,
    _current_user: CurrentUser,
) -> MessageResponse:
    await AuthorService(session).delete(author_id)
    return MessageResponse(message="deleted")
