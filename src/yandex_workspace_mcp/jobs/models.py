from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..models.disk import UploadJobStatus
from ..policies.local_files import AllowedLocalFile

UploadRunner = Callable[[AllowedLocalFile, str, bool], Awaitable[None]]


@dataclass(slots=True)
class UploadJob:
    job_id: UUID
    status: UploadJobStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    bytes_total: int
    bytes_sent: int
    destination_path: str
    overwrite: bool
    opened: AllowedLocalFile
    runner: UploadRunner
    error_category: str | None = None
