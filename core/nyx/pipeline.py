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
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import numpy as np

from nyx.alarms.ringer import AlarmRinger
from nyx.audio.capture import AudioCapture, Frame, rms_level
from nyx.audio.playback import Player
from nyx.audio.vad import Endpointer, EndReason, VoiceDetector
from nyx.brain.base import LLMError, LLMErrorKind
from nyx.brain.reply import BubbleReady, Reply, SpokenDelta, SpokenEnd
from nyx.brain.router import Miss, Route
from nyx.brain.service import Brain, ReplyDone, ToolPlan
from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    AudioLevel,
    BubbleAction,
    BubbleHidden,
    BubbleShown,
    NyxState,
    StateChanged,
    TalkKey,
    TextEntered,
)
from nyx.executor import Confirmation, Executor, ToolCall, with_waits
from nyx.index.aliases import normalize as normalize_alias
from nyx.log import new_request_id
from nyx.safety.undo import UNDO_TTL_S
from nyx.settings.model import ListenSettings
from nyx.stt.base import STTEngine, STTError
from nyx.stt.normalize import has_wake_word, normalize
from nyx.tools.base import ToolResult
from nyx.tts.base import TTSEngine, TTSError
from nyx.tts.sentences import SentenceSplitter
from nyx.wake.base import WakeWordEngine
from nyx.winapi import windows

log = logging.getLogger(__name__)

# Vocabulario para Whisper: mejora la transcripción de «Nyx» (fase 3: apps y carpetas de la caché).
STT_PROMPT = "Nyx."
THINKING_AFTER_S = 0.3  # «pensando» solo si la transcripción tarda (SPEC sección 3)
HOLD_S = 0.4  # mantener el atajo más que esto = hablar mientras se mantiene
TALK_PREBUFFER_S = 0.3
VERIFY_CLIP_S = 2.0  # audio que whisper revisa para confirmar «Nyx»
CONFIRM_TIMEOUT_S = 15.0  # SPEC sección 8: sin respuesta, se cancela
CANCELLED_BUBBLE_S = 2.5
UNDONE_BUBBLE_S = 4.0
NOTICE_BUBBLE_S = 5.0  # avisos (alarma puesta…): se van solos
MISS_LLM_MIN = 70.0  # «abre X» sin coincidencia: se consulta al LLM solo si algo se parece
# Pausa tras la que se transcribe lo dicho para ver si la petición ya está completa.
EARLY_PAUSE_S = 0.4
# Ventana de seguimiento: silencio previo exigido para que una frase cuente como nueva.
FOLLOWUP_QUIET_S = 0.25
# Una «pregunta» que acaba así está a medias («¿cómo se dice … de?»).
_INCOMPLETE = "a al de del el la los las en con por para que y o u un una mi tu su como"
INCOMPLETE_ENDINGS = frozenset(_INCOMPLETE.split(" "))
# Coletillas que, en la ventana de seguimiento, casi nunca van dirigidas a Nyx.
FILLERS = frozenset(
    {
        "si",
        "no",
        "vale",
        "bueno",
        "ok",
        "okey",
        "claro",
        "ya",
        "venga",
        "gracias",
        "muchas gracias",
        "vale gracias",
        "perfecto",
        "genial",
        "de acuerdo",
        "entendido",
        "aja",
        "eh",
        "ah",
        "mm",
        "pues",
        "pues nada",
        "nada",
        "bien",
        "si claro",
        "vale vale",
        "ya ya",
        "que",
        "como",
        "hola",
        "adios",
        "jaja",
        "jajaja",
    }
)
LEVEL_HZ = 30
ERROR_HOLD_S = 2.5


