import os
import stat
import unicodedata
from pathlib import PurePath
from types import TracebackType
from typing import Self

from ..models.errors import InvalidPath


class AllowedLocalFile:
    def __init__(self, descriptor: int, *, basename: str, max_bytes: int) -> None:
        self._file = os.fdopen(descriptor, "rb", closefd=True)
        details = os.fstat(self._file.fileno())
        self._identity = (details.st_dev, details.st_ino)
        self.basename = basename
        self.size = details.st_size
        self.max_bytes = max_bytes
        self._closed = False

    def verify_identity(self) -> None:
        if self._closed:
            raise InvalidPath()
        details = os.fstat(self._file.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or (details.st_dev, details.st_ino) != self._identity
            or details.st_size > self.max_bytes
        ):
            raise InvalidPath()

    def read(self, size: int = -1) -> bytes:
        self.verify_identity()
        return self._file.read(size)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        self.verify_identity()
        return self._file.seek(offset, whence)

    @property
    def file(self):
        self.verify_identity()
        return self._file

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._file.close()

    async def aclose(self) -> None:
        self.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _validate_local_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or unicodedata.normalize("NFKC", value) != value
        or ".." in PurePath(value).parts
    ):
        raise InvalidPath()
    return os.path.abspath(value)


def open_allowed_local_file(
    file_path: str,
    allowed_dirs: list[str],
    *,
    max_bytes: int,
) -> AllowedLocalFile:
    if os.name != "posix" or not allowed_dirs or max_bytes < 0:
        raise InvalidPath()
    candidate = _validate_local_path(file_path)
    selected_root: str | None = None
    for configured_root in allowed_dirs:
        root = _validate_local_path(configured_root)
        try:
            if os.path.commonpath((root, candidate)) == root and candidate != root:
                selected_root = root
                break
        except ValueError:
            continue
    if selected_root is None:
        raise InvalidPath()

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_fd = -1
    current_fd = -1
    final_fd = -1
    try:
        root_fd = os.open(selected_root, os.O_RDONLY | directory | nofollow)
        current_fd = root_fd
        relative_parts = os.path.relpath(candidate, selected_root).split(os.sep)
        if not relative_parts or relative_parts == ["."]:
            raise InvalidPath()
        for part in relative_parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        final_name = relative_parts[-1]
        final_fd = os.open(final_name, os.O_RDONLY | nofollow, dir_fd=current_fd)
        details = os.fstat(final_fd)
        if not stat.S_ISREG(details.st_mode) or details.st_size > max_bytes:
            raise InvalidPath()
        opened = AllowedLocalFile(final_fd, basename=final_name, max_bytes=max_bytes)
        final_fd = -1
        return opened
    except (OSError, ValueError) as exc:
        raise InvalidPath() from exc
    finally:
        if final_fd >= 0:
            os.close(final_fd)
        if current_fd >= 0 and current_fd != root_fd:
            os.close(current_fd)
        if root_fd >= 0:
            os.close(root_fd)
