from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def csv_bytes(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


async def upload_csv(
    client: AsyncClient,
    headers: dict[str, str],
    content: bytes,
    filename: str = "books.csv",
) -> object:
    return await client.post(
        "/imports/books",
        headers=headers,
        files={"file": (filename, content, "text/csv")},
    )


async def test_successful_csv_import_and_exact_duplicate_returns_stored_result(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    content = csv_bytes(
        [
            "title,author_first_name,author_last_name,isbn,publication_year",
            "A Wizard of Earthsea,Ursula,Le Guin,978-0-547-77374-2,1968",
            "The Tombs of Atuan,Ursula,Le Guin,978-0-689-84159-7,1971",
        ]
    )

    first = await upload_csv(client, auth_headers, content)
    assert first.status_code == 200, first.text
    assert first.json() == {
        "total_rows": 2,
        "imported_rows": 2,
        "skipped_rows": 0,
        "errors": [],
    }

    second = await upload_csv(client, auth_headers, content)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()

    books = await client.get("/books?limit=10&title_search=earthsea")
    assert books.json()["pagination"]["total"] == 1


async def test_invalid_csv_row_rejects_complete_file_and_rolls_back(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    content = csv_bytes(
        [
            "title,author_first_name,author_last_name,isbn,publication_year",
            "Valid Book,Valid,Author,,2001",
            "Bad Book,Bad,Author,,2999",
        ]
    )

    response = await upload_csv(client, auth_headers, content)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_csv_rows"

    authors = await client.get("/authors")
    assert authors.json()["pagination"]["total"] == 0
    books = await client.get("/books")
    assert books.json()["pagination"]["total"] == 0


async def test_99_valid_rows_and_one_invalid_row_write_nothing(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    rows = ["title,author_first_name,author_last_name,isbn,publication_year"]
    rows.extend(f"Book {index},Author,One,,2001" for index in range(99))
    rows.append("Bad,Author,One,,3000")

    response = await upload_csv(client, auth_headers, csv_bytes(rows))
    assert response.status_code == 400

    books = await client.get("/books")
    assert books.json()["pagination"]["total"] == 0


async def test_duplicate_rows_inside_file_are_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    content = csv_bytes(
        [
            "title,author_first_name,author_last_name,isbn,publication_year",
            "A Wizard,Ursula,Le Guin,978-0-547-77374-2,1968",
            "Another Title,Ursula,Le Guin,9780547773742,1970",
        ]
    )

    response = await upload_csv(client, auth_headers, content)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_csv_rows"


async def test_existing_database_books_are_skipped_for_different_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    first = csv_bytes(
        [
            "title,author_first_name,author_last_name,isbn,publication_year",
            "A Wizard,Ursula,Le Guin,978-0-547-77374-2,1968",
        ]
    )
    second = csv_bytes(
        [
            "title,author_first_name,author_last_name,isbn,publication_year",
            "A Wizard Revised,Ursula,Le Guin,9780547773742,1968",
            "No ISBN,Ursula,Le Guin,,",
        ]
    )

    assert (await upload_csv(client, auth_headers, first)).status_code == 200
    response = await upload_csv(client, auth_headers, second)
    assert response.status_code == 200, response.text
    assert response.json()["imported_rows"] == 1
    assert response.json()["skipped_rows"] == 1


async def test_csv_file_shape_errors(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    empty = await upload_csv(client, auth_headers, b"")
    assert empty.status_code == 400

    header_only = await upload_csv(
        client,
        auth_headers,
        b"title,author_first_name,author_last_name,isbn,publication_year\n",
    )
    assert header_only.status_code == 400

    duplicate_header = await upload_csv(
        client,
        auth_headers,
        b"title,title,author_last_name,isbn,publication_year\nA,A,B,,2000\n",
    )
    assert duplicate_header.status_code == 400

    missing_column = await upload_csv(client, auth_headers, b"title,isbn\nA,\n")
    assert missing_column.status_code == 400

    inconsistent = await upload_csv(
        client,
        auth_headers,
        b"title,author_first_name,author_last_name,isbn,publication_year\nA,B\n",
    )
    assert inconsistent.status_code == 400

    unsupported = await upload_csv(client, auth_headers, b"a", filename="books.txt")
    assert unsupported.status_code == 415
