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


def test_error_codes_are_in_the_catalog() -> None:
    """Cada código del núcleo está explicado en docs/CODIGOS-DE-ERROR.md (la página de la web)."""
    from nyx import errors

    catalog = (Path(__file__).resolve().parents[2] / "docs" / "CODIGOS-DE-ERROR.md").read_text(
        encoding="utf-8"
    )
    codes = [v for k, v in vars(errors).items() if k.isupper() and isinstance(v, str)]
    codes = [c for c in codes if errors.CODE.match(c)]
    assert len(codes) >= 5
    for code in codes:
        assert f"| {code} |" in catalog, code
    assert errors.code_of(errors.coded("D-201", "x")) == "D-201"
    assert errors.code_of("sin código") is None


async def test_a_failed_download_carries_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nyx.events import SetupResult

    bus = EventBus()
    seen: list[Any] = []

    async def on_any(e: Any) -> None:
        seen.append(e)

    bus.subscribe(SetupProgress, on_any)
    bus.subscribe(SetupResult, on_any)
    model = models.ModelFile(
        key="vad", filename="vad.onnx", url="https://x", sha256="0", size_mb=2, license="MIT"
    )
    from nyx.setup import service as setup_service

    monkeypatch.setattr(setup_service, "CATALOG", (model,))
    monkeypatch.setattr(setup_service, "is_present", lambda _m: False)

    def broken(*_: object, **__: object) -> None:
        raise models.DownloadError("vad.onnx: la huella SHA-256 no coincide", "D-202")

    monkeypatch.setattr(setup_service, "download", broken)
    service = SetupService(bus, Settings(), root=tmp_path)

    async def ollama_ready() -> bool:
        return True  # sin tocar el Ollama de verdad (en CI no lo hay e intentaba instalarlo)

    monkeypatch.setattr(service, "_pull_ollama", ollama_ready)
    await service._download()
    errors_seen = [e.error for e in seen if isinstance(e, SetupProgress) and e.error]
    assert errors_seen[0].startswith("D-202 · ")
    result = [e for e in seen if isinstance(e, SetupResult)][-1]
    assert not result.ok and (result.message or "").startswith("D-202 · ")


async def test_nyx_brain_replaces_the_stock_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9.08b: con el modelo de serie, el primer arranque baja el cerebro de Nyx y lo usa."""
    from nyx.events import SettingsRequested
    from nyx.setup import brain

    bus = EventBus()
    patches: list[Any] = []

    async def on_settings(e: SettingsRequested) -> None:
        patches.append(e.patch)

    bus.subscribe(SettingsRequested, on_settings)
    service = SetupService(bus, Settings(), root=tmp_path)

    async def status() -> dict[str, Any]:
        return {"running": True, "models": [], "wanted": "qwen2.5:7b", "has_wanted": False}

    async def ensure(host: str, progress: Any, **_: Any) -> str:
        await progress(1.0, 2.0)
        return "nyx-r2:7b"

    async def running() -> bool:
        return True

    monkeypatch.setattr(service, "_ollama_status", status)
    monkeypatch.setattr(service, "_ensure_ollama", running)
    monkeypatch.setattr(brain, "ensure", ensure)
    assert await service._pull_ollama()
    assert {"llm": {"model": "nyx-r2:7b"}} in patches
