"""Arnés de la batería de audio: el pipeline real de Nyx con audio grabado y sin ejecutar nada.

Lo de verdad: detección de voz (Silero), detector de «Nyx», Whisper, router, LLM y el propio
`Pipeline` con sus pausas y su ventana de seguimiento. Lo simulado: el micrófono (el audio se
le pasa bloque a bloque **a la velocidad real**, porque las pausas y las transcripciones a
mitad de frase dependen del tiempo), la voz (no suena) y el ejecutor, que **solo apunta** lo
que haría: ninguna acción toca el equipo (`DryExecutor`).

Lo que pasa se recoge desde fuera, sin cambiar el pipeline: el ejecutor y la voz simulados, un
envoltorio de Whisper y los registros del pipeline (sus argumentos, no el texto).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from nyx.audio.capture import FRAME_S, FRAME_SAMPLES, Frame
from nyx.bench.audio import Audio
from nyx.events import BubbleShown
from nyx.executor import Executor, ToolCall, describe_call
from nyx.pipeline import Mode, Pipeline
from nyx.tools.base import ToolResult

log = logging.getLogger(__name__)


# --- piezas simuladas ---


class DryExecutor(Executor):
    """Valida cada llamada como el de verdad y la apunta, pero no la ejecuta nunca."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[float, str, dict[str, Any]]] = []

    async def run(self, call: ToolCall, *, phrase: str = "", voice: bool = False) -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            return ToolResult.fail("No sé hacer eso todavía")
        try:
            tool.params_model.model_validate(call.arguments)
        except Exception:
            return ToolResult.fail("No te he entendido")
        self.calls.append((time.perf_counter(), call.name, dict(call.arguments)))
        # Sin otra vuelta al LLM (`observe=False`): lo que se mide es el plan.
        return ToolResult(ok=True, message=f"Hecho: {describe_call(call)}", observe=False)


class SilentTTS:
    """Voz que no suena: apunta qué se iba a decir y cuándo estuvo lista la primera frase."""

    sample_rate = 24_000

    def __init__(self) -> None:
        self.said: list[tuple[float, str]] = []

    async def load(self) -> None:
        pass

    async def synthesize(self, text: str) -> npt.NDArray[np.float32]:
        self.said.append((time.perf_counter(), text))
        return np.zeros(240, dtype=np.float32)

    async def stream(self, text: str) -> AsyncIterator[npt.NDArray[np.float32]]:
        yield await self.synthesize(text)


class NullPlayer:
    level = 0.5
    queued_s = 0.0

    def prepare(self) -> None:
        pass

    def enqueue(self, samples: Any) -> None:
        pass

    def clear(self) -> None:
        pass

    def fade_out(self, ms: float = 150.0) -> None:
        pass

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass


class BenchCapture:
    """El «micrófono»: guarda los últimos segundos para la verificación y el audio previo."""

    def __init__(self, keep_s: float = 3.0) -> None:
        self.ring: deque[Frame] = deque(maxlen=int(keep_s / FRAME_S) + 1)

    def push(self, frame: Frame) -> None:
        self.ring.append(frame)

    def prebuffer(self, seconds: float) -> list[Frame]:
        n = round(seconds / FRAME_S)
        return list(self.ring)[-n:] if n else []

    def stop(self) -> None:
        pass


