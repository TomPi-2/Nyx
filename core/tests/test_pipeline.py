"""Bucle de voz con piezas falsas: micrófono, activación, VAD, whisper, LLM, voz y altavoz."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import numpy as np
import pytest

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES
from nyx.brain.base import ChatMessage, LLMError, LLMErrorKind, LLMToolCall
from nyx.brain.service import Brain
from nyx.bus import EventBus
from nyx.events import (
    BubbleHidden,
    BubbleShown,
    NyxState,
    StateChanged,
    TalkKey,
    TextEntered,
)
from nyx.pipeline import Mode, Pipeline
from nyx.settings.model import ListenSettings

WAKE, SPEECH, SILENCE = 7, 5000, 0


def frame(value: int) -> np.ndarray:
    return np.full(FRAME_SAMPLES, value, dtype=np.int16)


def n(seconds: float) -> int:
    return round(seconds / FRAME_S)


class FakeCapture:
    def __init__(self) -> None:
        self.ring: list[np.ndarray] = []

    def prebuffer(self, seconds: float) -> list[np.ndarray]:
        return self.ring[-n(seconds) :]

    def stop(self) -> None:
        pass


class FakeWake:
    def process(self, f: np.ndarray) -> bool:
        return int(f[0]) == WAKE

    def reset(self) -> None:
        pass


class FakeVAD:
    def __call__(self, f: np.ndarray) -> float:
        return 0.9 if int(f[0]) == SPEECH else 0.0

    def reset(self) -> None:
        pass


class FakeSTT:
    """El fragmento de verificación y la frase pueden dar textos distintos."""

    def __init__(
        self,
        text: str = "Nix, ¿cómo se dice hola en alemán?",
        clip_text: str | None = None,
    ) -> None:
        self.text = text
        self.clip_text = clip_text if clip_text is not None else text
        self.calls: list[int] = []
        self.clips: list[bool] = []
        self.script: list[str] = []
        # Si se activa, la verificación del fragmento espera (whisper ocupado o lento).
        self.clip_gate: asyncio.Event | None = None

    @property
    def full_calls(self) -> list[int]:
        return [size for size, clip in zip(self.calls, self.clips, strict=True) if not clip]

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def transcribe(self, pcm: np.ndarray, prompt: str = "") -> str:
        # El fragmento de verificación se toma al oír «Nyx», antes de que haya voz.
        clip = int(pcm.max(initial=0)) < SPEECH
        self.calls.append(pcm.size)
        self.clips.append(clip)
        if clip:
            if self.clip_gate is not None:
                await self.clip_gate.wait()
            return self.clip_text
        # `script`: textos sucesivos para cada transcripción con voz (la última se repite).
        if self.script:
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]
        return self.text


REPLY = "[Hallo | hola · alemán]\nEn alemán se dice Hallo."


class FakeLLM:
    def __init__(self, reply: str | None = None, error: LLMError | None = None) -> None:
        self.raw = reply or REPLY
        self.plans: list[list[LLMToolCall]] = []  # si hay, se devuelven como llamadas
        self.replies: list[str] = []  # respuestas sucesivas (si no, siempre `raw`)
        self.addressed = True  # veredicto del clasificador de la ventana de seguimiento
        self.classified: list[str] = []
        self.error = error
        self.requests: list[list[ChatMessage]] = []

    @property
    def asked(self) -> list[str]:
        """Lo que se preguntó al LLM, sin la línea de contexto («(Ahora es…)»)."""
        return [r[-1].content.split(chr(10), 1)[-1] for r in self.requests]

    async def warmup(
        self, prefix: Sequence[ChatMessage] = (), *, tools: Sequence[dict[str, Any]] = ()
    ) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        if schema is not None and "para_nyx" in schema.get("properties", {}):
            # Clasificador de la ventana de seguimiento (Brain.addressed).
            self.classified.append(messages[-1].content)
            yield json.dumps({"para_nyx": self.addressed})
            return
        self.requests.append(list(messages))
        if self.error:
            raise self.error
        raw = self.replies.pop(0) if self.replies else self.raw
        for i in range(0, len(raw), 4):
            await asyncio.sleep(0)
            yield raw[i : i + 4]

    async def chat(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        self.requests.append(list(messages))
        self.tools = list(tools)
        if self.error:
            raise self.error
        if self.plans:
            yield self.plans.pop(0)
            return
        raw = self.replies.pop(0) if self.replies else self.raw
        for i in range(0, len(raw), 4):
            await asyncio.sleep(0)
            yield raw[i : i + 4]


class FakeTTS:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.said: list[str] = []

    async def load(self) -> None:
        pass

    async def synthesize(self, text: str) -> np.ndarray:
        self.said.append(text)
        return np.zeros(2400, dtype=np.float32)

    async def stream(self, text: str) -> AsyncIterator[np.ndarray]:
        yield await self.synthesize(text)


class FakePlayer:
    def __init__(self, block: bool = False) -> None:
        self.level = 0.5
        self.enqueued = 0
        self.cleared = 0
        self._block = block
        self._released = asyncio.Event()

    def prepare(self) -> None:
        pass

    def enqueue(self, samples: np.ndarray) -> None:
        self.enqueued += 1

    def clear(self) -> None:
        self.cleared += 1
        self._released.set()

    async def drain(self) -> None:
        if self._block:  # «habla» hasta que alguien la corte
            self._released.clear()
            await self._released.wait()

    def close(self) -> None:
        pass


class Harness:
    def __init__(
        self,
        *,
        llm: FakeLLM | None = None,
        player: FakePlayer | None = None,
        stt: FakeSTT | None = None,
        speak_typed: bool = False,
    ) -> None:
        self.bus = EventBus()
        self.states: list[NyxState] = []
        self.bubbles: list[tuple[str, str | None]] = []
        self.hidden = 0
        self.capture = FakeCapture()
        self.stt = stt or FakeSTT()
        self.llm = llm or FakeLLM()
        self.tts = FakeTTS()
        self.player = player or FakePlayer()
        self.now = 0.0

        async def on_state(e: StateChanged) -> None:
            self.states.append(e.state)

        async def on_bubble(e: BubbleShown) -> None:
            self.bubbles.append((e.display, e.secondary))

        async def on_hidden(_: BubbleHidden) -> None:
            self.hidden += 1

        self.bus.subscribe(StateChanged, on_state)
        self.bus.subscribe(BubbleShown, on_bubble)
        self.bus.subscribe(BubbleHidden, on_hidden)
        self.p = Pipeline(
            self.bus,
            Brain(self.llm),
            listen=ListenSettings(followup_s=1.0, start_timeout_s=1.0),
            wake_prebuffer_s=0.5,
            speak_typed=speak_typed,
            capture=self.capture,  # type: ignore[arg-type]
            wake=FakeWake(),
            vad=FakeVAD(),
            stt=self.stt,
            tts=self.tts,
            player=self.player,  # type: ignore[arg-type]
            clock=lambda: self.now,
        )

        async def no_context() -> str:
            return ""  # sin consultar la ventana activa real

        self.p._context = no_context  # type: ignore[method-assign]

    async def feed(self, value: int, count: int = 1) -> None:
        for _ in range(count):
            f = frame(value)
            self.capture.ring.append(f)
            self.now += FRAME_S
            await self.p.process_frame(f)
            await asyncio.sleep(0)  # deja correr la verificación en paralelo

    async def say(self, *, speech_s: float = 1.0) -> None:
        """«Nix» + frase + 700 ms de silencio (con 0,5 s de audio previo)."""
        await self.feed(SILENCE, n(0.5))
        await self.feed(WAKE)
        await self.feed(SPEECH, n(speech_s))
        await self.feed(SILENCE, n(0.7))


async def test_text_request_answers_in_bubble_without_voice() -> None:
    h = Harness()
    await h.bus.publish(TextEntered("¿Cómo se dice hola en alemán?"))
    await h.p.wait_idle()
    assert h.states == [NyxState.THINKING, NyxState.IDLE]
    # Sin voz, la burbuja lleva la respuesta entera debajo del dato destacado.
    assert h.bubbles == [("Hallo", "En alemán se dice Hallo.")]
    assert h.tts.said == []
    assert h.player.enqueued == 0
    assert h.p.mode is Mode.IDLE
    # La memoria corta guarda el turno para la siguiente petición.
    await h.bus.publish(TextEntered("¿Y en francés?"))
    await h.p.wait_idle()
    assert [m.role for m in h.llm.requests[1]][1:3] == ["user", "assistant"]
    await h.p.close()


async def test_typed_request_can_also_be_spoken() -> None:
    h = Harness(speak_typed=True)  # ajuste responses.speak_typed
    await h.bus.publish(TextEntered("¿Cómo se dice hola en alemán?"))
    await h.p.wait_idle()
    assert h.states == [NyxState.THINKING, NyxState.SPEAKING, NyxState.IDLE]
    assert h.tts.said == ["En alemán se dice Hallo."]
    assert h.bubbles == [("Hallo", "hola · alemán")]
    assert h.p.mode is Mode.IDLE  # sin ventana de seguimiento: no se habló al micrófono
    await h.p.close()


async def test_voice_flow_with_followup_window() -> None:
    h = Harness()
    await h.say()
    await h.p.wait_idle()
    assert len(h.stt.full_calls) == 1
    # Prebúfer de 0,5 s + 1 s de voz + 0,7 s de silencio, aprox.
    assert h.stt.full_calls[0] >= (n(1.0) + n(0.7)) * FRAME_SAMPLES
    assert h.tts.said == ["En alemán se dice Hallo."]
    assert h.bubbles == [("Hallo", "hola · alemán")]
    assert h.llm.asked[0] == "¿Cómo se dice hola en alemán?"  # sin «Nix,»
    # Ventana de seguimiento: escucha sin repetir la palabra y, sin voz, vuelve a reposo.
    assert h.p.mode is Mode.LISTENING
    await h.feed(SILENCE, n(1.1))
    assert h.p.mode is Mode.IDLE
    assert h.states == [
        NyxState.LISTENING,
        NyxState.THINKING,
        NyxState.SPEAKING,
        NyxState.LISTENING,
        NyxState.IDLE,
    ]
    assert len(h.stt.full_calls) == 1
    await h.p.close()


async def test_false_activation_is_discarded_while_listening() -> None:
    # «No existe» engaña a Vosk, pero whisper no oye «Nyx»: se deja de escuchar enseguida.
    h = Harness(stt=FakeSTT(text="No existe.", clip_text="No existe."))
    await h.feed(SILENCE, n(0.5))
    await h.feed(WAKE)
    await h.feed(SPEECH, n(0.2))
    assert h.p.mode is Mode.IDLE
    # Fase 4c: el indicador espera a whisper, así que una activación falsa ni se ve.
    assert h.states == []
    assert h.llm.requests == []
    await h.feed(SPEECH, n(1.0))  # lo que siga diciendo ya no se escucha
    assert h.stt.full_calls == []
    await h.p.close()


async def test_wake_word_heard_only_in_full_sentence_is_accepted() -> None:
    # El fragmento corto no la recoge, pero la frase completa empieza por «Nyx»: vale.
    stt = FakeSTT(text="Nyx, ¿qué hora es?", clip_text="¿qué hora")
    stt.clip_gate = asyncio.Event()  # la verificación llega cuando la frase ya terminó
    h = Harness(stt=stt)
    await h.say()
    assert h.p.mode is Mode.BUSY
    stt.clip_gate.set()
    await h.p.wait_idle()
    assert h.llm.asked[0] == "¿Qué hora es?"
    await h.p.close()


async def test_late_failed_verification_without_wake_in_sentence_is_discarded() -> None:
    stt = FakeSTT(text="No existe.", clip_text="No existe.")
    stt.clip_gate = asyncio.Event()
    h = Harness(stt=stt)
    await h.say()
    stt.clip_gate.set()
    await h.p.wait_idle()
    assert h.llm.requests == []
    assert h.p.mode is Mode.IDLE
    await h.p.close()


async def test_wake_without_speech_goes_idle_without_transcribing() -> None:
    h = Harness()
    await h.feed(WAKE)
    await h.feed(SILENCE, n(1.1))
    assert h.p.mode is Mode.IDLE
    assert h.stt.full_calls == []
    assert h.states == [NyxState.LISTENING, NyxState.IDLE]


async def test_wake_word_interrupts_speech() -> None:
    h = Harness(player=FakePlayer(block=True))
    await h.say()
    for _ in range(50):
        await asyncio.sleep(0)
    assert h.p.state is NyxState.SPEAKING
    await h.feed(WAKE)
    for _ in range(50):  # primero se confirma con whisper; luego se interrumpe
        await asyncio.sleep(0)
    assert h.p.mode is Mode.LISTENING
    assert h.p.state is NyxState.LISTENING
    assert h.player.cleared >= 1
    assert h.hidden >= 1  # la burbuja de la respuesta cortada se oculta
    await h.p.close()


async def test_false_wake_while_speaking_does_not_interrupt() -> None:
    # Fase 5b: si whisper no oye «Nyx», la respuesta sigue (antes se cortaba al momento).
    h = Harness(player=FakePlayer(block=True))
    await h.say()
    for _ in range(50):
        await asyncio.sleep(0)
    assert h.p.state is NyxState.SPEAKING
    await h.feed(SILENCE, n(2.5))  # el fragmento de verificación no lleva la frase anterior
    h.stt.clip_text = "Gracias."  # el detector salta, pero whisper no oye «Nyx»
    cleared = h.player.cleared
    await h.feed(WAKE)
    for _ in range(50):
        await asyncio.sleep(0)
    assert h.p.state is NyxState.SPEAKING and h.player.cleared == cleared
    await h.p.close()


async def test_talk_key_hold_ignores_pauses_until_release() -> None:
    h = Harness()
    await h.bus.publish(TalkKey(pressed=True))
    assert h.p.mode is Mode.LISTENING
    await h.feed(SPEECH, n(0.5))
    await h.feed(SILENCE, n(1.5))  # pausa larga mientras se mantiene: no corta
    assert h.p.mode is Mode.LISTENING
    await h.feed(SPEECH, n(0.5))
    await h.bus.publish(TalkKey(pressed=True))  # repetición de tecla: se ignora
    await h.bus.publish(TalkKey(pressed=False))
    await h.p.wait_idle()
    assert len(h.stt.calls) == 1  # con el atajo no hace falta verificar «Nyx»
    await h.p.close()


async def test_talk_key_tap_lets_vad_decide() -> None:
    h = Harness(stt=FakeSTT(text="¿Qué hora es?"))
    await h.bus.publish(TalkKey(pressed=True))
    await h.bus.publish(TalkKey(pressed=False))  # toque corto
    assert h.p.mode is Mode.LISTENING
    await h.feed(SPEECH, n(0.5))
    await h.feed(SILENCE, n(0.7))
    await h.p.wait_idle()
    assert len(h.stt.calls) == 1
    assert h.llm.requests  # sin «Nyx» en la frase, pero vale: la activó el atajo
    await h.p.close()


@pytest.mark.parametrize(
    ("kind", "display"),
    [
        (LLMErrorKind.UNAVAILABLE, "Sin conexión con Ollama"),
        (LLMErrorKind.TIMEOUT, "Me he atascado"),
    ],
)
async def test_llm_errors_are_explained(kind: LLMErrorKind, display: str) -> None:
    h = Harness(llm=FakeLLM(error=LLMError(kind)))
    await h.say()
    await h.p.wait_idle()
    assert NyxState.ERROR in h.states
    assert h.states[-1] is NyxState.IDLE
    assert h.bubbles[-1][0] == display
    assert h.tts.said  # por voz, el error también se dice en voz alta
    await h.p.close()


async def test_llm_error_on_text_request_is_silent() -> None:
    h = Harness(llm=FakeLLM(error=LLMError(LLMErrorKind.UNAVAILABLE)))
    await h.bus.publish(TextEntered("hola"))
    await h.p.wait_idle()
    assert h.bubbles[-1][0] == "Sin conexión con Ollama"
    assert h.tts.said == []
    await h.p.close()


async def test_new_text_cancels_running_request() -> None:
    h = Harness(player=FakePlayer(block=True))
    await h.say()
    for _ in range(50):
        await asyncio.sleep(0)
    assert h.p.state is NyxState.SPEAKING
    await h.bus.publish(TextEntered("segunda"))
    await h.p.wait_idle()
    assert h.llm.asked[-1] == "segunda"
    assert h.player.cleared >= 1
    assert h.p.mode is Mode.IDLE
    await h.p.close()


async def test_indicator_waits_for_whisper_confirmation() -> None:
    # Fase 4c: se graba desde el salto del detector, pero «escuchando» se ve al confirmar.
    stt = FakeSTT(text="Nyx, ¿qué hora es?", clip_text="Nyx.")
    stt.clip_gate = asyncio.Event()
    h = Harness(stt=stt)
    await h.feed(SILENCE, n(0.5))
    await h.feed(WAKE)
    assert h.p.mode is Mode.LISTENING and h.states == []  # grabando, aún sin indicador
    stt.clip_gate.set()
    await asyncio.sleep(0.01)
    assert h.states == [NyxState.LISTENING]
    await h.p.close()


@pytest.mark.parametrize(
    ("text", "for_nyx"),
    [
        ("Reanúdalo.", True),
        ("O sea, anúdalo.", True),  # el caso real (whisper oyó mal «reanúdalo»)
        ("Súbele un poco.", True),
        ("Pon la siguiente.", True),
        ("Vale, y luego Nix, ¿qué hora es?", True),  # dice «Nyx» en medio
        ("Sí, mañana quedamos a las cinco.", False),
        ("Qué bueno el vídeo.", False),
    ],
)
def test_clearly_for_nyx_in_followup(text: str, for_nyx: bool) -> None:
    h = Harness()
    assert h.p._clearly_for_nyx(text) is for_nyx


@pytest.mark.parametrize(
    "raw",
    [
        # ERRORES.md, 2026-11-11: lo que Nyx llegó a leer en voz alta.
        '[acciones]\nappaction({"app": "Rocket League", "action": "jump"}); otra cosa(',
        '[Vale | ]\nClaro. app_action({"app": "Rocket League", "action": "jump"})',
    ],
)
async def test_code_in_reply_is_never_spoken(raw: str) -> None:
    h = Harness(llm=FakeLLM(raw), speak_typed=True)
    await h.bus.publish(TextEntered("salta"))
    await h.p.wait_idle()
    assert all("(" not in s and "{" not in s for s in h.tts.said)
    assert h.tts.said[-1] == "No he podido hacerlo."
    assert h.bubbles[-1] == ("No he podido hacerlo", "¿me lo pides de otra forma?")
    await h.p.close()
