from httpx import Request, Auth
from typing import Generator
from yandex_workspace_mcp.auth.models import AuthContext

class DiskAuth(Auth):
    def __init__(self, auth_context: AuthContext):
        self.auth_context = auth_context

    def auth_flow(self, request: Request) -> Generator[Request, None, None]:
        request.headers["Authorization"] = f"OAuth {self.auth_context.token.access_token}"
        yield request

class WikiAuth(Auth):
    def __init__(self, auth_context: AuthContext):
        self.auth_context = auth_context

    def auth_flow(self, request: Request) -> Generator[Request, None, None]:
        request.headers["Authorization"] = f"OAuth {self.auth_context.token.access_token}"
        if self.auth_context.wiki_org_id:
            request.headers["X-Org-Id"] = self.auth_context.wiki_org_id
        yield request
