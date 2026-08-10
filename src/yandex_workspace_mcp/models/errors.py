
class MCPError(Exception):
    """Base exception for all MCP related errors"""
    
    def __init__(self, message: str, code: int = -32000, data: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}

class UnsupportedProtocolVersionError(MCPError):
    def __init__(self, message: str):
        super().__init__(message, code=-32022)

class HeaderMismatchError(MCPError):
    def __init__(self, message: str):
        super().__init__(message, code=-32000)

class YandexWorkspaceError(MCPError):
    """Base for domain logic errors"""
    
    def __init__(self, message: str, code: str = "workspace_error", retryable: bool = False):
        super().__init__(message, data={"code": code, "retryable": retryable})

class AuthenticationError(YandexWorkspaceError):
    def __init__(self, message: str = "Invalid or missing authentication"):
        super().__init__(message, code="authentication_error", retryable=False)

class PermissionDenied(YandexWorkspaceError):
    def __init__(self, message: str = "Permission denied for this operation"):
        super().__init__(message, code="permission_denied", retryable=False)

class InvalidPath(YandexWorkspaceError):
    def __init__(self, message: str = "Invalid or unauthorized path"):
        super().__init__(message, code="invalid_path", retryable=False)

class ResourceNotFound(YandexWorkspaceError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="resource_not_found", retryable=False)

class RevisionConflict(YandexWorkspaceError):
    def __init__(self, message: str = "The page changed since it was read."):
        super().__init__(message, code="revision_conflict", retryable=False)

class RateLimitExceeded(YandexWorkspaceError):
    def __init__(self, message: str = "Rate limit exceeded. Try again later."):
        super().__init__(message, code="rate_limit_exceeded", retryable=True)

class UpstreamUnavailable(YandexWorkspaceError):
    def __init__(self, message: str = "Yandex API is unavailable."):
        super().__init__(message, code="upstream_unavailable", retryable=True)

class APIError(YandexWorkspaceError):
    def __init__(self, message: str = "API returned an error."):
        super().__init__(message, code="api_error", retryable=False)

