"""Primer arranque guiado por Nyx (9.10): respuestas habladas, pasos, fundido y la canalización."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from nyx.audio.playback import Player
from nyx.bus import EventBus
from nyx.events import (
    MicLevelChanged,
    SettingsRequested,
    SetupFlowChanged,
    SetupFlowRequested,
    SetupRequested,
    TextEntered,
)
from nyx.settings.live import apply_patch
from nyx.settings.model import Settings
from nyx.setup import flow as flow_module
from nyx.setup.answers import Answer, understand
from nyx.setup.flow import COLOR_SAYS, NOT_UNDERSTOOD, SAY, GuidedSetup

# --- Lo que se dice -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "text", "expected"),
    [
        ("color", "ponte azul cielo", Answer("pick", "azul_cielo")),
        ("color", "Vale, el azul", Answer("pick", "azul")),  # el color antes que «vale»
        ("color", "¡Coral!", Answer("pick", "coral")),
        ("color", "siguiente", Answer("next")),
        ("color", "vuelve atrás", Answer("back")),
        ("tint", "océano", Answer("pick", "oceano")),
        ("tint", "azul noche", Answer("pick", "azul_noche")),
        ("size", "más grande", Answer("size", 120)),
        ("size", "un poco más pequeña", Answer("size", 80)),
        ("size", "mucho más grande", Answer("size", 140)),
        ("size", "ponte a 135", Answer("size", 140)),
        ("size", "el de siempre", Answer("size", 100)),
        ("size", "1000", Answer("size", 180)),
        ("data", "no, gracias", Answer("data", False)),
        ("data", "sí, claro", Answer("data", True)),
        ("welcome", "luego", Answer("skip")),
        ("welcome", "empezamos", Answer("next")),
        ("mic", "Nyx", Answer("wake")),
        ("mic", "los auriculares", Answer("mic", 1)),
        ("mic", "hola hola probando", Answer("heard")),
        ("color", "qué hora es", None),
        ("color", "", None),
    ],
)
def test_understand(step: str, text: str, expected: Answer | None) -> None:
    mics = ["Micrófono (Realtek Audio)", "Auriculares HyperX Cloud"]
    assert understand(step, text, size=100, mics=mics) == expected


def test_data_done_only_after_choosing() -> None:
    assert understand("data", "terminar", data_chosen=False) is None
    assert understand("data", "terminar", data_chosen=True) == Answer("done")
    assert understand("data", "vale", data_chosen=True) == Answer("done")
    assert understand("data", "vale", data_chosen=False) == Answer("data", True)


# --- El fundido -----------------------------------------------------------------------------------


def test_fade_out_only_touches_what_was_playing() -> None:
    player = Player(24_000)
    player._chunks.append(np.ones(24_000, dtype=np.float32))  # 1 s de voz
    player._offset = 1000
    player.fade_out(150)
    out = player.fill(4000)
    assert out[0] == pytest.approx(1.0, abs=1e-3)
    assert 0 < out[1800] < 1  # bajando
    assert np.all(out[3600:] == 0)  # 150 ms y fuera; el resto de la frase se tira
    # Lo que se encola después (la frase siguiente) suena entero.
    player._chunks.append(np.full(100, 0.5, dtype=np.float32))
    assert np.all(player.fill(100) == 0.5)


# --- Los pasos ------------------------------------------------------------------------------------


class FakeSpeaker:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.hushed = 0
        self.listen: list[float] = []

    async def announce(self, text: str, *, listen_after: float = 0.0) -> None:
        self.said.append(text)
        self.listen.append(listen_after)

    def hush(self) -> None:
        self.hushed += 1


@pytest.fixture
async def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]]:
    monkeypatch.setattr(flow_module.everything, "status", lambda: {"installed": False})
    bus = EventBus()
    settings = Settings()
    speaker = FakeSpeaker()
    seen: list[Any] = []

    async def on_settings(e: SettingsRequested) -> None:
        assert e.patch is not None
        apply_patch(settings, e.patch, path=tmp_path / "settings.json")  # nunca los de verdad

    async def on_any(e: Any) -> None:
        seen.append(e)

    bus.subscribe(SettingsRequested, on_settings)
    bus.subscribe(SetupRequested, on_any)
    bus.subscribe(SetupFlowChanged, on_any)
    guided = GuidedSetup(
        bus,
        settings,
        speaker=lambda: speaker,
        mics=lambda: ["Micrófono (Realtek Audio)", "Auriculares HyperX Cloud"],
    )
    return guided, speaker, settings, seen


async def test_whole_first_run_by_voice(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    guided, speaker, settings, seen = setup
    await guided.start()
    assert guided.key == "welcome" and speaker.said == list(SAY["welcome"])
    assert any(isinstance(e, SetupRequested) and e.action == "download" for e in seen)

    await guided.hear("empezamos")
    assert guided.key == "mic"  # el micrófono, lo primero
    assert speaker.hushed >= 1  # se calla al pasar de paso
    assert any(isinstance(e, SetupRequested) and e.action == "mic_test_start" for e in seen)
    # Se le oye: lo dice. Luego «Nyx»: desde ahí escucha sin la palabra.
    await guided.bus.publish(MicLevelChanged(0.6))
    assert guided.heard and "Te oigo" in speaker.said[-1]
    await guided.on_wake()
    assert guided.woke and speaker.listen[-1] > 0

    await guided.hear("siguiente")
    assert guided.key == "color"
    assert any(isinstance(e, SetupRequested) and e.action == "mic_test_stop" for e in seen)
    await guided.hear("ponte azul cielo")
    assert settings.appearance.nyx_color == "azul_cielo"
    assert speaker.said[-1] == COLOR_SAYS["azul_cielo"]
    await guided.hear("¿qué hora es?")
    assert speaker.said[-1] in NOT_UNDERSTOOD
    assert guided.key == "color"

    await guided.hear("vale")
    await guided.hear("más grande")
    assert settings.appearance.indicator_size == 120
    await guided.hear("siguiente")
    await guided.hear("océano")
    assert settings.appearance.panel_tint == "oceano"

    await guided.hear("siguiente")
    assert guided.key == "scan"
    for _ in range(20):  # el escaneo va aparte
        await asyncio.sleep(0)
    assert guided.scan is not None and guided.scan["running"] is False

    await guided.hear("siguiente")
    assert guided.key == "data"
    await guided.hear("terminar")  # aún sin elegir: no termina
    assert guided.active
    await guided.hear("no, gracias")
    assert settings.privacy.usage_data is False and guided.usage is False
    await guided.hear("terminar")
    assert not guided.active and guided.finished
    assert settings.onboarding.done is True
    # Mientras baja lo que falta, lo dice; si no, «¡Lista!».
    assert "Termino de bajar" in speaker.said[-1] or "¡Lista!" in speaker.said[-1]
    states = [e.state for e in seen if isinstance(e, SetupFlowChanged)]
    assert states[-1]["active"] is False


async def test_panel_buttons_and_live_size(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    guided, speaker, settings, _ = setup
    await guided.start()
    await guided.bus.publish(SetupFlowRequested("next"))
    await guided.bus.publish(SetupFlowRequested("next"))
    assert guided.key == "color"
    await guided.bus.publish(SetupFlowRequested("pick", "lima"))
    assert settings.appearance.nyx_color == "lima"
    await guided.bus.publish(SetupFlowRequested("next"))
    said = len(speaker.said)
    await guided.bus.publish(SetupFlowRequested("size_live", 150))  # arrastrando: sin hablar
    assert settings.appearance.indicator_size == 150 and len(speaker.said) == said
    await guided.bus.publish(SetupFlowRequested("size", 170))
    assert settings.appearance.indicator_size == 170 and "grande" in speaker.said[-1]
    await guided.bus.publish(SetupFlowRequested("back"))
    assert guided.key == "color"
    await guided.bus.publish(SetupFlowRequested("close"))
    assert not guided.active and settings.onboarding.done is False  # vuelve a salir otro día


async def test_skip_from_welcome(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    guided, speaker, settings, _ = setup
    await guided.start()
    await guided.hear("luego")
    assert not guided.active and settings.onboarding.done is True
    assert any("me quedo como estoy" in s for s in speaker.said)


async def test_reused_color_panel(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    guided, speaker, settings, seen = setup
    await guided.start("color")  # «Nyx, quiero cambiarte el color» (9.11)
    assert guided.key == "color" and speaker.said == list(SAY["color_again"])
    assert not any(isinstance(e, SetupRequested) and e.action == "download" for e in seen)
    await guided.hear("turquesa")
    assert settings.appearance.nyx_color == "turquesa"
    await guided.hear("listo")
    assert not guided.active and settings.onboarding.done is False


# --- La canalización ------------------------------------------------------------------------------


async def test_pipeline_gives_text_to_the_setup() -> None:
    from tests.test_pipeline import Harness

    class Hook:
        active = True

        def __init__(self) -> None:
            self.heard: list[str] = []

        async def hear(self, text: str) -> bool:
            self.heard.append(text)
            return True

        async def on_wake(self) -> None:
            pass

    h = Harness()
    hook = Hook()
    h.p.setup = hook
    await h.bus.publish(TextEntered("ponte azul"))
    await h.p.wait_idle()
    assert hook.heard == ["ponte azul"]
    assert h.llm.requests == []  # ni router ni cerebro
    await h.p.close()


async def test_pipeline_announce_and_hush() -> None:
    from tests.test_pipeline import FakePlayer, Harness

    class FadingPlayer(FakePlayer):
        def __init__(self) -> None:
            super().__init__(block=True)
            self.faded = 0

        def fade_out(self, ms: float = 150.0) -> None:
            self.faded += 1
            self._released.set()

    player = FadingPlayer()
    h = Harness(player=player)
    await h.p.announce("Hola, soy Nyx. Vamos a dejarme a tu gusto.")
    for _ in range(10):
        await asyncio.sleep(0)
    assert h.tts.said and h.p.state.value == "speaking"
    h.p.hush()  # pasar de paso mientras habla
    for _ in range(10):
        await asyncio.sleep(0)
    assert player.faded == 1 and player.cleared == 0  # fundido, no corte seco
    assert h.p.state.value == "idle"
    await h.p.close()
