import pytest

from yandex_workspace_mcp.auth.models import DownstreamCredentialRecord
from yandex_workspace_mcp.auth.stores import EncryptedRecordCodec, InMemoryTokenStore


def test_ciphertext_has_key_id_and_no_plaintext_secret() -> None:
    codec = EncryptedRecordCodec((b"a" * 32,))
    encrypted = codec.encrypt("downstream", "record-key", b'{"token":"secret-value"}')
    assert encrypted.key_id
    assert encrypted.nonce
    assert encrypted.ciphertext
    assert "secret-value" not in repr(encrypted)
    assert codec.decrypt("downstream", "record-key", encrypted) == b'{"token":"secret-value"}'


@pytest.mark.asyncio
async def test_rotated_key_ring_reads_old_ciphertext_and_new_writes_use_primary() -> None:
    records: dict[str, object] = {}
    old = InMemoryTokenStore((b"o" * 32,), records=records, clock=lambda: 100.0)
    record = DownstreamCredentialRecord(
        principal_id="principal",
        access_token="yandex-access-secret",
        refresh_token="yandex-refresh-secret",
        expires_at=200,
        organization_id="org",
    )
    await old.put_downstream("principal", record)
    assert "yandex-access-secret" not in repr(records)
    assert "yandex-refresh-secret" not in repr(records)

    rotated = InMemoryTokenStore((b"n" * 32, b"o" * 32), records=records, clock=lambda: 100.0)
    assert await rotated.get_downstream("principal") == record
