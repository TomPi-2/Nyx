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
    NyxReady,
    SettingsRequested,
    SetupFlowChanged,
    SetupFlowRequested,
    SetupRequested,
    TextEntered,
)
from nyx.settings.live import apply_patch
from nyx.settings.model import Settings
from nyx.setup import flow as flow_module
from nyx.setup.answers import Answer, understand, vocabulary
from nyx.setup.flow import COLOR_SAYS, NOT_UNDERSTOOD, SAY, GuidedSetup
from nyx.stt.normalize import is_echo

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
        # Visto al probarlo (ERRORES.md, 2026-11-14).
        ("size", "Más pequeño.", Answer("size", 80)),  # en masculino la hacía más grande
        ("size", "Hazte más pequeño", Answer("size", 80)),
        ("size", "mucho más pequeño", Answer("size", 60)),
        ("size", "muchísimo más grande", Answer("size", 140)),
        ("color", "Pónteme la cotón.", Answer("pick", "melocoton")),  # whisper se come «melo»
        ("color", "lavenda", Answer("pick", "lavanda")),
        ("color", "quiero el violenta", Answer("pick", "violeta")),
        ("tint", "ciruelo", Answer("pick", "ciruela")),
        ("color", "no me gusta", None),  # nada parecido: no se adivina
        ("color", "vamos a ver", None),
    ],
)
def test_understand(step: str, text: str, expected: Answer | None) -> None:
    mics = ["Micrófono (Realtek Audio)", "Auriculares HyperX Cloud"]
    assert understand(step, text, size=100, mics=mics) == expected


def test_finish_and_speakers() -> None:
    assert understand("data", "¡Terminad!", data_chosen=True) == Answer("done")
    assert understand("data", "acabamos", data_chosen=True) == Answer("done")
    mics = ["Micrófono (Realtek Audio)"]
    speakers = ["Altavoces (Realtek Audio)", "Cascos Arctis 7"]
    # Con «suena», «altavoces»… es la salida; «Realtek» solo, el micrófono.
    said = understand("mic", "que suene por los cascos", mics=mics, speakers=speakers)
    assert said == Answer("speaker", 1)
    said = understand("mic", "por los altavoces realtek", mics=mics, speakers=speakers)
    assert said == Answer("speaker", 0)
    assert understand("mic", "el realtek", mics=mics, speakers=speakers) == Answer("mic", 0)


def test_vocabulary_hints_the_step_words() -> None:
    assert "melocotón" in vocabulary("color") and "Siguiente" in vocabulary("color")
    assert "océano" in vocabulary("tint")
    assert vocabulary("mic").count("Nyx") == 1


@pytest.mark.parametrize(
    ("heard", "spoken", "echo"),
    [
        ("Hola, soy Nix.", "¡Hola! Soy Nyx. Mientras bajo lo que me falta…", True),
        ("Claro, ahora llámame.", "¡Te oigo alto y claro! Ahora llámame: di «Nyx».", True),
        ("Nix.", "Ahora llámame: di «Nyx».", True),
        ("Nix.", "Ahora, mi color.", False),  # ella no lo dice: eres tú
        ("Nyx, siguiente.", "¿Y de tamaño? Dime «más grande» o «más pequeña».", False),
        ("Nyx, más pequeña.", "¿Y de tamaño? Dime «más grande» o «más pequeña».", True),
    ],
)
def test_echo_of_her_own_voice(heard: str, spoken: str, echo: bool) -> None:
    assert is_echo(heard, spoken) is echo


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
    switched: list[str] = []

    async def on_settings(e: SettingsRequested) -> None:
        assert e.patch is not None
        apply_patch(settings, e.patch, path=tmp_path / "settings.json")  # nunca los de verdad

    async def on_any(e: Any) -> None:
        seen.append(e)

    bus.subscribe(SettingsRequested, on_settings)
    bus.subscribe(SetupRequested, on_any)
    bus.subscribe(SetupFlowChanged, on_any)
    bus.subscribe(NyxReady, on_any)
    guided = GuidedSetup(
        bus,
        settings,
        speaker=lambda: speaker,
        mics=lambda: ["Micrófono (Realtek Audio)", "Auriculares HyperX Cloud"],
        speakers=lambda: ["Altavoces (Realtek Audio)", "Cascos Arctis 7"],
        switch_output=switched.append,
    )
    guided.switched = switched  # type: ignore[attr-defined]
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


