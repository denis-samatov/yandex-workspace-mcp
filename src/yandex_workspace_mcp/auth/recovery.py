import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Protocol

import anyio
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..models.errors import ConfigurationError, ResourceNotFound
from .models import RecoveryHandleRecord
from .stores import TokenStore, TokenStoreMiss

_AAD = b"yandex-workspace-mcp:wiki-recovery:v1"


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    upstream_token: str
    normalized_locator: str


@dataclass(frozen=True, slots=True)
class _StoredRecoveryRecord:
    encrypted_upstream_token: str
    principal_id: str
    normalized_locator: str
    expires_at: float


class RecoveryTokenStore(Protocol):
    async def put(
        self,
        *,
        upstream_token: str,
        principal_id: str,
        normalized_locator: str,
    ) -> str: ...

    async def consume(self, handle: str, *, principal_id: str) -> RecoveryRecord: ...

    async def close(self) -> None: ...


class InMemoryRecoveryTokenStore:
    def __init__(
        self,
        keys: tuple[bytes, ...],
        *,
        ttl_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        records: MutableMapping[str, object] | None = None,
    ) -> None:
        if not keys or any(len(key) < 32 for key in keys):
            raise ConfigurationError("Recovery encryption keys must contain at least 32 bytes.")
        self._keys = tuple(key[:32] for key in keys)
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._random_bytes = random_bytes
        self._records: MutableMapping[str, object] = records if records is not None else {}
        self._lock = anyio.Lock()
        self._closed = False

    async def put(
        self,
        *,
        upstream_token: str,
        principal_id: str,
        normalized_locator: str,
    ) -> str:
        if self._closed:
            raise ConfigurationError("Recovery token store is closed.")
        handle = self._encode(self._random_bytes(32))
        lookup = self._lookup_hash(self._keys[0], handle)
        nonce = self._random_bytes(12)
        ciphertext = AESGCM(self._keys[0]).encrypt(
            nonce,
            upstream_token.encode(),
            _AAD,
        )
        stored = _StoredRecoveryRecord(
            encrypted_upstream_token=self._encode(nonce + ciphertext),
            principal_id=principal_id,
            normalized_locator=normalized_locator,
            expires_at=self._clock() + self._ttl_seconds,
        )
        async with self._lock:
            self._records[lookup] = stored
        return handle

    async def consume(self, handle: str, *, principal_id: str) -> RecoveryRecord:
        if self._closed or not isinstance(handle, str):
            raise ResourceNotFound()
        async with self._lock:
            lookup = next(
                (
                    candidate
                    for key in self._keys
                    if (candidate := self._lookup_hash(key, handle)) in self._records
                ),
                None,
            )
            if lookup is None:
                raise ResourceNotFound()
            raw_record = self._records[lookup]
            if not isinstance(raw_record, _StoredRecoveryRecord):
                raise ResourceNotFound()
            if raw_record.expires_at <= self._clock():
                self._records.pop(lookup, None)
                raise ResourceNotFound()
            if not hmac.compare_digest(raw_record.principal_id, principal_id):
                raise ResourceNotFound()
            self._records.pop(lookup, None)

        token = self._decrypt(raw_record.encrypted_upstream_token)
        return RecoveryRecord(
            upstream_token=token,
            normalized_locator=raw_record.normalized_locator,
        )

    def _decrypt(self, encoded: str) -> str:
        encrypted = self._decode(encoded)
        if len(encrypted) < 13:
            raise ResourceNotFound()
        nonce, ciphertext = encrypted[:12], encrypted[12:]
        for key in self._keys:
            try:
                return AESGCM(key).decrypt(nonce, ciphertext, _AAD).decode()
            except (InvalidTag, UnicodeDecodeError):
                continue
        raise ResourceNotFound()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        async with self._lock:
            self._records.clear()

    @staticmethod
    def _lookup_hash(key: bytes, handle: str) -> str:
        return hmac.new(key, b"lookup\0" + handle.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, TypeError) as exc:
            raise ResourceNotFound() from exc


class SharedRecoveryTokenStore:
    """Recovery-handle adapter backed by the shared encrypted auth store."""

    def __init__(
        self,
        store: TokenStore,
        *,
        ttl_seconds: float = 900.0,
        clock: Callable[[], float] = time.time,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._store = store
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._random_bytes = random_bytes

    async def put(
        self,
        *,
        upstream_token: str,
        principal_id: str,
        normalized_locator: str,
    ) -> str:
        handle = InMemoryRecoveryTokenStore._encode(self._random_bytes(32))
        await self._store.put_recovery(
            handle,
            principal_id,
            RecoveryHandleRecord(
                principal_id=principal_id,
                upstream_token=upstream_token,
                normalized_locator=normalized_locator,
                expires_at=self._clock() + self._ttl_seconds,
            ),
        )
        return handle

    async def consume(self, handle: str, *, principal_id: str) -> RecoveryRecord:
        try:
            record = await self._store.consume_recovery(handle, principal_id)
        except TokenStoreMiss as exc:
            raise ResourceNotFound() from exc
        return RecoveryRecord(
            upstream_token=record.upstream_token,
            normalized_locator=record.normalized_locator,
        )

    async def close(self) -> None:
        # The application lifecycle owns and closes the shared backend.
        return None
