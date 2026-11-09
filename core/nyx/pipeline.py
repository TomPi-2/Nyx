"""Bucle de voz (SPEC sección 3): activación → escucha → transcripción → LLM → voz y burbuja.

Una sola petición a la vez: una nueva (voz, texto o atajo) cancela la que esté en curso.
Cada petición lleva su ID en el registro y una línea con su latencia
(fin de la frase → primera palabra hablada, objetivo < 1,5 s).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

from nyx.audio.capture import AudioCapture, Frame, rms_level
from nyx.audio.playback import Player
from nyx.audio.vad import Endpointer, EndReason, VoiceDetector
from nyx.brain.base import LLMError, LLMErrorKind
from nyx.brain.reply import BubbleReady, Reply, SpokenDelta, SpokenEnd
from nyx.brain.service import Brain, ReplyDone
from nyx.bus import EventBus
from nyx.events import (
    AudioLevel,
    BubbleHidden,
    BubbleShown,
    NyxState,
    StateChanged,
    TalkKey,
    TextEntered,
)
from nyx.log import new_request_id
from nyx.settings.model import ListenSettings
from nyx.stt.base import STTEngine, STTError
from nyx.stt.normalize import has_wake_word, normalize
from nyx.tts.base import TTSEngine, TTSError
from nyx.tts.sentences import SentenceSplitter
from nyx.wake.base import WakeWordEngine

log = logging.getLogger(__name__)

# Vocabulario para Whisper: mejora la transcripción de «Nyx» (fase 3: apps y carpetas de la caché).
STT_PROMPT = "Nyx."
THINKING_AFTER_S = 0.3  # «pensando» solo si la transcripción tarda (SPEC sección 3)
HOLD_S = 0.4  # mantener el atajo más que esto = hablar mientras se mantiene
TALK_PREBUFFER_S = 0.3
VERIFY_CLIP_S = 2.0  # audio que whisper revisa para confirmar «Nyx»
LEVEL_HZ = 30
ERROR_HOLD_S = 2.5


class Mode(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    BUSY = "busy"


@dataclass
class _Listening:
    endpointer: Endpointer
    frames: list[Frame]
    followup: bool = False
    manual: bool = False
    key_held: bool = False
    pressed_at: float = 0.0
    # Segunda verificación de «Nyx» con whisper (solo si la escucha empezó por la palabra).
    verify: asyncio.Task[bool] | None = None


@dataclass
class _Marks:
    """Tiempos de una petición para la línea de latencia del registro."""

    end: float
    stt: float | None = None
    first_token: float | None = None
    first_sentence: float | None = None
    first_audio: float | None = None


ERRORS: dict[LLMErrorKind, tuple[str, str, str]] = {
    LLMErrorKind.UNAVAILABLE: (
        "Sin conexión con Ollama",
        "no he podido abrirlo",
        "No puedo conectar con el modelo de lenguaje.",
    ),
    LLMErrorKind.MODEL_MISSING: (
        "Falta el modelo",
        "descárgalo con ollama pull",
        "Falta el modelo de lenguaje.",
    ),
    LLMErrorKind.TIMEOUT: ("Me he atascado", "¿lo repites?", "Me he atascado, ¿lo repites?"),
    LLMErrorKind.OTHER: ("Algo ha fallado", "inténtalo otra vez", "Algo ha fallado."),
}


def text_bubble(reply: Reply) -> BubbleReady:
    """Burbuja de una respuesta sin voz: el dato destacado y, debajo, la respuesta entera."""
    spoken = reply.spoken.strip()
    if not reply.display:
        return BubbleReady(spoken, "")
    if not spoken or spoken.rstrip(".!").casefold() == reply.display.rstrip(".!").casefold():
        return BubbleReady(reply.display, reply.secondary)
    return BubbleReady(reply.display, spoken)


def bubble_duration(display: str, secondary: str) -> float:
    """~300 ms por palabra, entre 4 y 15 s (SPEC sección 11)."""
    words = len(f"{display} {secondary}".split())
    return min(15.0, max(4.0, words * 0.3))


class _Speech:
    """Sintetiza frases en orden mientras suenan las anteriores."""

    def __init__(
        self,
        tts: TTSEngine,
        player: Player,
        on_start: Callable[[], Awaitable[None]],
    ) -> None:
        self._tts = tts
        self._player = player
        self._on_start = on_start
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.started = False
        self._task = asyncio.create_task(self._worker(), name="tts")

    def say(self, text: str) -> None:
        if not self.started and self._queue.empty():
            self._player.prepare()
        self._queue.put_nowait(text)

    async def _worker(self) -> None:
        while (text := await self._queue.get()) is not None:
            try:
                audio = await self._tts.synthesize(text)
            except TTSError:
                log.exception("Fallo de la voz con %r", text)
                continue
            if not self.started:
                self.started = True
                await self._on_start()
            self._player.enqueue(audio)

    async def finish(self) -> None:
        self._queue.put_nowait(None)
        await self._task
        if self.started:
            await self._player.drain()

    async def abort(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._player.clear()


class Pipeline:
    def __init__(
        self,
        bus: EventBus,
        brain: Brain,
        *,
        listen: ListenSettings | None = None,
        wake_prebuffer_s: float = 1.5,
        speak_typed: bool = False,
        capture: AudioCapture | None = None,
        wake: WakeWordEngine | None = None,
        vad: VoiceDetector | None = None,
        stt: STTEngine | None = None,
        tts: TTSEngine | None = None,
        player: Player | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.bus = bus
        self.brain = brain
        self.listen = listen or ListenSettings()
        self.wake_prebuffer_s = wake_prebuffer_s
        self.speak_typed = speak_typed
        self.capture = capture
        self.wake = wake
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.player = player
        self._clock = clock
        self.mode = Mode.IDLE
        self.state = NyxState.IDLE
        self._listening: _Listening | None = None
        self._request: asyncio.Task[None] | None = None
        self._bubble_timer: asyncio.Task[None] | None = None
        self._unsubscribe = [
            bus.subscribe(TextEntered, self._on_text),
            bus.subscribe(TalkKey, self._on_talk),
        ]

    @property
    def voice_enabled(self) -> bool:
        return self.vad is not None and self.stt is not None

    # --- ciclo de vida ---

    async def run(self) -> None:
        if self.capture is None:
            await asyncio.Event().wait()  # solo entrada por texto
            return
        async for frame in self.capture.frames():
            await self.process_frame(frame)

    async def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        await self._cancel_request()
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
        if self.capture is not None:
            self.capture.stop()
        if self.player is not None:
            self.player.close()

    async def wait_idle(self) -> None:
        """Espera a que termine la petición en curso (útil en pruebas y en --ask)."""
        while self._request is not None and not self._request.done():
            await asyncio.gather(self._request, return_exceptions=True)

    # --- audio ---

    async def process_frame(self, frame: Frame) -> None:
        if self.mode is Mode.LISTENING:
            await self._listen_frame(frame)
        elif self.wake is not None and self.voice_enabled and self.wake.process(frame):
            log.info("Activación")
            clip = self.capture.prebuffer(VERIFY_CLIP_S) if self.capture is not None else []
            await self.start_listening(self.wake_prebuffer_s)
            if self._listening is not None and clip:
                self._listening.verify = asyncio.create_task(
                    self._verify_wake(np.concatenate(clip).astype(np.int16)), name="verify"
                )

    async def _verify_wake(self, clip: Any) -> bool:
        """Whisper transcribe los últimos 2 s mientras el usuario sigue hablando (SPEC 4.4).

        Si «Nyx» no aparece, la escucha se cancela sin decir nada. Si whisper falla, no se
        penaliza al usuario: se da por buena.
        """
        assert self.stt is not None
        t0 = self._clock()
        try:
            text = await self.stt.transcribe(clip, prompt=STT_PROMPT)
        except STTError:
            log.warning("No se pudo verificar «Nyx»: se da por buena", exc_info=True)
            return True
        ok = has_wake_word(text)
        log.info("Verificación de «Nyx» (%d ms): %r → %s", _ms(self._clock() - t0), text, ok)
        listening = self._listening
        if not ok and listening is not None and listening.verify is asyncio.current_task():
            log.info("Activación descartada: whisper no ha oído «Nyx»")
            self._drop_listening(cancel_verify=False)
            await self._go_idle()
        return ok

    def _drop_listening(self, *, cancel_verify: bool = True) -> None:
        listening, self._listening = self._listening, None
        if listening is not None and listening.verify is not None and cancel_verify:
            listening.verify.cancel()
        if self.wake is not None:
            self.wake.reset()

    async def start_listening(
        self, prebuffer_s: float = 0.0, *, followup: bool = False, manual: bool = False
    ) -> None:
        self._drop_listening()
        await self._cancel_request()
        if self.vad is not None:
            self.vad.reset()
        frames = self.capture.prebuffer(prebuffer_s) if self.capture and prebuffer_s else []
        timeout = self.listen.followup_s if followup else self.listen.start_timeout_s
        self._listening = _Listening(
            endpointer=Endpointer(
                silence_ms=self.listen.silence_ms,
                max_s=self.listen.max_s,
                start_timeout_s=timeout,
            ),
            frames=list(frames),
            followup=followup,
            manual=manual,
            key_held=manual,
            pressed_at=self._clock(),
        )
        self.mode = Mode.LISTENING
        await self._set_state(NyxState.LISTENING)

    async def _listen_frame(self, frame: Frame) -> None:
        listening = self._listening
        assert listening is not None and self.vad is not None
        listening.frames.append(frame)
        await self.bus.publish(AudioLevel(rms_level(frame)))
        reason = listening.endpointer.push(self.vad(frame))
        if listening.key_held and reason in (EndReason.SILENCE, EndReason.NO_SPEECH):
            reason = None  # mientras se mantiene el atajo, las pausas no cortan
        if reason is not None:
            await self._end_listening(reason)

    async def _end_listening(self, reason: EndReason) -> None:
        listening = self._listening
        self._drop_listening(cancel_verify=False)
        if listening is None:
            return
        if not listening.endpointer.speech_started:
            log.info("Escucha terminada sin voz (%s)", reason)
            if listening.verify is not None:
                listening.verify.cancel()
            await self._go_idle()
            return
        audio = np.concatenate(listening.frames).astype(np.int16)
        marks = _Marks(end=self._clock())
        log.debug("Frase de %.1f s (%s)", audio.size / 16_000, reason)
        self.mode = Mode.BUSY
        self._start_request(self._handle_audio(audio, marks, listening.verify))

    # --- entradas de la interfaz ---

    async def _on_text(self, event: TextEntered) -> None:
        text = event.text.strip()
        if not text:
            return
        self._drop_listening()
        await self._cancel_request()
        self.mode = Mode.BUSY
        self._start_request(self._respond(text, _Marks(end=self._clock()), from_voice=False))

    async def _on_talk(self, event: TalkKey) -> None:
        if not self.voice_enabled:
            return
        listening = self._listening
        if event.pressed:
            if listening is not None:
                if not listening.key_held:  # ya escuchaba por la palabra: pasa a manual
                    listening.manual = listening.key_held = True
                    listening.pressed_at = self._clock()
                return  # repetición de tecla
            await self.start_listening(TALK_PREBUFFER_S, manual=True)
        elif listening is not None and listening.key_held:
            listening.key_held = False
            if self._clock() - listening.pressed_at >= HOLD_S:
                await self._end_listening(EndReason.MANUAL)
            # Toque corto: el VAD decide cuándo termina la frase.

    # --- peticiones ---

    def _start_request(self, coro: Coroutine[Any, Any, None]) -> None:
        self._request = asyncio.create_task(self._run_request(coro), name="request")

    async def _run_request(self, coro: Coroutine[Any, Any, None]) -> None:
        new_request_id()
        try:
            await coro
        except asyncio.CancelledError:
            log.info("Petición cancelada")
            raise
        except Exception:
            log.exception("Fallo inesperado en la petición")
            await self._fail("Algo ha fallado", "inténtalo otra vez", None)

    async def _cancel_request(self) -> None:
        task = self._request
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await self._hide_bubble()
        if self.player is not None:
            self.player.clear()

    async def _handle_audio(
        self, audio: Any, marks: _Marks, verify: asyncio.Task[bool] | None = None
    ) -> None:
        assert self.stt is not None
        thinking = asyncio.create_task(self._thinking_later())
        try:
            raw = await self.stt.transcribe(audio, prompt=STT_PROMPT)
            # Vale si whisper oyó «Nyx» en el fragmento corto o al principio de la frase.
            verified = verify is None or await verify or has_wake_word(raw, first_words=3)
        except STTError:
            log.exception("Fallo al transcribir")
            await self._fail("No he podido oírte bien", "fallo al transcribir", None)
            return
        finally:
            thinking.cancel()
        marks.stt = self._clock()
        text = normalize(raw)
        log.info("Transcripción (%d ms): %r → %r", _ms(marks.stt - marks.end), raw, text)
        if not verified:
            log.info("Activación descartada: whisper no ha oído «Nyx»")
            await self._go_idle()
            return
        if not text:
            await self._go_idle()
            return
        await self._respond(text, marks, from_voice=True)

    async def _thinking_later(self) -> None:
        await asyncio.sleep(THINKING_AFTER_S)
        await self._set_state(NyxState.THINKING)

    async def _respond(self, text: str, marks: _Marks, *, from_voice: bool) -> None:
        await self._set_state(NyxState.THINKING)
        bubble: BubbleReady | None = None
        bubble_shown = False
        splitter = SentenceSplitter()
        level_task: asyncio.Task[None] | None = None

        async def show_bubble() -> None:
            nonlocal bubble_shown
            if bubble is not None and (bubble.display or bubble.secondary):
                bubble_shown = True
                await self._show_bubble(bubble.display, bubble.secondary)

        async def on_speech_start() -> None:
            nonlocal level_task
            marks.first_audio = self._clock()
            await self._set_state(NyxState.SPEAKING)
            await show_bubble()
            level_task = asyncio.create_task(self._speaking_levels())
            log.info("Latencia: %s", _latency(marks))

        # Si la petición se escribió, por defecto la respuesta va solo en la burbuja (quien
        # escribe suele querer silencio); el ajuste responses.speak_typed la hace hablada.
        speak = from_voice or self.speak_typed
        speech = (
            _Speech(self.tts, self.player, on_speech_start)
            if speak and self.tts is not None and self.player is not None
            else None
        )
        try:
            async for event in self.brain.respond(text):
                if marks.first_token is None:
                    marks.first_token = self._clock()
                if isinstance(event, BubbleReady):
                    bubble = event
                    if bubble_shown:
                        await show_bubble()
                elif isinstance(event, SpokenDelta) and speech is not None:
                    for sentence in splitter.feed(event.text):
                        if marks.first_sentence is None:
                            marks.first_sentence = self._clock()
                        speech.say(sentence)
                elif isinstance(event, SpokenEnd) and speech is not None:
                    if rest := splitter.flush():
                        marks.first_sentence = marks.first_sentence or self._clock()
                        speech.say(rest)
                elif isinstance(event, ReplyDone):
                    log.info("Respuesta: %s", event.reply.model_dump_json())
                    if speech is None:
                        bubble = text_bubble(event.reply)
            if speech is not None and (rest := splitter.flush()):
                marks.first_sentence = marks.first_sentence or self._clock()
                speech.say(rest)
            if speech is not None:
                await speech.finish()
            if not bubble_shown:
                if speech is None or not speech.started:
                    log.info("Latencia (sin voz): %s", _latency(marks))
                await show_bubble()
        except LLMError as e:
            log.error("Fallo del LLM: %s", e)
            if speech is not None:
                await speech.abort()
            display, secondary, spoken = ERRORS[e.kind]
            await self._fail(display, secondary, spoken if speak else None)
            return
        except asyncio.CancelledError:
            if speech is not None:
                await speech.abort()
            raise
        finally:
            if level_task is not None:
                level_task.cancel()
        if bubble_shown and bubble is not None:
            self._schedule_bubble_hide(bubble_duration(bubble.display, bubble.secondary))
        if from_voice and self.listen.followup_s > 0 and self.capture is not None:
            await self.start_listening(followup=True)
        else:
            await self._go_idle()

    async def _speaking_levels(self) -> None:
        assert self.player is not None
        while True:
            await self.bus.publish(AudioLevel(self.player.level))
            await asyncio.sleep(1 / LEVEL_HZ)

    async def _fail(self, display: str, secondary: str, spoken: str | None) -> None:
        await self._set_state(NyxState.ERROR)
        await self._show_bubble(display, secondary)
        played = False
        if spoken and self.tts is not None and self.player is not None:
            try:
                self.player.enqueue(await self.tts.synthesize(spoken))
                await self.player.drain()
                played = True
            except TTSError:
                log.exception("No se pudo decir el error")
        if not played:
            await asyncio.sleep(ERROR_HOLD_S)
        self._schedule_bubble_hide(bubble_duration(display, secondary))
        await self._go_idle()

    # --- estado y burbuja ---

    async def _go_idle(self) -> None:
        self.mode = Mode.IDLE
        await self._set_state(NyxState.IDLE)

    async def _set_state(self, state: NyxState) -> None:
        if state is not self.state:
            self.state = state
            await self.bus.publish(StateChanged(state))

    async def _show_bubble(self, display: str, secondary: str) -> None:
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        await self.bus.publish(BubbleShown(display=display, secondary=secondary or None))

    async def _hide_bubble(self) -> None:
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        await self.bus.publish(BubbleHidden())

    def _schedule_bubble_hide(self, seconds: float) -> None:
        async def hide_later() -> None:
            await asyncio.sleep(seconds)
            self._bubble_timer = None
            await self.bus.publish(BubbleHidden())

        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
        self._bubble_timer = asyncio.create_task(hide_later(), name="bubble-hide")


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def _latency(m: _Marks) -> str:
    parts = []
    if m.first_audio is not None:
        parts.append(f"fin de frase → voz {_ms(m.first_audio - m.end)} ms")
    if m.stt is not None:
        parts.append(f"stt {_ms(m.stt - m.end)}")
    start = m.stt if m.stt is not None else m.end
    if m.first_token is not None:
        parts.append(f"1.er token {_ms(m.first_token - start)}")
    if m.first_sentence is not None:
        parts.append(f"1.ª frase {_ms(m.first_sentence - start)}")
    if m.first_audio is not None and m.first_sentence is not None:
        parts.append(f"tts {_ms(m.first_audio - m.first_sentence)}")
    return ", ".join(parts) or "sin datos"
