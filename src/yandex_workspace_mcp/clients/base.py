import asyncio
import httpx
from typing import Any, Callable
from yandex_workspace_mcp.exceptions import (
    AuthenticationError,
    PermissionDenied,
    ResourceNotFound,
    RateLimitExceeded,
    ConflictError,
    APIError,
)
from yandex_workspace_mcp.logging import get_logger

logger = get_logger(__name__)

class BaseClient:
    """Base API client with retry logic and error mapping."""

    def __init__(self, auth_flow: Callable, base_url: str):
        self.auth_flow = auth_flow
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth_flow,
            timeout=httpx.Timeout(30.0)
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute request with exponential backoff for transient errors."""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                if response.status_code < 400:
                    return response
                
                # Check if it's a transient error that should be retried
                if response.status_code in (429, 502, 503, 504):
                    if attempt < max_retries:
                        retry_after = float(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                        logger.warning("Transient API error, retrying...", status_code=response.status_code, url=url, attempt=attempt)
                        await asyncio.sleep(retry_after)
                        continue

                self._handle_error(response)
                
            except httpx.RequestError as e:
                if attempt < max_retries:
                    logger.warning("Network error, retrying...", error=str(e), url=url, attempt=attempt)
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
                raise APIError(f"Network error: {str(e)}") from e

        raise APIError("Maximum retries exceeded")

    def _handle_error(self, response: httpx.Response) -> None:
        """Map HTTP errors to custom exceptions."""
        try:
            error_data = response.json()
        except ValueError:
            error_data = {"message": response.text}

        message = error_data.get("message") or error_data.get("description") or "Unknown API Error"
        
        status_code = response.status_code
        if status_code == 401:
            raise AuthenticationError(message)
        elif status_code == 403:
            raise PermissionDenied(message)
        elif status_code == 404:
            raise ResourceNotFound(message)
        elif status_code == 409:
            raise ConflictError(message)
        elif status_code == 429:
            raise RateLimitExceeded(message)
        else:
            raise APIError(f"HTTP {status_code}: {message}", status_code=status_code, response_data=error_data)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", url, **kwargs)
