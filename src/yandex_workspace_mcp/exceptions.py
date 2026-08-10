class YandexWorkspaceError(Exception):
    """Base exception for all Yandex Workspace MCP errors."""
    pass

class AuthenticationError(YandexWorkspaceError):
    """Raised when authentication fails."""
    pass

class PermissionDenied(YandexWorkspaceError):
    """Raised when an operation is not permitted (e.g. read-only mode or outside allowed roots)."""
    pass

class ResourceNotFound(YandexWorkspaceError):
    """Raised when a requested resource (file, folder, page) is not found."""
    pass

class RateLimitExceeded(YandexWorkspaceError):
    """Raised when API rate limits are exceeded and retries are exhausted."""
    pass

class ConflictError(YandexWorkspaceError):
    """Raised when there is a conflict (e.g. resource already exists)."""
    pass

class RevisionConflict(YandexWorkspaceError):
    """Raised when updating a wiki page with a stale revision (optimistic locking failed)."""
    pass

class InvalidPath(YandexWorkspaceError):
    """Raised when a path is invalid or attempts path traversal."""
    pass

class APIError(YandexWorkspaceError):
    """Raised when the Yandex API returns an unexpected error."""
    def __init__(self, message: str, status_code: int | None = None, response_data: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data
