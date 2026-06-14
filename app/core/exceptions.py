from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError


@dataclass
class ErrorDetail:
    code: str
    message: str
    status_code: int
    details: Any = None


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.error = ErrorDetail(
            code=code, message=message, status_code=status_code, details=details
        )


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__("not_found", f"{resource} was not found.", status_code=404)


class DuplicateResourceError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)


class AuthenticationError(AppError):
    def __init__(
        self, code: str = "unauthenticated", message: str = "Authentication failed."
    ) -> None:
        super().__init__(code, message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not authorized.") -> None:
        super().__init__("forbidden", message, status_code=403)


class CsvImportError(AppError):
    def __init__(self, code: str, message: str, *, details: Any = None) -> None:
        super().__init__(code, message, status_code=400, details=details)


CONSTRAINT_ERROR_MAP: dict[str, tuple[str, str]] = {
    "uq_users_email": ("duplicate_user", "A user with this email already exists."),
    "uq_authors_normalized_first_last": (
        "duplicate_author",
        "An author with the same normalized first and last name already exists.",
    ),
    "uq_books_isbn_present": ("duplicate_book", "A book with this ISBN already exists."),
    "uq_books_no_isbn_identity": (
        "duplicate_book",
        "A book with the same title, author, and publication year already exists.",
    ),
    "uq_import_jobs_user_checksum": (
        "duplicate_import",
        "This file has already been imported by this user.",
    ),
    "fk_books_author_id_authors": (
        "author_has_books",
        "Author cannot be deleted while books exist.",
    ),
}


def constraint_name_from_integrity_error(exc: IntegrityError) -> str | None:
    pending: list[BaseException | None] = [exc, exc.orig]
    seen: set[int] = set()
    current = pending.pop()
    while current is not None:
        if id(current) in seen:
            current = pending.pop() if pending else None
            continue
        seen.add(id(current))
        constraint_name = getattr(current, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
        diag = getattr(current, "diag", None)
        if diag is not None:
            diag_constraint = getattr(diag, "constraint_name", None)
            if isinstance(diag_constraint, str):
                return diag_constraint
        pending.extend([current.__cause__, current.__context__])
        current = pending.pop() if pending else None
    return None


def app_error_from_integrity_error(exc: IntegrityError) -> AppError:
    constraint_name = constraint_name_from_integrity_error(exc)
    if constraint_name and constraint_name in CONSTRAINT_ERROR_MAP:
        code, message = CONSTRAINT_ERROR_MAP[constraint_name]
        return DuplicateResourceError(code, message)
    return AppError(
        "database_conflict", "The request conflicts with existing data.", status_code=409
    )
