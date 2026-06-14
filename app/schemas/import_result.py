from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int | None
    message: str


class ImportResult(BaseModel):
    total_rows: int
    imported_rows: int
    skipped_rows: int
    errors: list[ImportRowError] = []
