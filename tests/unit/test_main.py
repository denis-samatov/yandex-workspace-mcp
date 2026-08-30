import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from yandex_workspace_mcp import main as main_module
from yandex_workspace_mcp import server as server_module
from yandex_workspace_mcp.config import Settings


def test_serve_constructs_application_through_factory(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeMcp:
        def run(self, transport: str, **kwargs: object) -> None:
            calls.append((transport, kwargs))

    fake_application = SimpleNamespace(mcp_server=FakeMcp())
    created: list[Settings] = []

    def create(settings: Settings):
        created.append(settings)
        return fake_application

    monkeypatch.setattr(server_module, "create_application", create)
    monkeypatch.setattr(server_module, "mcp_server", FakeMcp())
    monkeypatch.setattr(sys, "argv", ["yandex-workspace-mcp", "serve", "--transport", "stdio"])

    main_module.main()

    assert len(created) == 1
    assert created[0].mcp_transport == "stdio"
    assert calls == [("stdio", {})]


def test_cli_http_override_is_validated_before_application_creation(monkeypatch) -> None:
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setattr(
        sys,
        "argv",
        ["yandex-workspace-mcp", "serve", "--transport", "streamable-http"],
    )

    with pytest.raises(ValidationError, match="authentication"):
        main_module.main()
