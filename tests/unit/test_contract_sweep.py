import argparse
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from scripts import contract_sweep


class _CloseTracked:
    def __init__(self, **_kwargs) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_live_sweep_awaits_both_paths_and_gates_cleanup_report(monkeypatch, tmp_path) -> None:
    clients: list[_CloseTracked] = []

    def client_factory(**kwargs):
        client = _CloseTracked(**kwargs)
        clients.append(client)
        return client

    async def wiki(*_args, **_kwargs):
        return [{"operation": "wiki", "status": "drift", "error": "ContractMismatch"}]

    async def disk(*_args, **_kwargs):
        return [{"operation": "cleanup", "status": "cleanup_failed", "error": "Timeout"}]

    monkeypatch.setattr(
        contract_sweep,
        "get_settings",
        lambda: SimpleNamespace(
            yandex_oauth_token=SecretStr("token"),
            yandex_wiki_org_id=None,
            yandex_wiki_is_cloud_org=False,
        ),
    )
    monkeypatch.setattr(contract_sweep, "YandexWikiClient", client_factory)
    monkeypatch.setattr(contract_sweep, "YandexDiskClient", client_factory)
    monkeypatch.setattr(contract_sweep, "SignedTransferClient", client_factory)
    monkeypatch.setattr(contract_sweep, "_wiki_sweep", wiki)
    monkeypatch.setattr(contract_sweep, "_disk_sweep", disk)
    report_path = tmp_path / "report.json"
    args = argparse.Namespace(
        wiki_scratch_root="Team/Test",
        disk_scratch_root="/Test",
        query="q",
        report=report_path,
    )

    with pytest.raises(SystemExit) as caught:
        await contract_sweep.run(args)

    assert caught.value.code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["cleanup_ok"] is False
    assert report["success"] is False
    assert all(client.closed for client in clients)
