from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.normalization import clean_display_text, normalize_author_name
from app.models.author import Author
from app.services.author_service import AuthorService

pytestmark = pytest.mark.integration


async def create_author(
    client: AsyncClient,
    headers: dict[str, str],
    first_name: str = "Ursula",
    last_name: str = "Le Guin",
) -> dict[str, Any]:
    response = await client.post(
        "/authors",
        headers=headers,
        json={"first_name": first_name, "last_name": last_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_book(
    client: AsyncClient,
    headers: dict[str, str],
    author_id: str,
    *,
    title: str = "A Wizard of Earthsea",
    isbn: str | None = "978-0-547-77374-2",
    publication_year: int | None = 1968,
) -> dict[str, Any]:
    response = await client.post(
        "/books",
        headers=headers,
        json={
            "title": title,
            "isbn": isbn,
            "publication_year": publication_year,
            "author_id": author_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_author_crud_duplicate_and_restricted_delete(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    author = await create_author(client, auth_headers, " Ursula ", " Le   Guin ")
    fetched = await client.get(f"/authors/{author['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["first_name"] == "Ursula"

    duplicate = await client.post(
        "/authors",
        headers=auth_headers,
        json={"first_name": "ursula", "last_name": "le guin"},
    )
    assert duplicate.status_code == 409

    updated = await client.patch(
        f"/authors/{author['id']}",
        headers=auth_headers,
        json={"first_name": "Ursula K."},
    )
    assert updated.status_code == 200
    assert updated.json()["first_name"] == "Ursula K."

    await create_book(client, auth_headers, author["id"])
    blocked_delete = await client.delete(f"/authors/{author['id']}", headers=auth_headers)
    assert blocked_delete.status_code == 409

    list_response = await client.get("/authors?limit=10&offset=0")
    assert list_response.status_code == 200
    assert list_response.json()["pagination"]["total"] == 1


async def test_concurrent_duplicate_author_creation(migrated_database: str) -> None:
    engine = create_async_engine(migrated_database, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def insert_author() -> str:
        async with session_factory() as session:
            try:
                await AuthorService(session).create(" Octavia ", " Butler ")
            except Exception as exc:  # noqa: BLE001
                return exc.__class__.__name__
            return "ok"

    results = await asyncio.gather(insert_author(), insert_author())
    assert sorted(results) == ["DuplicateResourceError", "ok"]

    async with session_factory() as session:
        first, last = normalize_author_name(
            clean_display_text("Octavia"),
            clean_display_text("Butler"),
        )
        count = await session.scalar(
            select(func.count())
            .select_from(Author)
            .where(
                Author.normalized_first_name == first,
                Author.normalized_last_name == last,
            )
        )
    await engine.dispose()
    assert count == 1


async def test_book_crud_validation_uniqueness_and_null_year_fallback(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    author = await create_author(client, auth_headers)
    book = await create_book(client, auth_headers, author["id"])
    assert book["isbn"] == "9780547773742"

    fetched = await client.get(f"/books/{book['id']}")
    assert fetched.status_code == 200

    duplicate_isbn = await client.post(
        "/books",
        headers=auth_headers,
        json={
            "title": "Another",
            "isbn": "9780547773742",
            "publication_year": 1970,
            "author_id": author["id"],
        },
    )
    assert duplicate_isbn.status_code == 409

    invalid_year = await client.post(
        "/books",
        headers=auth_headers,
        json={
            "title": "Future",
            "isbn": None,
            "publication_year": 2999,
            "author_id": author["id"],
        },
    )
    assert invalid_year.status_code == 422

    no_isbn = await create_book(
        client,
        auth_headers,
        author["id"],
        title="Collected Essays",
        isbn=None,
        publication_year=None,
    )
    duplicate_null_year = await client.post(
        "/books",
        headers=auth_headers,
        json={
            "title": " collected   essays ",
            "isbn": None,
            "publication_year": None,
            "author_id": author["id"],
        },
    )
    assert duplicate_null_year.status_code == 409

    updated = await client.patch(
        f"/books/{no_isbn['id']}",
        headers=auth_headers,
        json={"publication_year": 1985},
    )
    assert updated.status_code == 200
    assert updated.json()["publication_year"] == 1985

    deleted = await client.delete(f"/books/{book['id']}", headers=auth_headers)
    assert deleted.status_code == 200


async def test_book_list_pagination_filtering_sorting_search_and_bounded_queries(
    client: AsyncClient,
    auth_headers: dict[str, str],
    migrated_database: str,
) -> None:
    author = await create_author(client, auth_headers)
    other = await create_author(client, auth_headers, "N. K.", "Jemisin")

    for index in range(1, 101):
        await create_book(
            client,
            auth_headers,
            author["id"] if index <= 90 else other["id"],
            title=f"Earthsea Volume {index:03d}",
            isbn=None,
            publication_year=1960 + (index % 5),
        )

    filtered = await client.get(
        f"/books?author_id={author['id']}&publication_year=1961&title_search=earthsea"
        "&sort=title&direction=asc&limit=10&offset=0"
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["pagination"]["limit"] == 10
    assert body["pagination"]["total"] > 0
    titles = [item["title"] for item in body["items"]]
    assert titles == sorted(titles)

    query_counts: list[int] = []
    engine = create_async_engine(migrated_database, pool_pre_ping=True)

    for limit in (1, 100):
        counter = {"count": 0}

        def count_sql(*_: object, current_counter: dict[str, int] = counter) -> None:
            current_counter["count"] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_sql)
        try:
            # Count the service-level query shape directly against this engine.
            async_session = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with async_session() as session:
                from app.schemas.book import BookSortField, SortDirection
                from app.services.book_service import BookService

                await BookService(session).list_books(
                    limit=limit,
                    offset=0,
                    author_id=None,
                    publication_year=None,
                    title_search=None,
                    sort=BookSortField.TITLE,
                    direction=SortDirection.asc,
                )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_sql)
        query_counts.append(counter["count"])

    await engine.dispose()
    assert query_counts[0] == query_counts[1]
