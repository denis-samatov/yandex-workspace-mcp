import base64
import hashlib
import hmac
import importlib.util
import json

import pytest
from pydantic import ValidationError


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signed(payload: dict[str, object], key: bytes) -> str:
    encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def test_cursor_policy_module_exists() -> None:
    assert importlib.util.find_spec("yandex_workspace_mcp.policies.cursors") is not None


def test_disk_cursor_round_trip_and_bindings() -> None:
    from yandex_workspace_mcp.policies.cursors import CursorCodec, DiskSearchCursorV1

    codec = CursorCodec((b"a" * 32,))
    state = DiskSearchCursorV1(
        query_hash=codec.query_hash("  Report  "),
        principal_hash=codec.principal_hash("user-1"),
        offset=50,
        seen=["item-hash"],
    )

    token = codec.encode_disk(state)

    assert codec.decode_disk(token, query="report", principal="user-1") == state
    with pytest.raises(ValueError, match="cursor"):
        codec.decode_disk(token, query="other", principal="user-1")
    with pytest.raises(ValueError, match="cursor"):
        codec.decode_disk(token, query="report", principal="user-2")


def test_cursor_rejects_tampering_unknown_fields_and_oversize() -> None:
    from yandex_workspace_mcp.policies.cursors import CursorCodec

    key = b"a" * 32
    codec = CursorCodec((key,))
    valid = {
        "v": 1,
        "query_hash": codec.query_hash("q"),
        "principal_hash": codec.principal_hash("p"),
        "offset": 0,
        "seen": [],
    }

    token = _signed(valid, key)
    payload, signature = token.split(".")
    tampered = f"{payload[:-1]}A.{signature}"
    with pytest.raises(ValueError, match="cursor"):
        codec.decode_disk(tampered, query="q", principal="p")

    with pytest.raises(ValueError, match="cursor"):
        codec.decode_disk(_signed({**valid, "unknown": True}, key), query="q", principal="p")

    huge = _signed({**valid, "seen": ["x" * 9000]}, key)
    with pytest.raises(ValueError, match="cursor"):
        codec.decode_disk(huge, query="q", principal="p")


def test_cursor_models_enforce_bounds() -> None:
    from yandex_workspace_mcp.policies.cursors import (
        DiskSearchCursorV1,
        RootCursorState,
    )

    with pytest.raises(ValidationError):
        DiskSearchCursorV1(query_hash="q", principal_hash="p", offset=10_001)
    with pytest.raises(ValidationError):
        DiskSearchCursorV1(query_hash="q", principal_hash="p", offset=0, seen=["x"] * 101)
    with pytest.raises(ValidationError):
        RootCursorState(root_hash="r", cursor="x", pages=21)


def test_cursor_key_rotation_and_remote_key_policy() -> None:
    from yandex_workspace_mcp.policies.cursors import (
        CursorCodec,
        CursorKeyRing,
        DiskSearchCursorV1,
        RootCursorState,
        WikiDescendantsCursorState,
        WorkspaceCursorSources,
        WorkspaceCursorV1,
    )

    old_key = b"o" * 32
    new_key = b"n" * 32
    old_codec = CursorCodec((old_key,))
    state = DiskSearchCursorV1(
        query_hash=old_codec.query_hash("q"),
        principal_hash=old_codec.principal_hash("p"),
        offset=1,
    )
    old_token = old_codec.encode_disk(state)
    rotated = CursorCodec((new_key, old_key))

    assert rotated.decode_disk(old_token, query="q", principal="p").offset == 1

    old_workspace = WorkspaceCursorV1(
        query_hash=old_codec.query_hash("q"),
        principal_hash=old_codec.principal_hash("p"),
        sources=WorkspaceCursorSources(
            enabled=["wiki"],
            root_hashes=[old_codec.root_hash("/Team")],
            wiki_descendants=WikiDescendantsCursorState(
                roots=[
                    RootCursorState(root_hash=old_codec.root_hash("/Team"), cursor="next", pages=1)
                ]
            ),
        ),
    )
    assert (
        rotated.decode_workspace(
            old_codec.encode_workspace(old_workspace),
            query="q",
            principal="p",
            enabled_sources={"wiki"},
            allowed_roots={"/Team"},
        )
        == old_workspace
    )
    with pytest.raises(ValueError, match="cursor"):
        old_codec.decode_disk(
            rotated.encode_disk(
                DiskSearchCursorV1(
                    query_hash=rotated.query_hash("q"),
                    principal_hash=rotated.principal_hash("p"),
                    offset=2,
                )
            ),
            query="q",
            principal="p",
        )

    with pytest.raises(ValueError, match="MCP_CURSOR_KEYS"):
        CursorKeyRing.from_config([], remote=True)
    first_local = CursorKeyRing.from_config([], remote=False)
    second_local = CursorKeyRing.from_config([], remote=False)
    assert first_local.keys != second_local.keys


def test_workspace_cursor_binds_sources_and_roots() -> None:
    from yandex_workspace_mcp.policies.cursors import (
        CursorCodec,
        DiskOffsetState,
        RootCursorState,
        WikiDescendantsCursorState,
        WorkspaceCursorSources,
        WorkspaceCursorV1,
    )

    codec = CursorCodec((b"k" * 32,))
    root_hash = codec.root_hash("/Team")
    state = WorkspaceCursorV1(
        query_hash=codec.query_hash("q"),
        principal_hash=codec.principal_hash("p"),
        sources=WorkspaceCursorSources(
            enabled=["wiki", "disk"],
            disk=DiskOffsetState(offset=50),
            wiki_descendants=WikiDescendantsCursorState(
                roots=[RootCursorState(root_hash=root_hash, cursor="next", pages=1)]
            ),
        ),
        seen=["seen"],
    )
    token = codec.encode_workspace(state)

    decoded = codec.decode_workspace(
        token,
        query="q",
        principal="p",
        enabled_sources={"disk", "wiki"},
        allowed_roots={"/Team"},
    )
    assert decoded == state

    with pytest.raises(ValueError, match="cursor"):
        codec.decode_workspace(
            token,
            query="q",
            principal="p",
            enabled_sources={"disk"},
            allowed_roots={"/Team"},
        )
    with pytest.raises(ValueError, match="cursor"):
        codec.decode_workspace(
            token,
            query="q",
            principal="p",
            enabled_sources={"disk", "wiki"},
            allowed_roots={"/Other"},
        )
