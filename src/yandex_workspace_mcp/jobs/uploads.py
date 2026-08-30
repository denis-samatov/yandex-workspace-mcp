import asyncio
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ..models.disk import (
    UploadJobListResponse,
    UploadJobResponse,
    UploadJobStatus,
)
from ..models.errors import (
    ConfigurationError,
    RateLimitExceeded,
    ResourceNotFound,
    YandexWorkspaceError,
)
from ..policies.cursors import CursorCodec, UploadJobCursorV1
from ..policies.local_files import AllowedLocalFile
from .models import UploadJob, UploadRunner


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class UploadJobStore:
    def __init__(
        self,
        *,
        capacity: int,
        ttl_seconds: int,
        cursor_codec: CursorCodec,
        owner: str = "trusted-local",
    ) -> None:
        if capacity < 1 or ttl_seconds < 1:
            raise ValueError("job store bounds must be positive")
        self.capacity = capacity
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cursor_codec = cursor_codec
        self.owner = owner
        self._jobs: OrderedDict[UUID, UploadJob] = OrderedDict()
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def submit(
        self,
        opened: AllowedLocalFile,
        *,
        destination_path: str,
        overwrite: bool,
        runner: UploadRunner,
    ) -> UploadJobResponse:
        async with self._lock:
            if self._closed:
                opened.close()
                raise ConfigurationError("Upload job store is closed.")
            self._prune_locked()
            self._evict_terminal_locked()
            if len(self._jobs) >= self.capacity:
                opened.close()
                raise RateLimitExceeded()
            now = datetime.now(UTC)
            job = UploadJob(
                job_id=uuid4(),
                status="queued",
                created_at=now,
                updated_at=now,
                expires_at=now + self.ttl,
                bytes_total=opened.size,
                bytes_sent=0,
                destination_path=destination_path,
                overwrite=overwrite,
                opened=opened,
                runner=runner,
            )
            self._jobs[job.job_id] = job
            self._tasks[job.job_id] = asyncio.create_task(self._run(job.job_id))
            return self._public(job)

    async def _run(self, job_id: UUID) -> None:
        try:
            async with self._lock:
                job = self._jobs[job_id]
                if job.status != "queued":
                    return
                job.status = "running"
                job.updated_at = datetime.now(UTC)
            await job.runner(job.opened, job.destination_path, job.overwrite)
            async with self._lock:
                if job.status == "running":
                    job.status = "completed"
                    job.bytes_sent = job.bytes_total
                    job.updated_at = datetime.now(UTC)
                    job.expires_at = job.updated_at + self.ttl
        except asyncio.CancelledError:
            async with self._lock:
                current = self._jobs.get(job_id)
                if current is not None and current.status in {"queued", "running"}:
                    current.status = "cancelled"
                    current.updated_at = datetime.now(UTC)
                    current.expires_at = current.updated_at + self.ttl
            raise
        except Exception as exc:  # noqa: BLE001 - job boundary records a sanitized category
            async with self._lock:
                current = self._jobs.get(job_id)
                if current is not None and current.status == "running":
                    current.status = "failed"
                    current.error_category = (
                        exc.category if isinstance(exc, YandexWorkspaceError) else "upstream_error"
                    )
                    current.updated_at = datetime.now(UTC)
                    current.expires_at = current.updated_at + self.ttl
        finally:
            async with self._lock:
                current = self._jobs.get(job_id)
                if current is not None:
                    current.opened.close()
                self._tasks.pop(job_id, None)

    async def get(self, job_id: UUID) -> UploadJobResponse:
        async with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None:
                raise ResourceNotFound()
            return self._public(job)

    async def list(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        status: UploadJobStatus | None = None,
        principal: str | None = None,
    ) -> UploadJobListResponse:
        selected_principal = principal or self.owner
        async with self._lock:
            self._prune_locked()
            offset = 0
            if cursor is not None:
                offset = self.cursor_codec.decode_upload_jobs(
                    cursor,
                    principal=selected_principal,
                    status=status,
                ).offset
            jobs = [job for job in self._jobs.values() if status is None or job.status == status]
            page = jobs[offset : offset + limit]
            next_offset = offset + len(page)
            next_cursor = None
            if next_offset < len(jobs):
                next_cursor = self.cursor_codec.encode_upload_jobs(
                    UploadJobCursorV1(
                        principal_hash=self.cursor_codec.principal_hash(selected_principal),
                        filter_hash=self.cursor_codec.query_hash(status or "*"),
                        offset=next_offset,
                    )
                )
            return UploadJobListResponse(
                jobs=[self._public(job) for job in page],
                next_cursor=next_cursor,
            )

    def _prune_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"completed", "failed", "cancelled"} and job.expires_at <= now
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    def _evict_terminal_locked(self) -> None:
        while len(self._jobs) >= self.capacity:
            terminal = next(
                (
                    job_id
                    for job_id, job in self._jobs.items()
                    if job.status in {"completed", "failed", "cancelled"}
                ),
                None,
            )
            if terminal is None:
                return
            self._jobs.pop(terminal, None)

    @staticmethod
    def _public(job: UploadJob) -> UploadJobResponse:
        return UploadJobResponse(
            job_id=job.job_id,
            status=job.status,
            created_at=_timestamp(job.created_at),
            updated_at=_timestamp(job.updated_at),
            expires_at=_timestamp(job.expires_at),
            bytes_total=job.bytes_total,
            bytes_sent=job.bytes_sent,
            destination_path=job.destination_path,
            error_category=job.error_category,
        )

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            tasks = list(self._tasks.values())
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            for job in self._jobs.values():
                if job.status in {"queued", "running"}:
                    job.status = "cancelled"
                    job.updated_at = datetime.now(UTC)
                    job.expires_at = job.updated_at + self.ttl
                job.opened.close()
