"""Arranque de los servicios de voz a partir de los ajustes.

Todo se carga en paralelo (objetivo: listo en menos de 10 s). Si una pieza falla, Nyx sigue
con lo que tenga y lo avisa una vez (SPEC sección 2): sin whisper o sin micrófono queda la
entrada por texto; sin voz, las respuestas solo salen en la burbuja.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nyx.alarms.ringer import AlarmRinger
from nyx.alarms.scheduler import AlarmScheduler
from nyx.alarms.store import AlarmStore
from nyx.audio.capture import AudioCapture
from nyx.audio.playback import Player
from nyx.audio.vad import SileroVAD
from nyx.brain.answers import Answers
from nyx.brain.base import ChatMessage, LLMError
from nyx.brain.ollama import OllamaEngine, launch_ollama
from nyx.brain.panel import tidy
from nyx.brain.phrases import PhraseBook
from nyx.brain.router import refusal, route, written_command
from nyx.brain.select import ToolSelector, tools_budget
from nyx.brain.service import Brain
from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import (
    BubbleHidden,
    BubbleShown,
    CoreRestart,
    OpenSettingsWindow,
    SettingsChanged,
    SettingsRequested,
    SetupFlowRequested,
)
from nyx.executor import Executor
from nyx.ext import revocation
from nyx.ext.api import ExtensionApi, LlmAsker, ToolRunner
from nyx.ext.api import forget as forget_credentials
from nyx.ext.host import ExtensionHost
from nyx.ext.manager import ExtensionManager
from nyx.ext.rpc import RpcError
from nyx.ext.sandbox import SandboxLauncher, delete_container
from nyx.ext.service import ExtensionsService
from nyx.ext.store import ExtensionStore
from nyx.ext.tools import make_tools
from nyx.game.brain import GameBrain
from nyx.game.controller import GameController
from nyx.game.detector import GameDetector, GameStateChanged
from nyx.game.policy import GameGate
from nyx.index.model import Kind
from nyx.index.scanners.apps import start_menu_dirs
from nyx.index.scanners.folders import known_folders
from nyx.index.scanners.games import steam_root
from nyx.index.service import SystemIndex
from nyx.index.watcher import IndexWatcher
from nyx.models import MODELS
from nyx.organizer.calendar import schedule_reminders
from nyx.organizer.store import OrganizerStore
from nyx.paths import local_dir
from nyx.pipeline import Pipeline
from nyx.safety.action_log import ActionLog
from nyx.safety.paths import PathPolicy
from nyx.settings.live import apply_patch
from nyx.settings.model import Settings
from nyx.stt.whisper_server import WhisperServer
from nyx.tools.base import ToolContext
from nyx.tools.hide_apps import restore_hidden
from nyx.tools.registry import ToolRegistry, default_registry
from nyx.tts.base import TTSEngine
from nyx.tts.piper import PiperTTS
from nyx.tts.pocket import PocketTTS
from nyx.tts.voices import Engine, voice_for
from nyx.update.coordinator import UpdateCoordinator
from nyx.update.moment import UpdateGate
from nyx.usage.sender import UsageSender
from nyx.usage.stats import STATS
from nyx.wake.activations import ActivationLog
from nyx.wake.base import WakeWordEngine
from nyx.wake.custom import WakePhrase, validate, vosk_vocabulary
from nyx.wake.own_engine import OWN_MODEL, OwnWakeWord, threshold_for
from nyx.wake.vosk_engine import VoskWakeWord, VoskYesNo

log = logging.getLogger(__name__)

NOTICE_DELAY_S = 3.0  # da tiempo a que la interfaz se conecte antes de avisar
NOTICE_S = 8.0


def whisper_server_path(settings: Settings) -> Path:
    r"""El de los ajustes; si no, el que va con Nyx empaquetado (9.07: `core\bin\whisper`
    junto a su Python); si no, en %LOCALAPPDATA%\Nyx\whisper."""
    if settings.stt.server is not None:
        return settings.stt.server
    packaged = Path(sys.prefix).parent / "bin" / "whisper" / "whisper-server.exe"
    if packaged.is_file():
        return packaged
    return local_dir() / "whisper" / "whisper-server.exe"


class Services:
    def __init__(
        self,
        pipeline: Pipeline,
        llm: OllamaEngine,
        stt: WhisperServer | None,
        index: SystemIndex,
        watcher: IndexWatcher | None,
        alarms: AlarmScheduler | None = None,
        ringer: AlarmRinger | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.alarms = alarms
        self.ringer = ringer
        self.alarms_start: asyncio.Task[None] | None = None
        self.game_detector: GameDetector | None = None
        self.game_controller: GameController | None = None
        self.llm = llm
        self.stt = stt
        self.index = index
        self.watcher = watcher
        self.notice: asyncio.Task[None] | None = None
        self.background: set[asyncio.Task[Any]] = set()
        self.extensions: ExtensionManager | None = None
        self.extensions_service: ExtensionsService | None = None
        # ¿Buen momento para actualizar? (SPEC §15; lo pregunta la app con Velopack, 9.06)
        self.update_gate = UpdateGate()
        # Cuándo se aplica una versión descargada (9.06); «Nyx, actualízate» (nyx_update).
        self.updates: UpdateCoordinator | None = None
        # Datos de uso anónimos (SPEC §8): solo con permiso y si esta versión trae a dónde.
        self.usage: UsageSender | None = None

    async def close(self) -> None:
        # Lo oculto con «oculta X del todo» (8.08) nunca se queda oculto sin Nyx.
        await asyncio.to_thread(restore_hidden)
        if self.usage is not None:
            await self.usage.close()
        if self.updates is not None:
            self.updates.close()
        if self.notice is not None:
            self.notice.cancel()
        if self.extensions_service is not None:
            self.extensions_service.close()
        if self.alarms_start is not None:
            self.alarms_start.cancel()
        if self.alarms is not None:
            await self.alarms.close()
            self.alarms.store.close()
        if self.ringer is not None:
            await self.ringer.close()
        if self.game_detector is not None:
            await self.game_detector.close()
        if self.game_controller is not None:
            await self.game_controller.close()
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


async def _attempt[T](
    name: str, key: str, problems: list[str], load: Callable[[], Awaitable[T]]
) -> T | None:
    """Carga una pieza; si falla, lo apunta con su clave (ver `startup_notice`)."""
    try:
        return await load()
    except Exception as e:
        log.warning("%s no disponible: %s", name, e, exc_info=log.isEnabledFor(logging.DEBUG))
        problems.append(key)
        return None


def _tool_runner(registry: ToolRegistry, ctx: ToolContext) -> ToolRunner:
    """Las herramientas propias de Nyx para la API de extensiones (apps, sonido, ventanas).
    Nunca las de otra extensión: solo las que no tienen dueño en el registro."""

    async def run(name: str, args: dict[str, Any]) -> tuple[bool, str]:
        tool = registry.get(name)
        if tool is None or registry.owner_of(name) is not None:
            return False, "no está disponible"
        try:
            params = tool.params_model.model_validate(args)
        except ValidationError:
            return False, "datos no válidos"
        try:
            result = await asyncio.wait_for(tool.run(params, ctx), tool.timeout_s)
        except TimeoutError:
            return False, "ha tardado demasiado"
        return result.ok, result.message

    return run


def _llm_asker(brain: Brain) -> LlmAsker:
    """`llm.ask` de las extensiones: una pregunta suelta al modelo de Nyx, sin herramientas
    ni la memoria de la conversación (no ve nada del usuario)."""

    async def ask(system: str, prompt: str) -> str:
        messages = [ChatMessage("system", system)] if system else []
        messages.append(ChatMessage("user", prompt))
        out = ""
        try:
            async for piece in brain.llm.stream(messages):
                out += piece
        except LLMError as e:
            raise RpcError("el modelo no está disponible ahora") from e
        return out.strip()

    return ask


def _extensions(
    bus: EventBus,
    registry: ToolRegistry,
    brain: Brain,
    game: GameGate,
    settings: Settings,
    tools_ctx: ToolContext,
) -> ExtensionManager:
    """Extensiones (0.7): se cargan y se quitan en marcha. Al cambiar las herramientas, selector
    nuevo y el modelo se recalienta; nunca en partida (espera a que acabe)."""

    async def apply_selector(selector: ToolSelector) -> None:
        brain.selector = selector
        try:
            await brain.warmup()
        except LLMError as e:
            log.warning("No se pudo recalentar el modelo tras cambiar las extensiones: %s", e)

    store = ExtensionStore()

    def accepted(ext_id: str) -> tuple[str, ...]:
        ext = next((e for e in store.installed() if e.id == ext_id), None)
        return tuple(ext.state.accepted) if ext is not None and ext.active else ()

    def settings_of(ext_id: str) -> tuple[str, ...]:
        ext = store.get(ext_id)
        return tuple(s.key for s in ext.manifest.settings) if ext is not None else ()

    # Extensiones con código (7.06–7.07): encerradas, y lo que pidan, con su permiso.
    api = ExtensionApi(
        bus,
        accepted,
        settings_of=settings_of,
        playing=lambda: game.active,
        run_tool=_tool_runner(registry, tools_ctx),
        ask_llm=_llm_asker(brain),
    )

    async def disabled(ext_id: str, reason: str) -> None:
        log.warning("Extensión %s desactivada: %s", ext_id, reason)
        await manager.set_enabled(ext_id, False)
        await bus.publish(
            BubbleShown(display="He desactivado una extensión", secondary=reason[:120], alert=True)
        )

    host = ExtensionHost(SandboxLauncher(), on_disabled=disabled, handlers=api.handlers)

    async def stopped(ext_id: str, removed: bool) -> None:
        await host.stop(ext_id)
        await api.close(ext_id)
        if removed:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(delete_container, ext_id)
            # Sus claves y ajustes no se quedan en el Administrador de credenciales.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(forget_credentials, ext_id)

    manager = ExtensionManager(
        store,
        registry,
        budget_chars=tools_budget(settings.llm.num_ctx),
        apply_selector=apply_selector,
        playing=lambda: game.active,
        tool_factory=lambda ext: make_tools(ext, host),
        on_stopped=stopped,
    )

    async def on_game(event: GameStateChanged) -> None:
        host.set_game(event.active)
        if not event.active:
            await manager.game_ended()

    bus.subscribe(GameStateChanged, on_game)
    manager.set_revocations(revocation.load_cached())
    return manager


async def _revocations(manager: ExtensionManager) -> None:
    """Lista de revocación (7.08): una vez al día, solo con alguna extensión firmada."""
    import httpx

    while True:
        signed = [e for e in manager.store.installed() if not e.state.dev]
        if signed and revocation.due():
            async with httpx.AsyncClient(follow_redirects=False) as client:
                fresh = await revocation.refresh(client)
            if fresh != manager.revocations:
                manager.set_revocations(fresh)
                await manager.reload()
        await asyncio.sleep(3600)


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

    registry = default_registry()
    # Si las herramientas no caben en su parte del contexto, se rotan por grupos (6.20b).
    selector = ToolSelector(registry, budget_chars=tools_budget(settings.llm.num_ctx))
    brain = Brain(llm, tone=settings.responses.tone, selector=selector)

    async def load_llm() -> None:
        try:
            await brain.warmup()
        except LLMError as e:
            # No es fatal: Ollama puede abrirse después. Cada petición lo vuelve a intentar.
            log.warning("Ollama no está listo (%s)", e)
            problems.append("llm")

    async def load_stt() -> WhisperServer:
        stt = WhisperServer(
            whisper_server_path(settings),
            settings.stt.model,
            language=settings.stt.language,
            gpu=settings.stt.gpu,
        )
        await stt.start()
        return stt

    async def load_tts() -> TTSEngine:
        voice = voice_for(settings.tts.voice)
        if voice.id != settings.tts.voice:
            log.warning("No existe la voz %r: uso %s", settings.tts.voice, voice.label)
        tts: TTSEngine
        if voice.engine is Engine.POCKET:
            tts = PocketTTS(voice.name, speed=settings.tts.speed)
        else:
            tts = PiperTTS(
                MODELS[voice.model].path(),
                MODELS[voice.config].path(),
                speaker=voice.speaker,
                speed=settings.tts.speed,
            )
        await tts.load()
        return tts

    async def load_vad() -> SileroVAD:
        return await asyncio.to_thread(SileroVAD, MODELS["vad"].path())

    vosk_model: Any = None  # modelo de Vosk, también para el «sí / no» por voz
    wake_phrase = WakePhrase()  # «Nyx», salvo palabra personalizada válida

    async def load_wake() -> WakeWordEngine:
        vosk = await asyncio.to_thread(VoskWakeWord, MODELS["wake"].path(), settings.wake.word)
        nonlocal vosk_model, wake_phrase
        vosk_model = vosk.model  # el «sí / no» por voz sigue con Vosk
        if custom := settings.wake.custom_word.strip():
            check = validate(custom, vosk_vocabulary(vosk.model))
            if check.ok:
                wake_phrase = WakePhrase.custom(custom)
                log.info("Palabra personalizada: «%s» %s", custom, check.warnings or "")
                return await asyncio.to_thread(VoskWakeWord, MODELS["wake"].path(), custom)
            log.warning("Palabra «%s» no válida: %s", custom, "; ".join(check.problems))
            problems.append(f"wake_word:{custom}")
        if settings.wake.engine == "vosk":
            return vosk
        try:
            return await asyncio.to_thread(own_wake_word, settings)
        except Exception:
            log.warning("No se pudo cargar el detector propio: se usa Vosk", exc_info=True)
            return vosk

    async def nothing() -> None:
        return None

    use_wake = voice and settings.wake.enabled
    _, stt, tts, vad, wake = await asyncio.gather(
        load_llm(),
        _attempt("Transcripción (whisper)", "hear", problems, load_stt) if voice else nothing(),
        _attempt("Voz", "tts", problems, load_tts) if settings.tts.enabled else nothing(),
        _attempt("Detección de voz (Silero)", "hear", problems, load_vad) if voice else nothing(),
        _attempt("Activación", "wake", problems, load_wake) if use_wake else nothing(),
    )

    capture: AudioCapture | None = None
    if stt is not None and vad is not None:

        async def open_mic() -> AudioCapture:
            mic = AudioCapture(settings.audio.input_device, prebuffer_s=2.0)
            mic.start()
            return mic

        capture = await _attempt("Micrófono", "mic", problems, open_mic)

    player = Player(tts.sample_rate, settings.audio.output_device) if tts is not None else None

    # Caché del sistema: la de disco al instante; el escaneo, en segundo plano. La primera
    # vez (caché vacía) se espera al escaneo (~1,5 s) para que «abre X» funcione desde ya.
    index = SystemIndex.open()
    # Sin apps también se espera: una versión anterior podía guardar la caché sin ellas.
    if len(index) == 0 or not index.entries({Kind.APP}):
        await index.refresh()
    # Rutas protegidas (SPEC sección 8): sistema, Nyx y las carpetas principales del usuario.
    paths = PathPolicy.default(list(known_folders().values()))
    alarms = AlarmScheduler(AlarmStore.default(), bus)

    async def open_nyx_settings(section: str | None) -> None:
        await bus.publish(OpenSettingsWindow(section))

    async def close_nyx_settings() -> None:
        await bus.publish(OpenSettingsWindow(close=True))

    async def restart_nyx() -> None:
        await bus.publish(CoreRestart())

    async def open_nyx_panel(mode: str) -> None:
        await bus.publish(SetupFlowRequested("start", mode))

    async def apply_settings(patch: dict[str, Any]) -> list[str]:
        restart = apply_patch(settings, patch)
        # La ventana de Ajustes y las demás se enteran (como si se cambiara desde Ajustes).
        await bus.publish(SettingsRequested())
        return restart

    tools_ctx = ToolContext(
        index=index,
        settings=settings,
        paths=paths,
        alarms=alarms,
        organizer=OrganizerStore.default(),
        open_nyx_settings=open_nyx_settings,
        close_nyx_settings=close_nyx_settings,
        restart_nyx=restart_nyx,
        apply_settings=apply_settings,
        open_nyx_panel=open_nyx_panel,
    )
    ringer = AlarmRinger(bus, tts=tts, player=player)
    # Modo partida (SPEC sección 9): qué herramientas se permiten, se difieren o se bloquean.
    game = GameGate(settings.game, path=local_dir() / "game-queue.json")
    game.load()
    tools_ctx.game = game
    phrases = PhraseBook()
    executor = Executor(
        registry, tools_ctx, action_log=ActionLog.default(), game=game, phrases=phrases
    )
    # Registro de activaciones; los errores apuntados suben el umbral del detector propio.
    activations = ActivationLog.default()
    activations.save_clips = settings.wake.save_false_clips
    if isinstance(wake, OwnWakeWord):
        wake.threshold = min(0.95, wake.threshold + activations.offset)
    # «Sí» / «no» por voz con el mismo modelo de Vosk que la activación.
    yesno = VoskYesNo(vosk_model) if vosk_model is not None else None
    # Órdenes que el LLM escribe como texto («pon el volumen al 100»): al router (6.21).
    brain.reroute = lambda text: written_command(text, index, playing=game.active)
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
        refuse=lambda text: refusal(text, index, playing=game.active),
        executor=executor,
        yesno=yesno,
        ringer=ringer,
        shortcuts=ShortcutStore.default(),
        activations=activations,
        wake_phrase=wake_phrase,
        game=game,
        phrases=phrases,
        answers=Answers(settings.responses.tone),
    )
    log.info(
        "Servicios listos en %.1f s (voz: %s, activación: %s, respuesta hablada: %s)",
        time.perf_counter() - t0,
        "sí" if pipeline.voice_enabled else "no",
        "sí" if wake is not None else "no",
        "sí" if tts is not None else "no",
    )

    # «Responder también en voz a lo escrito» se cambia al momento desde Ajustes.
    async def on_settings(_: SettingsChanged) -> None:
        pipeline.speak_typed = settings.responses.speak_typed

    bus.subscribe(SettingsChanged, on_settings)
    services = Services(
        pipeline, llm, stt, index, start_watcher(index), alarms=alarms, ringer=ringer
    )
    # Si Nyx se cerró de golpe con apps ocultas (8.08), vuelven a verse.
    if restored := await asyncio.to_thread(restore_hidden):
        log.info("Ventanas ocultas devueltas al arrancar: %d", restored)
    services.alarms_start = asyncio.create_task(
        _start_alarms(alarms, tools_ctx.organizer), name="alarms-start"
    )
    services.game_controller = GameController(
        bus,
        game,
        executor,
        unload_llm=llm.unload,
        reload_llm=brain.warmup,
        brain=GameBrain(game, llm, brain.warmup),
    )
    services.extensions = _extensions(bus, registry, brain, game, settings, tools_ctx)
    services.extensions_service = ExtensionsService(bus, services.extensions, settings)
    services.update_gate.add("pipeline", pipeline.busy)
    services.update_gate.add("game", lambda: "hay una partida" if game.active else None)
    services.update_gate.add(
        "pending", lambda: "hay cosas pendientes para después de la partida" if game.queue else None
    )
    # Actualizaciones (9.06): la app avisa al descargarla; aquí se decide cuándo. Por voz,
    # «Nyx, actualízate» (herramienta nyx_update).
    services.updates = UpdateCoordinator(bus, settings, services.update_gate)
    tools_ctx.update_now = services.updates.by_voice
    services.usage = UsageSender(
        STATS, enabled=lambda: settings.privacy.usage_data, llm_model=lambda: settings.llm.model
    )
    services.usage.start()
    services.game_detector = GameDetector(
        bus,
        always=settings.game.always,
        never=settings.game.never,
        game_processes=lambda: {e.process for e in index.entries({Kind.GAME}) if e.process},
        mode=lambda: settings.game.mode,
    )
    await services.game_detector.start()
    if services.extensions.store.installed():
        # Solo si hay alguna: recargar recalienta el modelo con sus herramientas.
        await services.extensions.reload()
    revocations = asyncio.create_task(_revocations(services.extensions), name="ext-revocations")
    services.background.add(revocations)
    revocations.add_done_callback(services.background.discard)
    if index.needs_scan():
        task = asyncio.create_task(index.refresh(), name="index-scan")
        services.background.add(task)
        task.add_done_callback(services.background.discard)
    if problems:
        services.notice = asyncio.create_task(_notice(bus, problems), name="startup-notice")
    return services


def own_wake_word(settings: Settings) -> OwnWakeWord:
    """Detector propio de «Nyx» (fase 4) con la sensibilidad de los ajustes."""
    return OwnWakeWord(
        OWN_MODEL,
        MODELS["wake-melspec"].path(),
        MODELS["wake-embedding"].path(),
        threshold=threshold_for(settings.wake.sensitivity),
    )


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


async def _start_alarms(alarms: AlarmScheduler, organizer: OrganizerStore | None) -> None:
    # Tras dar tiempo a que la interfaz se conecte: el aviso de las alarmas que vencieron
    # con Nyx cerrado tiene que verse.
    await asyncio.sleep(NOTICE_DELAY_S)
    await alarms.start()
    # Calendario (8.02): los avisos de los próximos días, renovados cada hora (las citas que
    # se repiten cada semana o mes no caben en una sola alarma).
    while organizer is not None:
        try:
            # En el bucle (no en otro hilo): `alarms.add` avisa a su espera de asyncio.
            schedule_reminders(organizer, alarms)
        except Exception as e:
            log.warning("No se pudieron poner los avisos del calendario: %s", e)
        await asyncio.sleep(3600)


#: Lo que no funciona, dicho para cualquiera: qué pasa y qué puede hacer mientras tanto.
_EXPLAINED: dict[str, tuple[str, str]] = {
    "mic": (
        "No puedo oírte",
        "No encuentro el micrófono. Mientras, escríbeme con Win + Alt + N.",
    ),
    "hear": (
        "No puedo oírte",
        "Me falta una pieza para entender lo que dices. Mientras, escríbeme con Win + Alt + N.",
    ),
    "wake": ("No respondo a «Nyx»", "Para hablarme, pulsa Win + Alt + H."),
    "tts": ("No puedo hablar", "Te respondo por escrito."),
    "llm": ("Aún no puedo pensar", "Ollama no está abierto: de momento solo hago cosas sencillas."),
}


def startup_notice(problems: list[str]) -> tuple[str, str] | None:
    """Aviso de arranque (título y explicación) a partir de lo que ha fallado.

    Breve y sin nombres técnicos (salvo Ollama, que el usuario tiene que abrir). Si no puede
    oír, no se dice además que no responde a «Nyx»: ya está dicho.
    """
    keys = list(dict.fromkeys(problems))  # sin repetidos, en orden
    deaf = "mic" in keys or "hear" in keys
    lines: list[tuple[str, str]] = []
    if deaf:
        lines.append(_EXPLAINED["mic" if "mic" in keys else "hear"])
    for key in keys:
        if key.startswith("wake_word:") and not deaf:
            word = key.removeprefix("wake_word:")
            lines.append((f"No respondo a «{word}»", "Esa palabra no me sirve: respondo a «Nyx»."))
        elif key == "wake" and not deaf:
            lines.append(_EXPLAINED["wake"])
        elif key in ("tts", "llm"):
            lines.append(_EXPLAINED[key])
    if not lines:
        return None
    if len(lines) == 1:
        return lines[0]
    return "Funciono a medias", "\n".join(f"{title}. {detail}" for title, detail in lines)


async def _notice(bus: EventBus, problems: list[str]) -> None:
    notice = startup_notice(problems)
    if notice is None:
        return
    await asyncio.sleep(NOTICE_DELAY_S)
    display, secondary = tidy(*notice)
    await bus.publish(BubbleShown(display=display, secondary=secondary))
    # Con varias cosas que leer, se deja un poco más.
    await asyncio.sleep(NOTICE_S + 3 * secondary.count("\n"))
    await bus.publish(BubbleHidden())
