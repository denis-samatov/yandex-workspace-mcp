import pytest
import os
from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.models.errors import APIError

@pytest.mark.asyncio
async def test_ssrf_protection_in_disk_client():
    client = YandexDiskClient("fake_token")
    
    # We will mock the get_download_url to return a malicious URL
    # and verify that read_file_text rejects it.
    
    class MockClient(YandexDiskClient):
        async def get_download_url(self, path: str) -> str:
            return "https://169.254.169.254/latest/meta-data/"
            
    malicious_client = MockClient("fake")
    
    with pytest.raises(APIError, match="Invalid download URL domain returned by Yandex"):
        await malicious_client.read_file_text("/some/file.txt")

@pytest.mark.asyncio
async def test_ssrf_protection_valid_domain():
    class MockClient(YandexDiskClient):
        async def get_download_url(self, path: str) -> str:
            return "https://downloader.disk.yandex.net/test"
            
    valid_client = MockClient("fake")
    # This will fail on httpx connection because the URL is fake, but it should NOT raise the SSRF APIError
    with pytest.raises(Exception):
        try:
            await valid_client.read_file_text("/some/file.txt")
        except APIError as e:
            if "Invalid download URL" in str(e):
                pytest.fail("Should not reject valid domain")
            raise
