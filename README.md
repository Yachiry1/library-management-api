# Library Management API

FastAPI backend for a small library management system. It manages users, authors, books, JWT access/refresh authentication, health checks, and atomic CSV book imports backed by PostgreSQL.

## Architecture

The service uses a pragmatic `route -> service -> database` structure. Routes validate HTTP inputs and delegate to services. Services own business rules and transaction boundaries. SQLAlchemy async ORM/Core statements handle persistence. There is no repository layer.

## Requirements

- Python 3.12
- PostgreSQL 15 or newer
- `uv`
- Docker and Docker Compose for the containerized setup

PostgreSQL 15 is required for the no-ISBN book uniqueness index using `NULLS NOT DISTINCT`.

## Local Setup

```bash
uv sync --frozen
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Docker Setup

```bash
docker compose up --build
```

For local development the app container runs migrations before starting. Production deployments should run `alembic upgrade head` as a separate deployment step rather than from every application replica.

## Environment Variables

See `.env.example` for all variables. Important values include `DATABASE_URL`, `JWT_SECRET_KEY`, token lifetimes, and `MAX_CSV_UPLOAD_BYTES`. Do not commit real secrets.

## Commands

```bash
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic check
uv run pytest
uv run ruff check .
uv run mypy app
```

## Authentication Flow

Registration and login return a short-lived access token and a longer-lived refresh token. Access tokens are bearer tokens for API calls. Refresh tokens contain `sub`, `jti`, `type=refresh`, `iat`, and `exp`; only a hash of the refresh identifier is stored.

Refresh rotation locks the current token row with `SELECT FOR UPDATE`, creates a replacement token, revokes the old token, and commits atomically. Reuse of a revoked, expired, malformed, unknown, or incorrectly typed token returns HTTP 401. Logout revokes the submitted refresh token only; already issued access tokens remain valid until their short expiration.

Mobile clients should store refresh tokens in secure OS storage and keep access tokens in memory where practical. When an access token expires, refresh once and retry the original request.

## Schema And Concurrency Decisions

Authors store internal `normalized_first_name` and `normalized_last_name` derived by trimming, collapsing whitespace, and applying Unicode `casefold()`. They are protected by `uq_authors_normalized_first_last`. The database constraint is the final protection against concurrent duplicate creates and updates.

Books store internal `normalized_title` and normalized ISBN. ISBN values remove whitespace and hyphens and uppercase `X`; ISBN-10 and ISBN-13 checksums are validated. ISBN uniqueness is enforced by `uq_books_isbn_present`, a partial unique index where ISBN is not null.

Books without ISBN are unique by normalized title, author ID, and publication year. The index is:

```sql
CREATE UNIQUE INDEX uq_books_no_isbn_identity
ON books (normalized_title, author_id, publication_year)
NULLS NOT DISTINCT
WHERE isbn IS NULL;
```

This treats two missing publication years as duplicates. Author deletion uses `ON DELETE RESTRICT`; deleting an author with books returns HTTP 409.

## Book Listing

The list endpoint uses bounded limit/offset pagination with a maximum limit of 100. Sorting is deterministic by adding book ID as a secondary key. Publication year sorting uses `NULLS LAST`. The endpoint normally performs one count query and one paginated item query including author data. Substring title search uses `ILIKE '%term%'`; for the 10,000-book target this is acceptable, but a trigram index would be a future improvement for larger datasets.

## CSV Import

The CSV import endpoint is authenticated and synchronous. It reads uploads in chunks with a configurable maximum size, computes a checksum from the exact uploaded bytes, parses UTF-8 or UTF-8 with BOM, validates the complete file, and only then opens a database transaction.

Expected columns are exactly:

- `title`
- `author_first_name`
- `author_last_name`
- `isbn`
- `publication_year`

Duplicate rows inside the uploaded file reject the complete import. Existing database records are skipped. Concurrently created authors/books are handled with PostgreSQL conflict-safe inserts and classified as existing/skipped where safe. Unexpected integrity errors roll back the complete import.

Import idempotency is user-scoped by `UNIQUE(user_id, file_checksum)`. Uploading the exact same successfully completed file again returns the previously stored result and does not reprocess the file. Different line endings, encoding, row order, or whitespace can produce different checksums.

## Health Checks

- `/health/live` checks process liveness.
- `/health/ready` checks PostgreSQL connectivity.

Redis-backed rate limiting is intentionally deferred until all core checks pass. Redis is not part of general readiness by default.

## Example Requests

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"reader@example.com","password":"correct horse battery staple"}'

curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"reader@example.com","password":"correct horse battery staple"}'

curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"REFRESH_TOKEN"}'

curl -X POST http://localhost:8000/authors \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Ursula","last_name":"Le Guin"}'

curl -X POST http://localhost:8000/books \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"A Wizard of Earthsea","isbn":"978-0547773742","publication_year":1968,"author_id":"AUTHOR_UUID"}'

curl "http://localhost:8000/books?limit=50&offset=0&sort=title&direction=asc&title_search=earthsea"

curl -X POST http://localhost:8000/imports/books \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F "file=@books.csv;type=text/csv"
```

## Known Trade-Offs

- Limit/offset pagination is simple and flexible, but very deep offsets can become slower than cursor pagination.
- Substring title search does not use a trigram index in the core implementation.
- Access-token blacklisting and refresh-token-family revocation are intentionally omitted.
- Rate limiting is optional and deferred until the core implementation is fully verified.
