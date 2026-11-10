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


def test_only_listed_settings_inside_a_section(tmp_path: Path) -> None:
    """En Voz y Activación solo se tocan los ajustes de la ventana, no toda la sección."""
    service, settings, _ = _service(tmp_path)
    service.apply({"tts": {"voice": "davefx", "speed": 1.2}, "wake": {"sensitivity": 8}})
    assert (settings.tts.voice, settings.wake.sensitivity) == ("davefx", 8)
    with pytest.raises(SettingsError, match=r"listen.max_s"):
        service.apply({"listen": {"max_s": 30}})
    with pytest.raises(SettingsError, match=r"llm.host"):
        service.apply({"llm": {"host": "http://otro-equipo:11434"}})


def test_restart_is_reported_for_voice_and_activation(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    restart = service.apply({"tts": {"speed": 1.3}, "appearance": {"nyx_color": "rojo"}})
    assert restart == ["tts.speed"]


def test_custom_wake_word_is_checked(tmp_path: Path) -> None:
    service, settings, _ = _service(tmp_path)
    with pytest.raises(SettingsError, match="sílabas"):
        service.apply({"wake": {"custom_word": "sol"}})
    assert settings.wake.custom_word == ""
    service.apply({"wake": {"custom_word": "oye lumen"}})
    assert settings.wake.custom_word == "oye lumen"


def test_unknown_color_is_rejected(tmp_path: Path) -> None:
    service, settings, _ = _service(tmp_path)
    with pytest.raises(SettingsError, match="nyx_color"):
        service.apply({"appearance": {"nyx_color": "morado-chillón"}})
    assert settings.appearance.nyx_color == "blanco"


async def test_reading_lists_audio_devices(tmp_path: Path) -> None:
    bus = EventBus()
    SettingsService(
        bus, Settings(), tmp_path / "s.json", devices=lambda: (["Micro USB"], ["Altavoces"])
    )
    got: list[SettingsChanged] = []

    async def collect(event: SettingsChanged) -> None:
        got.append(event)

    bus.subscribe(SettingsChanged, collect)
    await bus.publish(SettingsRequested())
    await bus.publish(SettingsRequested({"tts": {"enabled": False}}))
    assert got[0].inputs == ("Micro USB",) and got[0].outputs == ("Altavoces",)
    assert got[1].inputs == ()  # al cambiar algo no se vuelven a listar


async def test_restart_notice_goes_away_when_reverted(tmp_path: Path) -> None:
    """Cambiar la voz pide reiniciar; volver a dejarla como estaba, ya no."""
    bus = EventBus()
    SettingsService(bus, Settings(), tmp_path / "s.json")
    got: list[SettingsChanged] = []

    async def collect(event: SettingsChanged) -> None:
        got.append(event)

    bus.subscribe(SettingsChanged, collect)
    await bus.publish(SettingsRequested({"tts": {"voice": "davefx"}}))
    await bus.publish(SettingsRequested({"appearance": {"nyx_color": "azul"}}))
    await bus.publish(SettingsRequested({"tts": {"voice": "lola"}}))
    assert [e.restart for e in got] == [("tts.voice",), ("tts.voice",), ()]


def test_monitor_settings_are_live(tmp_path: Path) -> None:
    """5d‑1: monitor de Nyx y monitor en partida, desde Ajustes y sin reiniciar."""
    service, settings, _ = _service(tmp_path)
    restart = service.apply(
        {
            "appearance": {"monitor": {"follow": "fixed", "fixed": r"\.\DISPLAY2"}},
            "game": {"alt_monitor": r"\.\DISPLAY3"},
        }
    )
    assert restart == []
    assert settings.appearance.monitor.follow == "fixed"
    assert settings.appearance.monitor.fixed == r"\.\DISPLAY2"
    assert settings.appearance.monitor.transition is True
    assert settings.game.alt_monitor == r"\.\DISPLAY3"
    with pytest.raises(SettingsError, match="follow"):
        service.apply({"appearance": {"monitor": {"follow": "ventana"}}})
