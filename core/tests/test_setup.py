"""Asistente de primer arranque y Ajustes → Cerebro, Caché, Ayuda y Privacidad (nyx/setup)."""

from pathlib import Path
from typing import Any

import pytest

from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import SetupRequested, SetupResult, SetupStatusChanged
from nyx.executor import ToolCall
from nyx.index.service import SystemIndex
from nyx.settings import Settings
from nyx.setup import service as setup_service
from nyx.setup.service import SetupService


def _settings() -> Settings:
    s = Settings()
    s.llm.host = "http://127.0.0.1:9"  # nada escucha ahí: «Ollama no está en marcha»
    return s


class Collect:
    def __init__(self, bus: EventBus) -> None:
        self.status: list[dict[str, Any]] = []
        self.results: list[SetupResult] = []
        bus.subscribe(SetupStatusChanged, self._status)
        bus.subscribe(SetupResult, self._result)

    async def _status(self, e: SetupStatusChanged) -> None:
        self.status.append(e.status)

    async def _result(self, e: SetupResult) -> None:
        self.results.append(e)


async def test_status_lists_models_index_and_shortcuts(tmp_path: Path, index: SystemIndex) -> None:
    bus = EventBus()
    store = ShortcutStore(tmp_path / "s.db")
    store.learn("abre riot client", ToolCall("open_app", {"name": "Riot Client"}), "green")
    SetupService(
        bus,
        _settings(),
        index=lambda: index,
        shortcuts=lambda: store,
        whisper_server=lambda: tmp_path / "no-existe.exe",
        root=tmp_path,
    )
    got = Collect(bus)
    await bus.publish(SetupRequested("status"))
    status = got.status[-1]
    assert {m["key"] for m in status["models"]} >= {"vad", "stt"}
    assert status["ollama"]["running"] is False
    assert status["whisper"] is False
    assert status["index"]["total"] == len(index) > 0
    # Recién aprendido: aún no se ha usado como atajo.
    assert status["shortcuts"] == [{"phrase": "abre riot client", "tool": "open_app", "uses": 0}]


async def test_forget_shortcut(tmp_path: Path) -> None:
    bus = EventBus()
    store = ShortcutStore(tmp_path / "s.db")
    store.learn("abre riot client", ToolCall("open_app", {"name": "Riot Client"}), "green")
    SetupService(bus, _settings(), shortcuts=lambda: store, root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("forget_shortcut", "abre riot client"))
    assert got.results[-1].ok
    assert got.status[-1]["shortcuts"] == []


async def test_forget_all_shortcuts(tmp_path: Path) -> None:
    bus = EventBus()
    store = ShortcutStore(tmp_path / "s.db")
    store.learn("abre riot client", ToolCall("open_app", {"name": "Riot Client"}), "green")
    store.learn("abre discord", ToolCall("open_app", {"name": "Discord"}), "green")
    SetupService(bus, _settings(), shortcuts=lambda: store, root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("forget_all_shortcuts"))
    assert got.results[-1].ok and got.results[-1].action == "forget_all_shortcuts"
    assert got.status[-1]["shortcuts"] == []
    assert store.lookup("abre discord") is None


async def test_clear_goes_to_the_recycle_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Las grabaciones se mandan a la papelera (nunca borrado permanente)."""
    trashed: list[str] = []
    import send2trash

    monkeypatch.setattr(send2trash, "send2trash", trashed.append)
    folder = tmp_path / "training" / "grabaciones" / "positivos"
    folder.mkdir(parents=True)
    (folder / "nyx-1.wav").write_bytes(b"RIFF")
    bus = EventBus()
    SetupService(bus, _settings(), root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("status"))
    assert got.status[-1]["samples"] == 1
    await bus.publish(SetupRequested("clear_samples"))
    assert trashed == [str(tmp_path / "training" / "grabaciones")]
    assert got.results[-1].ok


async def test_download_with_nothing_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin nada que descargar y con Ollama ya abierto y con el cerebro: termina bien y vuelve
    a mandar el estado."""
    monkeypatch.setattr(setup_service, "CATALOG", ())

    async def ready(_: object) -> dict[str, object]:
        return {"running": True, "models": ["x"], "wanted": "x", "has_wanted": True}

    monkeypatch.setattr(setup_service.SetupService, "_ollama_status", ready)
    bus = EventBus()
    SetupService(bus, _settings(), root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("download"))
    assert got.results[-1].ok and got.results[-1].action == "download"
    assert got.status[-1]["downloading"] is False


@pytest.mark.parametrize(
    ("vram", "model"),
    [(None, "qwen2.5:7b"), (2.0, "qwen2.5:7b"), (8.0, "qwen2.5:7b"), (12.0, "qwen2.5:7b")],
)
def test_recommended_model_by_gpu_memory(vram: float | None, model: str) -> None:
    """El más capaz que cabe entero en la GPU; sin tarjeta conocida, el de por defecto."""
    from nyx.setup.hardware import recommend

    assert recommend(vram) == model


async def test_status_has_llm_choices_and_everything(tmp_path: Path) -> None:
    bus = EventBus()
    SetupService(bus, _settings(), root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("status"))
    status = got.status[-1]
    assert {c["id"] for c in status["llm"]["choices"]} == {"qwen2.5:7b"}  # uno solo (2026-11-11)
    assert status["llm"]["recommended"] in {c["id"] for c in status["llm"]["choices"]}
    assert set(status["everything"]) == {"installed", "running", "cli"}


async def test_download_without_ollama_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin Ollama y sin poder instalarlo (9.08): la descarga termina con el aviso."""
    monkeypatch.setattr(setup_service, "CATALOG", ())
    bus = EventBus()
    SetupService(bus, _settings(), root=tmp_path)
    got = Collect(bus)
    await bus.publish(SetupRequested("download"))
    assert not got.results[-1].ok and got.results[-1].action == "download"
