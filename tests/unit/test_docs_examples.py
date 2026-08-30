import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_increment_one_documentation_names_runtime_contracts() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    security = Path("docs/security.md").read_text(encoding="utf-8")
    skill = Path("skills/yandex-workspace/SKILL.md").read_text(encoding="utf-8")

    assert "YANDEX_API_DOCS_WIRE_DRIFT" in readme
    assert "MCP_CURSOR_KEYS" in readme
    assert "POST /v1/search" in readme
    assert "create_application" in architecture
    assert "logical read" in architecture
    assert "signed cursor" in security
    assert "descendants" in skill


def test_contract_sweep_help_is_non_live() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/contract_sweep.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--acknowledge-live" in result.stdout
    assert "--wiki-scratch-root" in result.stdout


def test_contract_sweep_rejects_disk_service_root_before_credentials() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/contract_sweep.py",
            "--acknowledge-live",
            "--wiki-scratch-root",
            "contract-sweep",
            "--disk-scratch-root",
            "disk:/",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "scratch roots must not be service roots" in result.stderr


def test_auth_and_deployment_docs_cover_separate_credentials_and_profiles() -> None:
    auth = Path("docs/authentication.md").read_text(encoding="utf-8")
    deployment = Path("docs/deployment.md").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "MCP client authentication and Yandex credentials are separate" in auth
    assert "MCP_AUTH_MODE=static" in auth
    assert "MCP_AUTH_MODE=local" in auth
    assert "MCP_TRUSTED_PROXY_CIDRS" in auth
    assert "server's isolated tokenless transport" in deployment
    assert 'profiles: ["static"]' in compose
    assert 'profiles: ["multi-user"]' in compose
    assert "MCP_AUTH_MODE=local" in env_example
    assert "YANDEX_AUTH_MODE=oauth" in env_example


def test_ci_and_live_workflow_have_required_matrix_and_safety_gates() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    live = Path(".github/workflows/live-contract.yml").read_text(encoding="utf-8")

    for value in ("ubuntu-latest", "macos-latest", "windows-latest", '"3.12"', '"3.13"'):
        assert value in ci
    assert "scripts/generate_schema_snapshots.py" in ci
    assert "workflow_dispatch" in live
    assert "schedule:" in live
    assert "secrets.YANDEX_OAUTH_TOKEN" in live
    assert "github.run_id" in live
    assert "if: always()" in live
    assert "pull_request" not in live.split("permissions:", 1)[0]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI is not installed")
def test_compose_configuration_parses() -> None:
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
