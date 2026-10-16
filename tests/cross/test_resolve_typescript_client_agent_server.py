"""Tests for the TypeScript client pinned Agent Server resolver."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_prod_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / ".github" / "scripts" / "resolve_typescript_client_agent_server.py"
    )
    name = "resolve_typescript_client_agent_server"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_prod = _load_prod_module()


def _fixture(root: Path, pinned: str, source: str) -> tuple[Path, Path]:
    client = root / "client"
    client.mkdir()
    image = f"ghcr.io/openhands/agent-server:{pinned}-python"
    (client / "package.json").write_text(
        json.dumps({"config": {"agentServerImage": image}})
    )
    pyproject = root / "pyproject.toml"
    pyproject.write_text(f'[project]\nname = "x"\nversion = "{source}"\n')
    return client, pyproject


def test_source_pin_uses_source_contract_even_when_release_is_published(tmp_path):
    client, pyproject = _fixture(tmp_path, "1.53.0", "1.53.0")

    assert _prod.resolve(client, pyproject) == {
        "pinned_version": "1.53.0",
        "pinned_is_source": "true",
        "use_source_contract": "true",
    }


def test_pin_behind_source_uses_its_pinned_release_contract(tmp_path):
    client, pyproject = _fixture(tmp_path, "1.52.0", "1.53.0")

    result = _prod.resolve(client, pyproject)

    assert result == {
        "pinned_version": "1.52.0",
        "pinned_is_source": "false",
        "use_source_contract": "false",
    }


def test_rejects_non_release_pin(tmp_path):
    client, pyproject = _fixture(tmp_path, "1.53.0", "1.53.0")
    (client / "package.json").write_text(
        json.dumps({"config": {"agentServerImage": "agent-server:latest"}})
    )

    with pytest.raises(SystemExit, match="exact release tag"):
        _prod.resolve(client, pyproject)
