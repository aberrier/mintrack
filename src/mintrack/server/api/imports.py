import datetime as dt
import typing
import uuid

import fastapi
import pydantic
from starlette.datastructures import UploadFile

from mintrack.core.imports.managers import ImportInProgressError, ImportManager
from mintrack.core.imports.parsers import MAX_IMPORT_BYTES, ImportFileError
from mintrack.db.dependencies import DbSessionDepType
from mintrack.db.models import ImportReport, ImportSource, ImportStatus
from mintrack.server.api.dependencies import CurrentUserDepType, TMDBClientDepType
from mintrack.worker.tasks import defer_import

# Room for the multipart boundaries and the source field around the file.
FORM_OVERHEAD_BYTES = 64 * 1024

router = fastapi.APIRouter(prefix="/imports", tags=["imports"])


class ImportJobResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: ImportSource
    status: ImportStatus
    filename: str
    total: int
    processed: int
    report: ImportReport | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


def get_import_manager(session: DbSessionDepType, tmdb: TMDBClientDepType) -> ImportManager:
    return ImportManager(session, tmdb)


ImportManagerDepType = typing.Annotated[ImportManager, fastapi.Depends(get_import_manager)]


def _too_large() -> fastapi.HTTPException:
    return fastapi.HTTPException(
        fastapi.status.HTTP_413_CONTENT_TOO_LARGE,
        f"The file is larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB.",
    )


@router.post(
    "",
    status_code=fastapi.status.HTTP_202_ACCEPTED,
    responses={
        fastapi.status.HTTP_409_CONFLICT: {"description": "An import is already pending or running"},
        fastapi.status.HTTP_411_LENGTH_REQUIRED: {"description": "No Content-Length header"},
        fastapi.status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The file is over the size limit"},
    },
)
async def create_import(
    request: fastapi.Request, user: CurrentUserDepType, manager: ImportManagerDepType, session: DbSessionDepType
) -> ImportJobResponse:
    """Queue the import of a Yamtrack CSV export or a TV Time GDPR export (.zip or tracking CSV)."""
    # The size is checked before the form is parsed, as parsing spools the whole body.
    length = request.headers.get("content-length", "")
    if not length.isdigit():
        raise fastapi.HTTPException(fastapi.status.HTTP_411_LENGTH_REQUIRED)
    if int(length) > MAX_IMPORT_BYTES + FORM_OVERHEAD_BYTES:
        raise _too_large()

    async with request.form(max_files=1, max_fields=1) as form:
        source, upload = form.get("source"), form.get("file")
        if source not in list(ImportSource) or not isinstance(upload, UploadFile):
            raise fastapi.HTTPException(fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "Send a source and a file.")
        data = await upload.read(MAX_IMPORT_BYTES + 1)
        filename = upload.filename or ""
    if len(data) > MAX_IMPORT_BYTES:
        raise _too_large()
    if not data:
        raise fastapi.HTTPException(fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty.")

    try:
        job = await manager.create(user, ImportSource(source), filename, data)
    except ImportFileError as error:
        raise fastapi.HTTPException(fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ImportInProgressError as error:
        raise fastapi.HTTPException(fastapi.status.HTTP_409_CONFLICT, "An import is already running.") from error
    await defer_import(session, job.id, user.id)
    await session.commit()
    await session.refresh(job)
    return ImportJobResponse.model_validate(job)


@router.get("/latest")
async def latest_import(user: CurrentUserDepType, manager: ImportManagerDepType) -> ImportJobResponse | None:
    """The user's latest import, with its progress or its report."""
    job = await manager.latest(user)
    return None if job is None else ImportJobResponse.model_validate(job)
