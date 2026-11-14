"""Lo que el núcleo hace para el instalador (9.08): progreso en JSON, Ollama si falta, lo
elegido en el instalador y el whisper-server empaquetado."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from nyx import models, services
from nyx.bus import EventBus
from nyx.events import SetupProgress
from nyx.settings.model import Settings
from nyx.setup import flow as flow_module
from nyx.setup import ollama
from nyx.setup.service import SetupService


def test_download_progress_as_json_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    present = models.ModelFile(
        key="vad", filename="vad.onnx", url="https://x", sha256="0", size_mb=2, license="MIT"
    )
    (tmp_path / "vad.onnx").write_bytes(b"x")
    monkeypatch.setattr(models, "CATALOG", (present,))
    monkeypatch.setattr(models, "download_pocket", lambda: None)
    assert models.download_all(tmp_path, json_lines=True) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0] == {
        "key": "vad", "label": "vad.onnx", "done_mb": 2, "total_mb": 2,
        "finished": True, "error": None,
    }  # fmt: skip
    assert lines[-1]["key"] == "pocket" and lines[-1]["finished"] is True


async def test_ollama_is_installed_and_started_before_the_brain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = EventBus()
    seen: list[SetupProgress] = []

    async def on_progress(e: SetupProgress) -> None:
        seen.append(e)

    bus.subscribe(SetupProgress, on_progress)
    service = SetupService(bus, Settings(), root=tmp_path)
    calls: list[str] = []

    async def status() -> dict[str, Any]:
        return {"running": "start" in calls, "models": [], "wanted": "x", "has_wanted": True}

    async def install() -> bool:
        calls.append("install")
        return True

    async def start(host: str) -> bool:
        calls.append("start")
        return True

    monkeypatch.setattr(service, "_ollama_status", status)
    monkeypatch.setattr(ollama, "installed", lambda: False)
    monkeypatch.setattr(ollama, "install", install)
    monkeypatch.setattr(ollama, "start", start)
    assert await service._pull_ollama()
    assert calls == ["install", "start"]
    assert [e.key for e in seen] == ["ollama-app", "ollama-app"] and seen[-1].finished


async def test_ollama_that_cannot_be_installed_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus = EventBus()
    seen: list[SetupProgress] = []

    async def on_progress(e: SetupProgress) -> None:
        seen.append(e)

    bus.subscribe(SetupProgress, on_progress)
    service = SetupService(bus, Settings(), root=tmp_path)

    async def status() -> dict[str, Any]:
        return {"running": False, "models": [], "wanted": "x", "has_wanted": False}

    async def nope() -> bool:
        return False

    monkeypatch.setattr(service, "_ollama_status", status)
    monkeypatch.setattr(ollama, "installed", lambda: False)
    monkeypatch.setattr(ollama, "install", nope)
    assert not await service._pull_ollama()
    assert seen[-1].error


def test_installer_choices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flow_module, "roaming_dir", lambda: tmp_path)
    assert flow_module.installer_choices() == {}
    (tmp_path / "instalador.json").write_text('{"everything": true}', encoding="utf-8")
    assert flow_module.installer_choices() == {"everything": True}
    (tmp_path / "instalador.json").write_text("roto", encoding="utf-8")
    assert flow_module.installer_choices() == {}


def test_packaged_whisper_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    python = tmp_path / "core" / "python"
    exe = tmp_path / "core" / "bin" / "whisper" / "whisper-server.exe"
    exe.parent.mkdir(parents=True)
    python.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "prefix", str(python))
    assert services.whisper_server_path(Settings()) == exe
    exe.unlink()
    assert services.whisper_server_path(Settings()).name == "whisper-server.exe"
    assert services.whisper_server_path(Settings()) != exe


def test_download_models_json_flag() -> None:
    """El instalador lanza `python -m nyx --download-models --json` (9.08)."""
    from nyx.main import parse_args

    args = parse_args(["--download-models", "--json"])
    assert args.download_models and args.json
    assert not parse_args([]).json