class TimedSTT:
    """Envuelve el Whisper de verdad y apunta cada transcripción (para contar las de la
    gráfica: las verificaciones de «Nyx» también cuentan)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: list[tuple[float, float, float, str]] = []  # (inicio, ms, s de audio, texto)

    async def transcribe(self, pcm: npt.NDArray[np.int16], prompt: str = "") -> str:
        t0 = time.perf_counter()
        text: str = await self.inner.transcribe(pcm, prompt=prompt)
        self.calls.append((t0, (time.perf_counter() - t0) * 1000, pcm.size / 16_000, text))
        return text

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class _PipelineLog(logging.Handler):
    """Recoge los registros del pipeline que interesan, con sus argumentos tal cual."""

    WANTED = (
        "Transcripción (",
        "Verificación de",
        "Activación descartada",
        "Escucha terminada",
        "Latencia",
        "Transcripción en otro idioma",
    )

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.records: list[tuple[float, str, tuple[Any, ...]]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = str(record.msg)
        if msg.startswith(self.WANTED):
            args = record.args if isinstance(record.args, tuple) else ()
            self.records.append((time.perf_counter(), msg, args))


# --- resultado de una frase ---


@dataclass
class Trace:
    """Lo que pasó con una frase."""

    fed_from: float = 0.0  # cuándo empezó a sonar la grabación
    speech_end: float | None = None  # cuándo dejó de hablar el usuario (de la grabación limpia)
    listen_end: float | None = None  # cuándo dio Nyx la frase por terminada
    end_reason: str = ""
    transcript: str = ""  # lo que entendió de la petición (sin «Nyx»)
    raw_transcript: str = ""
    # Lo que entendió después, en la ventana de seguimiento (fondo, otra gente…).
    later: list[str] = field(default_factory=list)
    path: str = ""  # router / llm / shortcut…
    calls: list[tuple[float, str, dict[str, Any]]] = field(default_factory=list)
    said: list[tuple[float, str]] = field(default_factory=list)
    bubbles: list[str] = field(default_factory=list)
    stt_calls: list[tuple[float, float, float, str]] = field(default_factory=list)
    verifications: list[tuple[str, bool]] = field(default_factory=list)
    foreign: bool = False

    @property
    def activated(self) -> bool:
        return self.listen_end is not None and self.end_reason != "no_speech"

    @property
    def reply(self) -> str:
        return " ".join([t for _, t in self.said] or self.bubbles)

    @property
    def first_output(self) -> float | None:
        """Cuándo hizo o dijo algo por primera vez."""
        times = [t for t, *_ in self.calls] + [t for t, _ in self.said]
        return min(times) if times else None


# --- el arnés ---


class Bench:
    """El pipeline real alimentado con audio grabado, frase a frase."""

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        capture: BenchCapture,
        executor: DryExecutor,
        tts: SilentTTS,
        stt: TimedSTT,
        realtime: bool = True,
    ) -> None:
        self.p = pipeline
        self.capture = capture
        self.executor = executor
        self.tts = tts
        self.stt = stt
        self.realtime = realtime
        self._log = _PipelineLog()
        pipeline_log = logging.getLogger("nyx.pipeline")
        # Sin configurar el registro, solo pasan los avisos: hacen falta los INFO del pipeline.
        self._old_level = pipeline_log.level
        pipeline_log.setLevel(logging.INFO)
        pipeline_log.addHandler(self._log)
        self._bubbles: list[tuple[float, str]] = []
        self._ends: list[tuple[float, str]] = []
        self._clock_start: float | None = None
        self._fed = 0
        pipeline.bus.subscribe(BubbleShown, self._on_bubble)
        # Cuándo y por qué da Nyx la frase por terminada: envolviendo el método (sin cambiarlo).
        original = pipeline._end_listening

        async def end_listening(reason: Any, transcript: str | None = None) -> None:
            self._ends.append((time.perf_counter(), str(reason)))
            await original(reason, transcript=transcript)

        pipeline._end_listening = end_listening  # type: ignore[method-assign]

    async def _on_bubble(self, e: BubbleShown) -> None:
        self._bubbles.append((time.perf_counter(), e.display))

    async def feed(self, audio: Audio) -> None:
        """Pasa el audio bloque a bloque; con `realtime`, al ritmo de un micrófono."""
        loop = asyncio.get_running_loop()
        if self._clock_start is None:
            self._clock_start = loop.time()
            self._fed = 0
        for i in range(audio.size // FRAME_SAMPLES):
            frame = audio[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
            if self.realtime:
                due = self._clock_start + self._fed * FRAME_S
                delay = due - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                elif delay < -1.0:
                    # Muy atrasado (el bucle estuvo ocupado): se reengancha sin acelerar de golpe.
                    self._clock_start = loop.time() - self._fed * FRAME_S
            self.capture.push(frame)
            self._fed += 1
            await self.p.process_frame(frame)
            await asyncio.sleep(0)

    def busy(self, *, followup_ok: bool = False) -> bool:
        """¿Sigue Nyx con algo? Con `followup_ok`, escuchar en la ventana de seguimiento no
        cuenta (la frase siguiente de un grupo se dice ahí)."""
        request = self.p._request
        if request is not None and not request.done():
            return True
        if followup_ok:
            listening = self.p._listening
            return self.p.mode is Mode.BUSY or (
                self.p.mode is Mode.LISTENING and (listening is None or not listening.followup)
            )
        return self.p.mode is not Mode.IDLE

    async def settle(
        self,
        background: Callable[[int], Audio],
        *,
        min_s: float,
        max_s: float,
        followup_ok: bool = False,
    ) -> None:
        """Sigue pasando fondo hasta que Nyx termine (o `max_s`), al menos `min_s`."""
        chunk = FRAME_SAMPLES * 4
        waited = 0.0
        while waited < max_s:
            await self.feed(background(chunk))
            waited += chunk / 16_000
            if waited >= min_s and not self.busy(followup_ok=followup_ok):
                return

    async def run(
        self,
        clip: Audio,
        background: Callable[[int], Audio],
        *,
        speech_end_s: float | None,
        lead_s: float = 2.0,
        max_wait_s: float = 25.0,
        then_followup: bool = False,
    ) -> Trace:
        """Una frase: `lead_s` de fondo, la grabación (ya mezclada) y fondo hasta el reposo.

        `then_followup`: la frase siguiente es de la misma conversación; se para en cuanto Nyx
        ha respondido, con la ventana de seguimiento aún abierta."""
        marks = (
            len(self.executor.calls),
            len(self.tts.said),
            len(self._bubbles),
            len(self.stt.calls),
            len(self._log.records),
            len(self._ends),
        )
        if lead_s:
            await self.feed(background(int(lead_s * 16_000)))
        trace = Trace(fed_from=time.perf_counter())
        if speech_end_s is not None:
            trace.speech_end = trace.fed_from + speech_end_s
        await self.feed(clip)
        await self.settle(background, min_s=0.8, max_s=max_wait_s, followup_ok=then_followup)
        if not then_followup:
            await self.p.wait_idle()
        calls, said, bubbles, stt, records, ends = marks
        trace.calls = self.executor.calls[calls:]
        trace.said = self.tts.said[said:]
        trace.bubbles = [t for _, t in self._bubbles[bubbles:]]
        trace.stt_calls = self.stt.calls[stt:]
        for end_at, reason in self._ends[ends:]:
            if trace.listen_end is None or reason != "no_speech":
                trace.listen_end, trace.end_reason = end_at, reason
                if reason != "no_speech":
                    break
        for _, msg, args in self._log.records[records:]:
            if msg.startswith("Transcripción (") and len(args) >= 3:
                if trace.raw_transcript:
                    trace.later.append(str(args[1]))
                else:
                    trace.raw_transcript, trace.transcript = str(args[1]), str(args[2])
            elif msg.startswith("Verificación de") and len(args) >= 3:
                trace.verifications.append((str(args[1]), str(args[2]) == "True"))
            elif msg.startswith("Latencia (acción") and args:
                trace.path = "llm" if args[0] == "llm" else f"router:{args[0]}"
            elif msg.startswith("Latencia (respuesta directa"):
                trace.path = trace.path or "router:respuesta"
            elif msg.startswith("Latencia"):
                trace.path = trace.path or "llm"
            elif msg.startswith("Transcripción en otro idioma"):
                trace.foreign = True
        return trace

    def close(self) -> None:
        pipeline_log = logging.getLogger("nyx.pipeline")
        pipeline_log.removeHandler(self._log)
        pipeline_log.setLevel(self._old_level)


def background_stream(audio: Audio | None, start: int = 0) -> Callable[[int], Audio]:
    """Un fondo que sigue sonando de corrido (el ruido no para entre frase y frase)."""
    pos = start

    def take(n: int) -> Audio:
        nonlocal pos
        if audio is None or audio.size == 0:
            return np.zeros(n, dtype=np.int16)
        idx = (np.arange(n) + pos) % audio.size
        pos += n
        return audio[idx]

    return take