async def test_speaker_choice_and_ready_wave(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    guided, speaker, settings, seen = setup
    await guided.start()
    await guided.hear("empezar")
    assert guided.snapshot()["speakers"] == ["Altavoces (Realtek Audio)", "Cascos Arctis 7"]
    await guided.hear("que suene por los cascos")
    assert settings.audio.output_device == "Cascos Arctis 7"
    assert guided.switched == ["Cascos Arctis 7"]  # type: ignore[attr-defined]
    assert speaker.said[-1] == "¿Me oyes bien por aquí?"
    # Escucha sin «Nyx» desde el principio (antes, solo tras la prueba del micrófono).
    assert all(listen > 0 for listen in speaker.listen)
    # Termina con todo descargado: «¡Lista!» y la onda (NyxReady) cuando acaban las descargas.
    guided.step = len(flow_module.STEPS) - 1
    await guided.hear("sí")
    await guided.hear("terminar")
    assert not any(isinstance(e, NyxReady) for e in seen)  # aún bajando
    await guided.bus.publish(flow_module.SetupResult("download", True, None))
    assert any(isinstance(e, NyxReady) for e in seen)
    assert "¡Lista!" in speaker.said[-1]


async def test_reused_panel_lets_other_requests_through(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
) -> None:
    """9.11: el panel suelto solo se queda con lo suyo; «abre Spotify» lo cierra sin decir nada
    y lo atiende Nyx como siempre. Si no se cambia nada, «listo» no dice «me encanta»."""
    guided, speaker, _, _ = setup
    await guided.start("size")
    assert guided.wants("más grande") and not guided.wants("abre Spotify")
    said = len(speaker.said)
    assert await guided.hear("abre Spotify") is False
    assert not guided.active and len(speaker.said) == said
    await guided.start("tint")
    await guided.hear("listo")
    assert not guided.active and not any("Me encanta" in t for t in speaker.said)


async def test_reused_panel_closes_when_idle(
    setup: tuple[GuidedSetup, FakeSpeaker, Settings, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guided, _, _, _ = setup
    monkeypatch.setattr(flow_module, "PANEL_IDLE_S", 0.01)
    await guided.start("color")
    assert guided.active
    await asyncio.sleep(0.05)
    assert not guided.active
    # El primer arranque no se cierra solo.
    await guided.start()
    await asyncio.sleep(0.05)
    assert guided.active
    await guided.cancel()


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


class Hook:
    """El primer arranque visto desde la canalización."""

    active = True
    prompt = "Nyx. Coral, lavanda. Siguiente."

    def __init__(self) -> None:
        self.heard: list[str] = []
        self.woke = 0

    def understands(self, text: str) -> bool:
        return understand("color", text) is not None

    def wants(self, text: str) -> bool:
        return self.active

    async def dismiss(self) -> None:
        self.active = False

    async def hear(self, text: str) -> bool:
        self.heard.append(text)
        return True

    async def on_wake(self) -> None:
        self.woke += 1


async def _spin(times: int = 50) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


async def test_pipeline_gives_text_to_the_setup() -> None:
    from tests.test_pipeline import Harness

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


async def test_her_own_name_does_not_wake_her() -> None:
    """«¡Hola! Soy Nyx» por los altavoces: el micrófono la oye, pero es su eco (ERRORES.md,
    2026-11-14: se activaba sola y se cortaba a media frase)."""
    from tests.test_pipeline import SILENCE, WAKE, FakePlayer, Harness, n

    player = FakePlayer(block=True)
    h = Harness(player=player)
    h.p.setup = Hook()
    await h.feed(SILENCE, n(0.5))
    await h.p.announce("¡Hola! Soy Nyx. Mientras bajo lo que me falta, vamos a dejarme a tu gusto.")
    await _spin()
    assert h.p.state.value == "speaking"
    h.stt.clip_text = "Hola, soy Nix."
    await h.feed(WAKE)
    await _spin()
    assert h.p.mode.value != "listening" and h.p.state.value == "speaking"
    # Tú, con otra cosa: sí la corta y te escucha.
    h.stt.clip_text = "Nyx, siguiente."
    await h.feed(SILENCE, n(0.3))
    await h.feed(WAKE)
    await _spin()
    assert h.p.mode.value == "listening"
    await h.p.close()


async def test_setup_keeps_listening_without_the_name() -> None:
    from tests.test_pipeline import SILENCE, SPEECH, Harness, n

    h = Harness()
    hook = Hook()
    h.p.setup = hook
    prompts: list[str] = []
    transcribe = h.stt.transcribe

    async def spy(pcm: np.ndarray, prompt: str = "") -> str:
        prompts.append(prompt)
        return await transcribe(pcm, prompt)

    h.stt.transcribe = spy  # type: ignore[method-assign]
    await h.p.start_listening(followup=True, timeout_s=0.5)
    await h.feed(SILENCE, n(1.5))  # nadie habla: sigue escuchando
    assert h.p.mode.value == "listening"
    h.stt.text = h.stt.clip_text = "Siguiente."
    await h.feed(SPEECH, n(0.6))
    await h.feed(SILENCE, n(0.8))
    await h.p.wait_idle()
    assert hook.heard == ["Siguiente."]
    assert prompts and all(p == Hook.prompt for p in prompts)  # con los nombres del paso
    # Sin primer arranque, la ventana de seguimiento se cierra como siempre.
    hook.active = False
    await h.p.start_listening(followup=True, timeout_s=0.5)
    await h.feed(SILENCE, n(1.5))
    assert h.p.mode.value == "idle"
    await h.p.close()


async def test_announce_stops_listening_to_herself() -> None:
    """Un botón mientras se te escuchaba: al hablar deja de escuchar o se oiría a sí misma
    («Azul. Clásico y seguro.» elegiría el azul)."""
    from tests.test_pipeline import FakePlayer, Harness

    h = Harness(player=FakePlayer(block=True))
    h.p.setup = Hook()
    await h.p.start_listening(followup=True, timeout_s=5.0)
    assert h.p.mode.value == "listening"
    await h.p.announce("Azul. Clásico y seguro.")
    await _spin()
    assert h.p.mode.value != "listening"
    await h.p.close()


async def test_reused_panel_hands_over_what_it_does_not_understand() -> None:
    """Con el panel suelto abierto, «abre Spotify» va al router como siempre."""
    from tests.test_pipeline import Harness

    class Panel(Hook):
        def wants(self, text: str) -> bool:
            return self.active and self.understands(text)

    h = Harness()
    panel = Panel()
    h.p.setup = panel
    await h.bus.publish(TextEntered("coral"))
    await h.p.wait_idle()
    assert panel.heard == ["coral"] and panel.active
    await h.bus.publish(TextEntered("¿qué hora es?"))
    await h.p.wait_idle()
    assert panel.heard == ["coral"] and not panel.active  # cerrado y atendido por Nyx
    await h.p.close()
