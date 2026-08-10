import random

import anyio
import httpx
import structlog

from ..models.errors import RateLimitExceeded, UpstreamUnavailable

logger = structlog.get_logger()

class BaseYandexClient:
    def __init__(self, token: str, base_url: str, headers: dict[str, str] | None = None):
        self.base_url = base_url
        self.token = token
        
        default_headers = {
            "Authorization": f"OAuth {self.token}",
            "Accept": "application/json"
        }
        if headers:
            default_headers.update(headers)
            
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=default_headers,
            timeout=httpx.Timeout(10.0, connect=5.0)
        )

    async def _request(self, method: str, path: str, retries: int = 3, **kwargs) -> httpx.Response:
        for attempt in range(retries):
            try:
                response = await self.client.request(method, path, **kwargs)
                if response.status_code == 429:
                    if attempt < retries - 1:
                        retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                        jitter = random.uniform(0, 0.1 * retry_after)
                        await anyio.sleep(retry_after + jitter)
                        continue
                    raise RateLimitExceeded()
                if response.status_code in [502, 503, 504]:
                    # For non-idempotent methods, we might want to avoid retrying. 
                    # We will assume GET/PUT/DELETE are generally idempotent in our usage.
                    if method.upper() not in ["GET", "PUT", "DELETE"]:
                        raise UpstreamUnavailable(f"Upstream returned {response.status_code}. Not retrying non-idempotent {method}.")
                    if attempt < retries - 1:
                        jitter = random.uniform(0, 0.1 * (2 ** attempt))
                        await anyio.sleep((2 ** attempt) + jitter)
                        continue
                    raise UpstreamUnavailable(f"Upstream returned {response.status_code}")
                
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                if method.upper() not in ["GET", "PUT", "DELETE"]:
                    raise UpstreamUnavailable(f"Network error: {e!s}. Not retrying non-idempotent {method}.")
                if attempt < retries - 1:
                    jitter = random.uniform(0, 0.1 * (2 ** attempt))
                    await anyio.sleep((2 ** attempt) + jitter)
                    continue
                raise UpstreamUnavailable(f"Network error: {e!s}")
        raise UpstreamUnavailable("Failed to complete request (exhausted retries or 0 retries).")

    async def close(self):
        await self.client.aclose()