class Mode(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    BUSY = "busy"
    CONFIRM = "confirm"  # esperando «sí» o «no» (o un clic)


class YesNoDetector(Protocol):
    def process(self, frame: Frame) -> bool | None: ...

    def reset(self) -> None: ...


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
    # Transcripción anticipada en cada pausa corta (ver _speculate).
    spec: asyncio.Task[None] | None = None
    spec_text: str | None = None
    spoke_since_spec: bool = True


@dataclass
class _Marks:
    """Tiempos de una petición para la línea de latencia del registro."""

    end: float
    stt: float | None = None
    first_token: float | None = None
    first_sentence: float | None = None
    first_audio: float | None = None
    phrase: str = ""  # lo que pidió el usuario (para el registro de acciones)


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


def is_filler(text: str) -> bool:
    return normalize_alias(text) in FILLERS


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
                # Cada trozo suena en cuanto se genera (Pocket: el primero en ~0,08 s).
                async for audio in self._tts.stream(text):
                    if not self.started:
                        self.started = True
                        await self._on_start()
                    self._player.enqueue(audio)
            except TTSError:
                log.exception("Fallo de la voz con %r", text)

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
        router: Callable[[str], Route | Miss | None] | None = None,
        executor: Executor | None = None,
        yesno: YesNoDetector | None = None,
        ringer: AlarmRinger | None = None,
        shortcuts: ShortcutStore | None = None,
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
        self.router = router
        self.executor = executor
        self.ringer = ringer
        self.shortcuts = shortcuts
        self._learned_last: tuple[str, float] | None = None  # (frase, cuándo) para olvidarla
        self._clock = clock
        self.mode = Mode.IDLE
        self.state = NyxState.IDLE
        self._listening: _Listening | None = None
        self.yesno = yesno
        self._request: asyncio.Task[None] | None = None
        self._bubble_timer: asyncio.Task[None] | None = None
        # Botones de la burbuja visible: id → qué hacer al pulsarlo.
        self._actions: dict[str, Callable[[], None]] = {}
        self._answer: asyncio.Future[bool] | None = None  # confirmación pendiente
        self._from_voice = False  # la petición en curso se hizo hablando
        self._side_tasks: set[asyncio.Task[None]] = set()
        if executor is not None and executor.confirm is None:
            executor.confirm = self.confirm
        self._unsubscribe = [
            bus.subscribe(TextEntered, self._on_text),
            bus.subscribe(TalkKey, self._on_talk),
            bus.subscribe(ActionChosen, self._on_action),
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
        if self.mode is Mode.CONFIRM:
            if self.yesno is not None and (said := self.yesno.process(frame)) is not None:
                log.info("Confirmación por voz: %s", "sí" if said else "no")
                self._resolve(said)
            return
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
        if listening is not None and cancel_verify:
            for task in (listening.verify, listening.spec):
                if task is not None and task is not asyncio.current_task():
                    task.cancel()
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
                # En la ventana de seguimiento solo cuenta una frase nueva, no una
                # conversación que ya estaba en marcha.
                require_quiet_s=FOLLOWUP_QUIET_S if followup else 0.0,
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
        endpointer = listening.endpointer
        prob = self.vad(frame)
        reason = endpointer.push(prob)
        if prob >= endpointer.start_threshold:
            listening.spoke_since_spec = True
        if listening.key_held and reason in (EndReason.SILENCE, EndReason.NO_SPEECH):
            reason = None  # mientras se mantiene el atajo, las pausas no cortan
        if reason is not None:
            await self._end_listening(reason)
            return
        if (
            endpointer.speech_started
            and endpointer.pause_s >= EARLY_PAUSE_S
            and listening.spoke_since_spec
            and not listening.key_held
            and self.stt is not None
        ):
            listening.spoke_since_spec = False
            if listening.spec is not None:
                listening.spec.cancel()
            audio = np.concatenate(listening.frames).astype(np.int16)
            listening.spec = asyncio.create_task(self._speculate(listening, audio), name="spec")

    async def _speculate(self, listening: _Listening, audio: Any) -> None:
        """Transcribe lo dicho hasta una pausa corta (~0,4 s) mientras se sigue escuchando.

        - Si ya es una petición completa («¿qué hora es?», «abre Spotify»), se deja de
          escuchar ahí: lo que el usuario diga después (a otra persona) no cuenta.
        - Si el usuario no vuelve a hablar, al cerrar la frase se reutiliza esta
          transcripción y la respuesta llega antes.
        """
        assert self.stt is not None
        try:
            raw = await self.stt.transcribe(audio, prompt=STT_PROMPT)
        except STTError:
            return
        listening.spec_text = raw
        if self._listening is listening and self._is_complete(raw):
            log.info("Petición completa tras una pausa: %r; dejo de escuchar", raw)
            await self._end_listening(EndReason.COMPLETE, transcript=raw)

    def _is_complete(self, raw: str) -> bool:
        """¿Es ya una petición entera? Una orden que el router entiende o una pregunta."""
        text = normalize(raw)
        if not text:
            return False
        if self.router is not None and isinstance(self.router(text), Route):
            return True
        words = text.rstrip("?").split()
        return (
            text.endswith("?") and len(words) >= 2 and words[-1].lower() not in INCOMPLETE_ENDINGS
        )

    async def _end_listening(self, reason: EndReason, transcript: str | None = None) -> None:
        listening = self._listening
        self._drop_listening(cancel_verify=False)
        if listening is None:
            return
        if not listening.endpointer.speech_started:
            log.info("Escucha terminada sin voz (%s)", reason)
            for task in (listening.verify, listening.spec):
                if task is not None:
                    task.cancel()
            await self._go_idle()
            return
        # Si no ha vuelto a hablar desde la última transcripción anticipada, se reutiliza.
        pending = None
        if transcript is None and listening.spec is not None:
            if listening.spoke_since_spec:
                listening.spec.cancel()
            else:
                pending = listening.spec
        audio = np.concatenate(listening.frames).astype(np.int16)
        marks = _Marks(end=self._clock())
        log.debug("Frase de %.1f s (%s)", audio.size / 16_000, reason)
        self.mode = Mode.BUSY
        self._start_request(
            self._handle_audio(
                audio,
                marks,
                listening.verify,
                transcript=transcript,
                pending=pending,
                listening=listening,
            )
        )

    # --- entradas de la interfaz ---

    async def _on_text(self, event: TextEntered) -> None:
        text = event.text.strip()
        if not text:
            return
        self._drop_listening()
        await self._cancel_request()
        self.mode = Mode.BUSY
        self._start_request(self._handle_text(text, _Marks(end=self._clock()), from_voice=False))

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
        self,
        audio: Any,
        marks: _Marks,
        verify: asyncio.Task[bool] | None = None,
        *,
        transcript: str | None = None,
        pending: asyncio.Task[None] | None = None,
        listening: _Listening | None = None,
    ) -> None:
        assert self.stt is not None
        thinking = asyncio.create_task(self._thinking_later())
        try:
            raw = transcript
            if raw is None and pending is not None and listening is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await pending
                raw = listening.spec_text
            if raw is None:
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
        followup = listening is not None and listening.followup
        if followup and is_filler(text):
            log.info("Seguimiento ignorado (coletilla): %r", text)
            await self._go_idle()
            return
        await self._handle_text(text, marks, from_voice=True, followup=followup)

    async def _thinking_later(self) -> None:
        await asyncio.sleep(THINKING_AFTER_S)
        await self._set_state(NyxState.THINKING)

    async def _handle_text(
        self, text: str, marks: _Marks, *, from_voice: bool, followup: bool = False
    ) -> None:
        """Router rápido primero (acciones sin LLM); si no encaja, el LLM."""
        marks.phrase = text
        if self.ringer is not None and self.ringer.swallow(text):
            # «Nyx, para» con la alarma sonando: es para ella, no para la música.
            await self.ringer.stop()
            await self._hide_bubble()
            return
        if self.router is not None and self.executor is not None:
            routed = self.router(text)
            if isinstance(routed, Route):
                await self._act(routed, marks, from_voice=from_voice)
                return
        else:
            routed = None
        # Ventana de seguimiento: lo que no es una orden clara solo se atiende si va dirigido
        # a Nyx (el usuario puede estar hablando con otra persona).
        if followup and not await self.brain.addressed(text):
            log.info("Seguimiento ignorado: no iba dirigido a Nyx (%r)", text)
            await self._go_idle()
            return
        if self.shortcuts is not None and self.executor is not None:
            learned = self.shortcuts.lookup(text)
            if learned is not None:
                log.info("Atajo aprendido: %r → %s(%s)", text, learned.name, learned.arguments)
                await self._act(
                    Route(with_waits([learned]), "aprendido"), marks, from_voice=from_voice
                )
                return
        hint = ""
        if isinstance(routed, Miss):
            if not routed.candidates or routed.candidates[0].score < MISS_LLM_MIN:
                # Nada se parece de verdad: «No encuentro Spotify» directo (el LLM, sin una
                # pista útil, acababa diciendo «Aún no sé hacer eso»).
                await self._not_found(routed, from_voice=from_voice)
                return
            names = ", ".join(m.entry.name for m in routed.candidates[:3]) or "ninguno"
            hint = (
                f"«{routed.target}» no coincide con nada instalado. Lo más parecido: {names}. "
                "Si es uno de ellos, úsalo; si no, di que no lo encuentras."
            )
        await self._respond(text, marks, from_voice=from_voice, hint=hint)

    async def _act(self, routed: Route, marks: _Marks, *, from_voice: bool) -> list[ToolResult]:
        assert self.executor is not None
        if routed.rule == "undo":
            self._forget_recent()
        thinking = asyncio.create_task(self._thinking_later())
        try:
            self._from_voice = from_voice
            results = await self.executor.run_plan(routed.calls, phrase=marks.phrase)
        finally:
            thinking.cancel()
        log.info(
            "Latencia (acción, regla %s): fin de frase → hecho %d ms",
            routed.rule,
            _ms(self._clock() - marks.end),
        )
        speak = from_voice or self.speak_typed
        failed = next((r for r in results if not r.ok), None)
        if failed is not None and failed.data.get("cancelled"):
            await self._show_bubble("Cancelado", failed.secondary or "")
            self._schedule_bubble_hide(CANCELLED_BUBBLE_S)
            await self._go_idle()
            return results
        if failed is not None:
            spoken = failed.message if speak else None
            await self._fail(failed.display or failed.message, failed.secondary or "", spoken)
            return results
        # Éxito: en silencio, salvo que la herramienta tenga algo que enseñar (SPEC sección 3)
        # o que se pueda deshacer (amarillas: «Deshacer» durante 30 s).
        undoable = next((r for r in reversed(results) if r.data.get("undo_id")), None)
        shown = next((r for r in results if r.display), None)
        if undoable is not None:
            await self._offer_undo(undoable)
        elif shown is not None and shown.display:
            await self._show_bubble(shown.display, shown.secondary or "")
            self._schedule_bubble_hide(bubble_duration(shown.display, shown.secondary or ""))
        if from_voice and self.listen.followup_s > 0 and self.capture is not None:
            await self.start_listening(followup=True)
        else:
            await self._go_idle()
        return results

    def _learn(self, text: str, call: ToolCall) -> None:
        """SPEC sección 6: frase resuelta por el LLM con una sola acción → atajo."""
        if self.shortcuts is None or self.executor is None:
            return
        tool = self.executor.registry.get(call.name)
        key = self.shortcuts.learn(text, call, str(tool.risk) if tool else "red")
        if key is not None:
            self._learned_last = (key, self._clock())
            log.info("Atajo aprendido: %r → %s(%s)", key, call.name, call.arguments)

    def _forget_recent(self) -> None:
        """Se deshizo justo después de aprender: el atajo estaba mal."""
        if self.shortcuts is None or self._learned_last is None:
            return
        key, when = self._learned_last
        self._learned_last = None
        if self._clock() - when <= UNDO_TTL_S and self.shortcuts.forget(key):
            log.info("Atajo olvidado (se deshizo): %r", key)

    async def _context(self) -> str:
        """Lo que el LLM necesita saber del momento: la ventana activa («ciérrala»)."""
        try:
            fg = await asyncio.to_thread(windows.foreground)
        except Exception:
            return ""
        return f"Ventana activa: «{fg.title}» ({fg.process})." if fg else ""

    async def _run_plan(
        self, plan: ToolPlan, text: str, marks: _Marks, *, from_voice: bool, retried: bool
    ) -> None:
        calls = with_waits([ToolCall(c.name, c.arguments) for c in plan.calls])
        log.info("Plan del LLM: %s", [(c.name, c.arguments) for c in calls])
        if not retried and self.executor is not None:
            # SPEC sección 6: si la llamada no es válida, se reintenta una vez con el error.
            invalid = self.executor.check(calls)
            if invalid:
                log.info("Plan no válido (%s): se reintenta", invalid)
                hint = f"Tu llamada anterior no era válida: {invalid}. Corrígela."
                await self._respond(text, marks, from_voice=from_voice, hint=hint, retried=True)
                return
        results = await self._act(Route(calls, "llm"), marks, from_voice=from_voice)
        if len(plan.calls) == 1 and results and all(r.ok for r in results):
            self._learn(text, ToolCall(plan.calls[0].name, plan.calls[0].arguments))

    async def _not_found(self, miss: Miss, *, from_voice: bool) -> None:
        best = miss.candidates[0].entry.name if miss.candidates else None
        suggestion = f"¿quizá {best}?" if best else ""
        log.info(
            "Router: no encuentro %r (candidatos: %s)",
            miss.target,
            [m.entry.name for m in miss.candidates[:3]],
        )
        spoken = f"No encuentro {miss.target}." if from_voice or self.speak_typed else None
        await self._fail(f"No encuentro «{miss.target}»", suggestion, spoken)

    async def _respond(
        self,
        text: str,
        marks: _Marks,
        *,
        from_voice: bool,
        hint: str = "",
        retried: bool = False,
    ) -> None:
        await self._set_state(NyxState.THINKING)
        plan: ToolPlan | None = None
        extra = "\n".join(part for part in (await self._context(), hint) if part)
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
            async with contextlib.aclosing(self.brain.respond(text, extra)) as events:
                async for event in events:
                    if marks.first_token is None:
                        marks.first_token = self._clock()
                    if isinstance(event, ToolPlan):
                        plan = event
                    elif isinstance(event, BubbleReady):
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
            if plan is not None:
                if speech is not None:
                    await speech.abort()
                await self._run_plan(plan, text, marks, from_voice=from_voice, retried=retried)
                return
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

    async def _show_bubble(
        self, display: str, secondary: str, actions: tuple[BubbleAction, ...] = ()
    ) -> None:
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        if not actions:
            self._actions.clear()  # una burbuja nueva sustituye a los botones anteriores
        await self.bus.publish(
            BubbleShown(display=display, secondary=secondary or None, actions=actions)
        )

    async def _hide_bubble(self) -> None:
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        self._actions.clear()
        await self.bus.publish(BubbleHidden())

    # --- confirmación y deshacer (SPEC sección 8) ---

    async def confirm(self, request: Confirmation) -> bool:
        """Pregunta antes de una acción roja: botones y, si se puede, «sí» / «no» por voz.
        Sin respuesta en 15 s, se cancela."""
        loop = asyncio.get_running_loop()
        answer: asyncio.Future[bool] = loop.create_future()
        self._answer = answer
        yes, no = f"yes-{uuid.uuid4().hex[:8]}", f"no-{uuid.uuid4().hex[:8]}"
        by_voice = not request.click_only and self.yesno is not None and self.capture is not None
        hint = "solo con clic" if request.click_only else "di «sí» o «no»"
        detail = " · ".join(part for part in (request.detail, hint if by_voice else "") if part)
        await self._set_state(NyxState.CONFIRM)
        await self._show_bubble(
            request.summary,
            detail,
            (BubbleAction(yes, "Confirmar", primary=True), BubbleAction(no, "Cancelar")),
        )
        self._actions = {yes: lambda: self._resolve(True), no: lambda: self._resolve(False)}
        try:
            if self._from_voice and self.tts is not None and self.player is not None:
                with contextlib.suppress(TTSError):
                    self.player.enqueue(
                        await self.tts.synthesize(f"{request.summary}. ¿Confirmas?")
                    )
                    await self.player.drain()
            if by_voice and self.yesno is not None:
                self.yesno.reset()
                self.mode = Mode.CONFIRM
            return await asyncio.wait_for(answer, CONFIRM_TIMEOUT_S)
        except TimeoutError:
            log.info("Confirmación caducada: %s", request.summary)
            return False
        finally:
            self._answer = None
            self._actions.clear()
            if self.mode is Mode.CONFIRM:
                self.mode = Mode.BUSY
            await self._set_state(NyxState.THINKING)

    def _resolve(self, value: bool) -> None:
        if self._answer is not None and not self._answer.done():
            self._answer.set_result(value)

    async def _on_action(self, event: ActionChosen) -> None:
        handler = self._actions.get(event.id)
        if handler is None:
            log.info("Botón %s ya no está activo", event.id)
            return
        handler()

    async def _offer_undo(self, result: ToolResult) -> None:
        undo_id = str(result.data["undo_id"])
        button = f"undo-{undo_id}"
        await self._show_bubble(
            result.display or result.message,
            result.secondary or "",
            (BubbleAction(button, "Deshacer"),),
        )
        self._actions = {button: lambda: self._spawn(self._undo(undo_id))}
        # Alarmas y temporizadores: aviso corto (se puede decir «deshaz» los 30 s igualmente).
        short = "alarm_id" in result.data
        self._schedule_bubble_hide(NOTICE_BUBBLE_S if short else UNDO_TTL_S)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._side_tasks.add(task)
        task.add_done_callback(self._side_tasks.discard)

    async def _undo(self, undo_id: str) -> None:
        """Botón «Deshacer» de la burbuja."""
        if self.executor is None:
            return
        self._actions.clear()
        self._forget_recent()
        result = await self.executor.run(
            ToolCall("undo", {"id": undo_id}), phrase="(botón Deshacer)"
        )
        await self._show_bubble(result.display or result.message, result.secondary or "")
        self._schedule_bubble_hide(UNDONE_BUBBLE_S)

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
