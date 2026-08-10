from pydantic import BaseModel


class OAuthToken(BaseModel):
    access_token: str

class AuthContext(BaseModel):
    token: OAuthToken
    wiki_org_id: str | None = None
