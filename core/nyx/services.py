"""Arranque de los servicios de voz a partir de los ajustes.

Todo se carga en paralelo (objetivo: listo en menos de 10 s). Si una pieza falla, Nyx sigue
con lo que tenga y lo avisa una vez (SPEC sección 2): sin whisper o sin micrófono queda la
entrada por texto; sin Kokoro, las respuestas solo salen en la burbuja.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from nyx.audio.capture import AudioCapture
from nyx.audio.playback import Player
from nyx.audio.vad import SileroVAD
from nyx.brain.base import LLMError
from nyx.brain.ollama import OllamaEngine, launch_ollama
from nyx.brain.router import route
from nyx.brain.service import Brain
from nyx.bus import EventBus
from nyx.events import BubbleHidden, BubbleShown
from nyx.executor import Executor
from nyx.index.scanners.apps import start_menu_dirs
from nyx.index.scanners.folders import known_folders
from nyx.index.scanners.games import steam_root
from nyx.index.service import SystemIndex
from nyx.index.watcher import IndexWatcher
from nyx.models import MODELS
from nyx.paths import local_dir
from nyx.pipeline import Pipeline
from nyx.settings.model import Settings
from nyx.stt.whisper_server import WhisperServer
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry
from nyx.tts.kokoro import KokoroTTS
from nyx.wake.vosk_engine import VoskWakeWord

log = logging.getLogger(__name__)

NOTICE_DELAY_S = 3.0  # da tiempo a que la interfaz se conecte antes de avisar
NOTICE_S = 8.0


def whisper_server_path(settings: Settings) -> Path:
    return settings.stt.server or local_dir() / "whisper" / "whisper-server.exe"


class Services:
    def __init__(
        self,
        pipeline: Pipeline,
        llm: OllamaEngine,
        stt: WhisperServer | None,
        index: SystemIndex,
        watcher: IndexWatcher | None,
    ) -> None:
        self.pipeline = pipeline
        self.llm = llm
        self.stt = stt
        self.index = index
        self.watcher = watcher
        self.notice: asyncio.Task[None] | None = None
        self.background: set[asyncio.Task[int]] = set()

    async def close(self) -> None:
        if self.notice is not None:
            self.notice.cancel()
        for task in self.background:
            task.cancel()
        if self.watcher is not None:
            self.watcher.stop()
        await self.pipeline.close()
        if self.stt is not None:
            await self.stt.stop()
        await self.llm.unload()  # libera la VRAM al salir
        await self.llm.aclose()
        self.index.close()


async def _attempt[T](name: str, problems: list[str], load: Callable[[], Awaitable[T]]) -> T | None:
    try:
        return await load()
    except Exception as e:
        log.warning("%s no disponible: %s", name, e, exc_info=log.isEnabledFor(logging.DEBUG))
        problems.append(name)
        return None


async def build(bus: EventBus, settings: Settings, *, voice: bool = True) -> Services:
    t0 = time.perf_counter()
    problems: list[str] = []

    llm = OllamaEngine(
        settings.llm.host,
        settings.llm.model,
        keep_alive=settings.llm.keep_alive,
        num_ctx=settings.llm.num_ctx,
        timeout_s=settings.llm.timeout_s,
        launcher=launch_ollama,
    )

    brain = Brain(llm)

    async def load_llm() -> None:
        try:
            await brain.warmup()
        except LLMError as e:
            # No es fatal: Ollama puede abrirse después. Cada petición lo vuelve a intentar.
            log.warning("Ollama no está listo (%s)", e)
            problems.append("Ollama")

    async def load_stt() -> WhisperServer:
        stt = WhisperServer(
            whisper_server_path(settings),
            settings.stt.model,
            language=settings.stt.language,
            gpu=settings.stt.gpu,
        )
        await stt.start()
        return stt

    async def load_tts() -> KokoroTTS:
        tts = KokoroTTS(
            MODELS["tts-model"].path(),
            MODELS["tts-voices"].path(),
            voice=settings.tts.voice,
            speed=settings.tts.speed,
            lang=settings.tts.lang,
        )
        await tts.load()
        return tts

    async def load_vad() -> SileroVAD:
        return await asyncio.to_thread(SileroVAD, MODELS["vad"].path())

    async def load_wake() -> VoskWakeWord:
        return await asyncio.to_thread(VoskWakeWord, MODELS["wake"].path(), settings.wake.word)

    async def nothing() -> None:
        return None

    use_wake = voice and settings.wake.enabled
    _, stt, tts, vad, wake = await asyncio.gather(
        load_llm(),
        _attempt("Transcripción (whisper)", problems, load_stt) if voice else nothing(),
        _attempt("Voz (Kokoro)", problems, load_tts) if settings.tts.enabled else nothing(),
        _attempt("Detección de voz (Silero)", problems, load_vad) if voice else nothing(),
        _attempt("Activación (Vosk)", problems, load_wake) if use_wake else nothing(),
    )

    capture: AudioCapture | None = None
    if stt is not None and vad is not None:

        async def open_mic() -> AudioCapture:
            mic = AudioCapture(settings.audio.input_device, prebuffer_s=2.0)
            mic.start()
            return mic

        capture = await _attempt("Micrófono", problems, open_mic)

    player = Player(tts.sample_rate, settings.audio.output_device) if tts is not None else None

    # Caché del sistema: la de disco al instante; el escaneo, en segundo plano. La primera
    # vez (caché vacía) se espera al escaneo (~1,5 s) para que «abre X» funcione desde ya.
    index = SystemIndex.open()
    if len(index) == 0:
        await index.refresh()
    executor = Executor(default_registry(), ToolContext(index=index, settings=settings))
    pipeline = Pipeline(
        bus,
        brain,
        listen=settings.listen,
        wake_prebuffer_s=settings.wake.prebuffer_s,
        speak_typed=settings.responses.speak_typed,
        capture=capture,
        wake=wake,
        vad=vad if capture is not None else None,
        stt=stt if capture is not None else None,
        tts=tts,
        player=player,
        router=lambda text: route(text, index),
        executor=executor,
    )
    log.info(
        "Servicios listos en %.1f s (voz: %s, activación: %s, respuesta hablada: %s)",
        time.perf_counter() - t0,
        "sí" if pipeline.voice_enabled else "no",
        "sí" if wake is not None else "no",
        "sí" if tts is not None else "no",
    )
    services = Services(pipeline, llm, stt, index, start_watcher(index))
    if index.needs_scan():
        task = asyncio.create_task(index.refresh(), name="index-scan")
        services.background.add(task)
        task.add_done_callback(services.background.discard)
    if problems:
        services.notice = asyncio.create_task(_notice(bus, problems), name="startup-notice")
    return services


def start_watcher(index: SystemIndex) -> IndexWatcher | None:
    """Reescanea al instalar apps o crear carpetas. Si no se puede vigilar, no es grave."""
    watcher = IndexWatcher(index.refresh)
    try:
        recursive = start_menu_dirs()
        if (steam := steam_root()) is not None:
            recursive.append(steam / "steamapps")
        watcher.start(recursive=recursive, shallow=list(known_folders().values()))
    except Exception:
        log.warning("No se pueden vigilar los cambios de apps y carpetas", exc_info=True)
        return None
    return watcher


async def _notice(bus: EventBus, problems: list[str]) -> None:
    await asyncio.sleep(NOTICE_DELAY_S)
    await bus.publish(BubbleShown(display="Nyx funciona a medias", secondary=", ".join(problems)))
    await asyncio.sleep(NOTICE_S)
    await bus.publish(BubbleHidden())
