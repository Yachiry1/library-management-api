from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.dependencies import AppSettings, CurrentUser, DbSession
from app.schemas.import_result import ImportResult
from app.services.import_service import ImportService

router = APIRouter(prefix="/imports", tags=["Imports"])


@router.post(
    "/books",
    response_model=ImportResult,
    summary="Import books from CSV",
    responses={
        400: {"description": "Malformed CSV or invalid rows"},
        401: {"description": "Authentication required"},
        415: {"description": "Unsupported file type"},
    },
)
async def import_books(
    session: DbSession,
    settings: AppSettings,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    return await ImportService(session, settings.max_csv_upload_bytes).import_books(
        file, current_user
    )
