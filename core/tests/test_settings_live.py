"""Ajustes desde la ventana de Ajustes (nyx/settings/live.py)."""

import json
from pathlib import Path

import pytest

from nyx.bus import EventBus
from nyx.events import SettingsChanged, SettingsRequested
from nyx.game.policy import GameGate
from nyx.settings import Settings
from nyx.settings.live import SettingsError, SettingsService


def _service(tmp_path: Path) -> tuple[SettingsService, Settings, Path]:
    settings = Settings()
    path = tmp_path / "settings.json"
    return SettingsService(EventBus(), settings, path), settings, path


def test_patch_is_applied_saved_and_live(tmp_path: Path) -> None:
    service, settings, path = _service(tmp_path)
    gate = GameGate(settings.game)  # como en services.py: guarda la sección, no una copia
    always = settings.game.always  # el detector de juegos guarda la lista
    restart = service.apply(
        {
            "game": {
                "mode": "normal",
                "always": ["juego.exe"],
                "policies": {"open_app": "blocked"},
            },
            "appearance": {"glass": {"edge": 7}},
        }
    )
    assert restart == []
    assert gate.mode == "normal"
    assert always == ["juego.exe"]  # misma lista, actualizada por dentro
    assert settings.game.policies == {"open_app": "blocked"}
    assert settings.appearance.glass.edge == 7
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["game"]["mode"] == "normal"
    assert saved["appearance"]["glass"]["edge"] == 7


def test_invalid_value_changes_nothing(tmp_path: Path) -> None:
    service, settings, path = _service(tmp_path)
    with pytest.raises(SettingsError, match=r"glass.edge"):
        service.apply({"appearance": {"glass": {"edge": 11}}})
    assert settings.appearance.glass.edge == 5
    assert not path.exists()


def test_only_editable_sections(tmp_path: Path) -> None:
    """La ruta de whisper-server y demás no se pueden cambiar desde Ajustes."""
    service, settings, _ = _service(tmp_path)
    with pytest.raises(SettingsError, match="stt"):
        service.apply({"stt": {"server": "C:/malo.exe"}})
    assert settings.stt.server is None


def test_policies_replace_instead_of_merge(tmp_path: Path) -> None:
    """Quitar una política la devuelve a su valor por defecto (el diccionario se sustituye)."""
    service, settings, _ = _service(tmp_path)
    service.apply({"game": {"policies": {"open_app": "blocked", "set_volume": "deferred"}}})
    service.apply({"game": {"policies": {"open_app": "blocked"}}})
    assert settings.game.policies == {"open_app": "blocked"}


async def test_requests_answer_with_current_settings(tmp_path: Path) -> None:
    bus = EventBus()
    settings = Settings()
    SettingsService(bus, settings, tmp_path / "settings.json")
    got: list[SettingsChanged] = []

    async def collect(event: SettingsChanged) -> None:
        got.append(event)

    bus.subscribe(SettingsChanged, collect)
    await bus.publish(SettingsRequested())
    await bus.publish(SettingsRequested({"responses": {"speak_typed": True}}))
    await bus.publish(SettingsRequested({"responses": {"speak_typed": "quizá"}}))
    assert [e.error is None for e in got] == [True, True, False]
    assert got[1].data["responses"]["speak_typed"] is True
    assert got[2].data["responses"]["speak_typed"] is True  # el cambio malo no se aplicó
