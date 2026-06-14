from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import and_, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError, CsvImportError, app_error_from_integrity_error
from app.core.normalization import (
    clean_display_text,
    is_valid_isbn,
    normalize_author_name,
    normalize_isbn,
    normalize_title,
)
from app.db.session import service_transaction
from app.models.author import Author
from app.models.book import Book
from app.models.import_job import ImportJob
from app.models.user import User
from app.schemas.import_result import ImportResult, ImportRowError

REQUIRED_COLUMNS = ["title", "author_first_name", "author_last_name", "isbn", "publication_year"]
ALLOWED_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}


@dataclass(frozen=True)
class ParsedImportRow:
    row_number: int
    title: str
    normalized_title: str
    author_first_name: str
    author_last_name: str
    normalized_author_first_name: str
    normalized_author_last_name: str
    isbn: str | None
    publication_year: int | None

    @property
    def duplicate_key(self) -> tuple[object, ...]:
        if self.isbn is not None:
            return ("isbn", self.isbn)
        return (
            "fallback",
            self.normalized_title,
            self.normalized_author_first_name,
            self.normalized_author_last_name,
            self.publication_year,
        )


class ImportService:
    def __init__(self, session: AsyncSession, max_upload_bytes: int) -> None:
        self.session = session
        self.max_upload_bytes = max_upload_bytes

    async def import_books(self, file: UploadFile, user: User) -> ImportResult:
        self._validate_file_type(file)
        file_bytes = await self._read_bounded(file)
        checksum = sha256(file_bytes).hexdigest()
        rows = await run_in_threadpool(self._parse_and_validate, file_bytes)

        lock_key = self._advisory_lock_key(user.id, checksum)
        try:
            async with service_transaction(self.session):
                await self.session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
                )
                existing_job = await self._get_completed_job(user.id, checksum)
                if existing_job is not None:
                    return ImportResult(
                        total_rows=existing_job.total_rows,
                        imported_rows=existing_job.imported_rows,
                        skipped_rows=existing_job.skipped_rows,
                        errors=[],
                    )

                author_map = await self._resolve_authors(rows)
                inserted_count = await self._insert_missing_books(rows, author_map)
                skipped_count = len(rows) - inserted_count
                self.session.add(
                    ImportJob(
                        user_id=user.id,
                        file_checksum=checksum,
                        status="completed",
                        total_rows=len(rows),
                        imported_rows=inserted_count,
                        skipped_rows=skipped_count,
                        completed_at=datetime.now(UTC),
                    )
                )
                await self.session.flush()
        except IntegrityError as exc:
            raise app_error_from_integrity_error(exc) from exc

        return ImportResult(
            total_rows=len(rows),
            imported_rows=inserted_count,
            skipped_rows=skipped_count,
            errors=[],
        )

    def _validate_file_type(self, file: UploadFile) -> None:
        filename = file.filename or ""
        content_type = (file.content_type or "").split(";")[0].strip().casefold()
        if not filename.casefold().endswith(".csv") and content_type not in ALLOWED_CONTENT_TYPES:
            raise AppError(
                "unsupported_file_type", "Only CSV uploads are supported.", status_code=415
            )

    async def _read_bounded(self, file: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_upload_bytes:
                raise CsvImportError(
                    "file_too_large", "CSV upload exceeds the configured size limit."
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _parse_and_validate(self, file_bytes: bytes) -> list[ParsedImportRow]:
        if not file_bytes:
            raise CsvImportError("malformed_csv", "CSV file is empty.")
        try:
            text_value = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CsvImportError("malformed_csv", "CSV file must be UTF-8 encoded.") from exc

        try:
            reader = csv.reader(StringIO(text_value, newline=""), strict=True)
            raw_rows = list(reader)
        except csv.Error as exc:
            raise CsvImportError("malformed_csv", f"CSV could not be parsed: {exc}") from exc

        non_blank_rows = [
            (index + 1, row) for index, row in enumerate(raw_rows) if not self._blank_row(row)
        ]
        if not non_blank_rows:
            raise CsvImportError("malformed_csv", "CSV file is empty.")

        header_row_number, header = non_blank_rows[0]
        normalized_header = [column.strip() for column in header]
        self._validate_header(header_row_number, normalized_header)
        if len(non_blank_rows) == 1:
            raise CsvImportError("malformed_csv", "CSV file contains a header but no data rows.")

        rows: list[ParsedImportRow] = []
        errors: list[ImportRowError] = []
        seen: dict[tuple[object, ...], int] = {}
        for row_number, row in non_blank_rows[1:]:
            if len(row) != len(normalized_header):
                errors.append(
                    ImportRowError(
                        row=row_number,
                        message="Row has an inconsistent number of columns.",
                    )
                )
                continue
            data = dict(zip(normalized_header, row, strict=True))
            parsed = self._parse_row(row_number, data, errors)
            if parsed is None:
                continue
            previous_row = seen.get(parsed.duplicate_key)
            if previous_row is not None:
                errors.append(
                    ImportRowError(
                        row=row_number,
                        message=f"Duplicate row; first occurrence is row {previous_row}.",
                    )
                )
                continue
            seen[parsed.duplicate_key] = row_number
            rows.append(parsed)

        if errors:
            raise CsvImportError(
                "invalid_csv_rows",
                "CSV contains invalid rows.",
                details=[error.model_dump() for error in errors],
            )
        return rows

    def _validate_header(self, row_number: int, header: list[str]) -> None:
        duplicate_columns = sorted({column for column in header if header.count(column) > 1})
        if duplicate_columns:
            raise CsvImportError(
                "malformed_csv",
                "CSV header contains duplicate columns.",
                details={"row": row_number, "columns": duplicate_columns},
            )
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        extra = [column for column in header if column not in REQUIRED_COLUMNS]
        if missing or extra:
            raise CsvImportError(
                "malformed_csv",
                "CSV header must exactly match the expected columns.",
                details={"missing": missing, "extra": extra},
            )

    def _parse_row(
        self,
        row_number: int,
        data: dict[str, str],
        errors: list[ImportRowError],
    ) -> ParsedImportRow | None:
        title = clean_display_text(data["title"])
        author_first = clean_display_text(data["author_first_name"])
        author_last = clean_display_text(data["author_last_name"])
        if not title:
            errors.append(ImportRowError(row=row_number, message="Title is required."))
        if not author_first:
            errors.append(ImportRowError(row=row_number, message="Author first name is required."))
        if not author_last:
            errors.append(ImportRowError(row=row_number, message="Author last name is required."))

        isbn = normalize_isbn(data["isbn"])
        if isbn is not None and not is_valid_isbn(isbn):
            errors.append(ImportRowError(row=row_number, message="ISBN is invalid."))

        publication_year = self._parse_publication_year(
            row_number, data["publication_year"], errors
        )
        if (
            not title
            or not author_first
            or not author_last
            or (isbn is not None and not is_valid_isbn(isbn))
        ):
            return None

        normalized_author_first, normalized_author_last = normalize_author_name(
            author_first, author_last
        )
        return ParsedImportRow(
            row_number=row_number,
            title=title,
            normalized_title=normalize_title(title),
            author_first_name=author_first,
            author_last_name=author_last,
            normalized_author_first_name=normalized_author_first,
            normalized_author_last_name=normalized_author_last,
            isbn=isbn,
            publication_year=publication_year,
        )

    def _parse_publication_year(
        self,
        row_number: int,
        value: str,
        errors: list[ImportRowError],
    ) -> int | None:
        clean_value = value.strip()
        if not clean_value:
            return None
        try:
            year = int(clean_value)
        except ValueError:
            errors.append(
                ImportRowError(row=row_number, message="Publication year must be an integer.")
            )
            return None
        current_year = datetime.now(UTC).year
        if year < 1:
            errors.append(
                ImportRowError(row=row_number, message="Publication year must be positive.")
            )
            return None
        if year > current_year:
            errors.append(
                ImportRowError(row=row_number, message="Publication year cannot be in the future.")
            )
            return None
        return year

    def _blank_row(self, row: list[str]) -> bool:
        return all(not value.strip() for value in row)

    async def _get_completed_job(self, user_id: UUID, checksum: str) -> ImportJob | None:
        result = await self.session.execute(
            select(ImportJob).where(
                ImportJob.user_id == user_id,
                ImportJob.file_checksum == checksum,
                ImportJob.status == "completed",
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_authors(self, rows: list[ParsedImportRow]) -> dict[tuple[str, str], Author]:
        author_values_by_key: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            key = (row.normalized_author_first_name, row.normalized_author_last_name)
            author_values_by_key.setdefault(
                key,
                {
                    "first_name": row.author_first_name,
                    "last_name": row.author_last_name,
                    "normalized_first_name": row.normalized_author_first_name,
                    "normalized_last_name": row.normalized_author_last_name,
                },
            )

        if author_values_by_key:
            stmt = (
                pg_insert(Author)
                .values(list(author_values_by_key.values()))
                .on_conflict_do_nothing(
                    index_elements=["normalized_first_name", "normalized_last_name"]
                )
                .returning(Author.id)
            )
            await self.session.execute(stmt)

        keys = list(author_values_by_key)
        result = await self.session.execute(
            select(Author).where(
                tuple_(Author.normalized_first_name, Author.normalized_last_name).in_(keys)
            )
        )
        authors = list(result.scalars().all())
        return {
            (author.normalized_first_name, author.normalized_last_name): author
            for author in authors
        }

    async def _insert_missing_books(
        self,
        rows: list[ParsedImportRow],
        author_map: dict[tuple[str, str], Author],
    ) -> int:
        existing_keys = await self._existing_book_keys(rows, author_map)
        values: list[dict[str, object]] = []
        for row in rows:
            author = author_map[(row.normalized_author_first_name, row.normalized_author_last_name)]
            key = self._book_db_key(row, author.id)
            if key in existing_keys:
                continue
            values.append(
                {
                    "title": row.title,
                    "normalized_title": row.normalized_title,
                    "isbn": row.isbn,
                    "publication_year": row.publication_year,
                    "author_id": author.id,
                }
            )

        if not values:
            return 0

        stmt = pg_insert(Book).values(values).on_conflict_do_nothing().returning(Book.id)
        result = await self.session.execute(stmt)
        inserted_ids = result.scalars().all()
        return len(inserted_ids)

    async def _existing_book_keys(
        self,
        rows: list[ParsedImportRow],
        author_map: dict[tuple[str, str], Author],
    ) -> set[tuple[object, ...]]:
        isbn_values = {row.isbn for row in rows if row.isbn is not None}
        fallback_conditions = []
        fallback_keys: set[tuple[str, UUID, int | None]] = set()
        for row in rows:
            if row.isbn is not None:
                continue
            author = author_map[(row.normalized_author_first_name, row.normalized_author_last_name)]
            key = (row.normalized_title, author.id, row.publication_year)
            fallback_keys.add(key)
            publication_condition = (
                Book.publication_year.is_(None)
                if row.publication_year is None
                else Book.publication_year == row.publication_year
            )
            fallback_conditions.append(
                and_(
                    Book.isbn.is_(None),
                    Book.normalized_title == row.normalized_title,
                    Book.author_id == author.id,
                    publication_condition,
                )
            )

        conditions: list[Any] = []
        if isbn_values:
            conditions.append(Book.isbn.in_(isbn_values))
        if fallback_conditions:
            conditions.append(or_(*fallback_conditions))
        if not conditions:
            return set()

        result = await self.session.execute(select(Book).where(or_(*conditions)))
        existing: set[tuple[object, ...]] = set()
        for book in result.scalars().all():
            if book.isbn is not None:
                existing.add(("isbn", book.isbn))
            else:
                existing.add(
                    ("fallback", book.normalized_title, book.author_id, book.publication_year)
                )
        return existing

    def _book_db_key(self, row: ParsedImportRow, author_id: UUID) -> tuple[object, ...]:
        if row.isbn is not None:
            return ("isbn", row.isbn)
        return ("fallback", row.normalized_title, author_id, row.publication_year)

    def _advisory_lock_key(self, user_id: UUID, checksum: str) -> int:
        digest = sha256(user_id.bytes + checksum.encode("ascii")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)
