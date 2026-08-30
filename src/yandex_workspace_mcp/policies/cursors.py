import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import Field

from ..models.base import PublicModel

_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_DECODED_BYTES = 8 * 1024


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    if not value or not _B64URL_RE.fullmatch(value):
        raise ValueError("invalid cursor encoding")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid cursor encoding") from exc


def _normalized_query(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


class DiskSearchCursorV1(PublicModel):
    v: Literal[1] = 1
    query_hash: str
    principal_hash: str
    offset: Annotated[int, Field(ge=0, le=10_000)]
    seen: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)


class DiskOffsetState(PublicModel):
    offset: Annotated[int, Field(ge=0, le=10_000)]


class UploadJobCursorV1(PublicModel):
    v: Literal[1] = 1
    principal_hash: str
    filter_hash: str
    offset: Annotated[int, Field(ge=0, le=10_000)]


class RootCursorState(PublicModel):
    root_hash: str
    cursor: Annotated[str, Field(min_length=1, max_length=4096)]
    pages: Annotated[int, Field(ge=0, le=20)]


class WikiDescendantsCursorState(PublicModel):
    roots: Annotated[list[RootCursorState], Field(max_length=20)] = Field(default_factory=list)


class WorkspaceCursorSources(PublicModel):
    enabled: Annotated[list[Literal["disk", "wiki"]], Field(min_length=1, max_length=2)]
    root_hashes: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    disk: DiskOffsetState | None = None
    wiki_descendants: WikiDescendantsCursorState | None = None


class WorkspaceCursorV1(PublicModel):
    v: Literal[1] = 1
    query_hash: str
    principal_hash: str
    sources: WorkspaceCursorSources
    seen: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)


class CursorKeyRing:
    def __init__(self, keys: tuple[bytes, ...]) -> None:
        if not keys or any(len(key) < 32 for key in keys):
            raise ValueError("MCP_CURSOR_KEYS entries must decode to at least 32 bytes")
        self.keys = keys

    @classmethod
    def from_config(cls, values: Iterable[str], *, remote: bool) -> "CursorKeyRing":
        encoded = tuple(value for value in values if value)
        if not encoded:
            if remote:
                raise ValueError("MCP_CURSOR_KEYS is required for remote mode")
            return cls((secrets.token_bytes(32),))
        return cls(tuple(_decode_base64url(value) for value in encoded))


class CursorCodec:
    def __init__(self, keys: tuple[bytes, ...]) -> None:
        self._key_ring = CursorKeyRing(keys)

    def query_hash(self, query: str) -> str:
        return hashlib.sha256(_normalized_query(query).encode("utf-8")).hexdigest()

    def principal_hash(self, principal: str) -> str:
        return self._identity_hash("principal", principal)

    def root_hash(self, root: str) -> str:
        return self._identity_hash("root", root)

    def item_hash(self, source: str, identity: str) -> str:
        return self._identity_hash(f"item:{source}", identity)

    def _identity_hash(self, kind: str, value: str) -> str:
        return self._identity_hash_with_key(self._key_ring.keys[0], kind, value)

    @staticmethod
    def _identity_hash_with_key(key: bytes, kind: str, value: str) -> str:
        digest = hmac.new(
            key,
            f"{kind}\0{value}".encode(),
            hashlib.sha256,
        ).digest()
        return _encode_base64url(digest[:16])

    def encode_disk(self, state: DiskSearchCursorV1) -> str:
        return self._encode(state.model_dump(mode="json"))

    def decode_disk(self, token: str, *, query: str, principal: str) -> DiskSearchCursorV1:
        payload = self._decode(token)
        try:
            state = DiskSearchCursorV1.model_validate(payload)
        except Exception as exc:
            raise ValueError("invalid cursor payload") from exc
        if not hmac.compare_digest(state.query_hash, self.query_hash(query)):
            raise ValueError("cursor query binding mismatch")
        if not self._matches_principal(state.principal_hash, principal):
            raise ValueError("cursor principal binding mismatch")
        return state

    def encode_upload_jobs(self, state: UploadJobCursorV1) -> str:
        return self._encode(state.model_dump(mode="json"))

    def decode_upload_jobs(
        self,
        token: str,
        *,
        principal: str,
        status: str | None,
    ) -> UploadJobCursorV1:
        payload = self._decode(token)
        try:
            state = UploadJobCursorV1.model_validate(payload)
        except Exception as exc:
            raise ValueError("invalid cursor payload") from exc
        if not self._matches_principal(state.principal_hash, principal):
            raise ValueError("cursor principal binding mismatch")
        if not hmac.compare_digest(state.filter_hash, self.query_hash(status or "*")):
            raise ValueError("cursor filter binding mismatch")
        return state

    def encode_workspace(self, state: WorkspaceCursorV1) -> str:
        return self._encode(state.model_dump(mode="json"))

    def decode_workspace(
        self,
        token: str,
        *,
        query: str,
        principal: str,
        enabled_sources: set[str],
        allowed_roots: set[str],
    ) -> WorkspaceCursorV1:
        payload = self._decode(token)
        try:
            state = WorkspaceCursorV1.model_validate(payload)
        except Exception as exc:
            raise ValueError("invalid cursor payload") from exc
        if not hmac.compare_digest(state.query_hash, self.query_hash(query)):
            raise ValueError("cursor query binding mismatch")
        if not self._matches_principal(state.principal_hash, principal):
            raise ValueError("cursor principal binding mismatch")
        if set(state.sources.enabled) != enabled_sources:
            raise ValueError("cursor source binding mismatch")

        encoded_roots = set(state.sources.root_hashes)
        if not encoded_roots and state.sources.wiki_descendants:
            encoded_roots = {item.root_hash for item in state.sources.wiki_descendants.roots}
        valid_root_sets = [
            {self._identity_hash_with_key(key, "root", root) for root in allowed_roots}
            for key in self._key_ring.keys
        ]
        if encoded_roots not in valid_root_sets:
            raise ValueError("cursor root binding mismatch")
        return state

    def _matches_principal(self, stored: str, principal: str) -> bool:
        matches = [
            hmac.compare_digest(
                stored,
                _encode_base64url(
                    hmac.new(
                        key,
                        f"principal\0{principal}".encode(),
                        hashlib.sha256,
                    ).digest()[:16]
                ),
            )
            for key in self._key_ring.keys
        ]
        return any(matches)

    def _encode(self, payload: dict[str, object]) -> str:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(raw) > _MAX_DECODED_BYTES:
            raise ValueError("cursor payload is too large")
        encoded = _encode_base64url(raw)
        signature = hmac.new(
            self._key_ring.keys[0], encoded.encode("ascii"), hashlib.sha256
        ).digest()
        return f"{encoded}.{_encode_base64url(signature)}"

    def _decode(self, token: str) -> dict[str, object]:
        if token.count(".") != 1:
            raise ValueError("invalid cursor format")
        encoded, supplied_signature = token.split(".", 1)
        raw = _decode_base64url(encoded)
        signature = _decode_base64url(supplied_signature)
        if len(raw) > _MAX_DECODED_BYTES or len(signature) != hashlib.sha256().digest_size:
            raise ValueError("invalid cursor size")
        matches = [
            hmac.compare_digest(
                signature,
                hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest(),
            )
            for key in self._key_ring.keys
        ]
        if not any(matches):
            raise ValueError("invalid cursor signature")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid cursor JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("invalid cursor payload")
        return payload
