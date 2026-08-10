import httpx
import anyio
from typing import Optional, Dict, Any, Mapping
import structlog
from ..models.errors import UpstreamUnavailable, RateLimitExceeded

logger = structlog.get_logger()

class BaseYandexClient:
    def __init__(self, token: str, base_url: str, headers: Optional[Dict[str, str]] = None):
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
                        await anyio.sleep(2 ** attempt)
                        continue
                    raise RateLimitExceeded()
                if response.status_code in [502, 503, 504]:
                    if attempt < retries - 1:
                        await anyio.sleep(2 ** attempt)
                        continue
                    raise UpstreamUnavailable(f"Upstream returned {response.status_code}")
                
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                if attempt < retries - 1:
                    await anyio.sleep(2 ** attempt)
                    continue
                raise UpstreamUnavailable(f"Network error: {str(e)}")

    async def close(self):
        await self.client.aclose()
