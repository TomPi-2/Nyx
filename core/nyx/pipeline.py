"""Bucle de voz (SPEC sección 3): activación → escucha → transcripción → LLM → voz y burbuja.

Una sola petición a la vez: una nueva (voz, texto o atajo) cancela la que esté en curso.
Cada petición lleva su ID en el registro y una línea con su latencia
(fin de la frase → primera palabra hablada, objetivo < 1,5 s).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

import numpy as np

from nyx.alarms.ringer import AlarmRinger
from nyx.audio.capture import AudioCapture, Frame, rms_level
from nyx.audio.playback import Player
from nyx.audio.vad import Endpointer, EndReason, VoiceDetector
from nyx.brain.agent import MAX_SECONDS, MAX_STEPS, AgentRun, continuation_hint, memory_note
from nyx.brain.answers import Answers
from nyx.brain.base import LLMError
from nyx.brain.guard import looks_like_code, mentions_tool, tool_keys
from nyx.brain.longform import (
    LongAnswer,
    PanelCommand,
    is_long,
    panel_command,
    panel_title,
    sentence_count,
    spoken_summary,
    structure,
    to_answer,
    wants_structure,
)
from nyx.brain.panel import tidy
from nyx.brain.phrases import PhraseBook
from nyx.brain.reply import BubbleReady, Reply, SpokenDelta, SpokenEnd, first_sentence
from nyx.brain.router import IN_GAME_REFUSAL, Miss, Route
from nyx.brain.service import Brain, ReplyDone, ToolPlan
from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import (
    ActionChosen,
    Announce,
    AudioLevel,
    BubbleAction,
    BubbleHidden,
    BubbleKind,
    BubbleShown,
    LongSection,
    NyxState,
    PanelNote,
    ReadingAppended,
    StateChanged,
    TalkKey,
    TextEntered,
)
from nyx.executor import Confirmation, Executor, ToolCall, fix_enums, with_waits
from nyx.game.policy import GameGate
from nyx.index.aliases import normalize as normalize_alias
from nyx.log import new_request_id
from nyx.safety.undo import UNDO_TTL_S
from nyx.settings.model import ListenSettings
from nyx.stt.base import STTEngine, STTError
from nyx.stt.normalize import addressed_by_name, is_echo, looks_foreign, normalize
from nyx.tools.base import GamePolicy, ToolResult
from nyx.tools.clipboard import write_clipboard_text
from nyx.tts.base import TTSEngine, TTSError
from nyx.tts.sentences import SentenceSplitter
from nyx.wake.activations import ActivationLog, is_not_for_you
from nyx.wake.base import WakeWordEngine
from nyx.wake.custom import WakePhrase
from nyx.winapi import windows

log = logging.getLogger(__name__)

# Vocabulario para Whisper: mejora la transcripción de «Nyx» (fase 3: apps y carpetas de la caché).
STT_PROMPT = "Nyx."
#: Primer arranque: si no dices nada en este rato, vuelve a escuchar (mientras dure).
SETUP_LISTEN_S = 30.0
# Acciones del router: «pensando» solo si tardan (las rápidas no dividen la forma). Las
# peticiones al LLM pasan a «pensando» al momento (_respond).
THINKING_AFTER_S = 0.3
HOLD_S = 0.4  # mantener el atajo más que esto = hablar mientras se mantiene
TALK_PREBUFFER_S = 0.3
VERIFY_CLIP_S = 2.0  # audio que whisper revisa para confirmar «Nyx»
# Herramientas tras las que el LLM sigue sin herramientas: lo leído de fuera no manda (6.06).
TOOLS_OFF_AFTER = frozenset({"web_search"})
# Panel largo (6.28): botones, cuánto vale un «sí» suelto tras ofrecer guardar la receta y
# desde cuánto texto encontrado merece la pena pedir la estructura (receta, pasos, lista).
LONG_ACTIONS = (
    BubbleAction("long-save", "Guardar en una nota", primary=True),
    BubbleAction("long-copy", "Copiar"),
    BubbleAction("long-close", "Cerrar"),
)
OFFER_S = 120.0
STRUCTURE_MIN_CHARS = 400
THRESHOLD_CHECK_S = 60.0  # cada cuánto se mira si la subida automática del umbral ha bajado
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


# Primeras palabras que marcan una orden para Nyx en la ventana de seguimiento.
_COMMAND_WORDS = (
    "abre", "cierra", "pon", "quita", "sube", "baja", "pausa", "para", "reanuda", "sigue",
    "vuelve", "busca", "mueve", "copia", "borra", "dime", "repite", "cambia", "maximiza",
    "minimiza", "silencia", "apaga", "enciende", "crea", "guarda", "haz", "pasa", "salta",
    "otra", "siguiente", "anterior", "deshaz", "recupera", "avisame", "recuerdame",
)  # fmt: skip
COMMAND_VERBS = frozenset(_COMMAND_WORDS)
# Imperativo con pronombre pegado: «reanúdalo», «súbela», «ciérralos», «pásamelo».
_IMPERATIVE_CLITIC = re.compile(r"^[a-z]{3,}(?:melo|mela|selo|sela|lo|la|los|las|le|les)$")


def norm_words(text: str) -> list[str]:
    from nyx.index.aliases import normalize as plain

    return plain(text).split()


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
    """Sintetiza frases en orden mientras suenan las anteriores.

    `on_sentence(texto, duración)` (6.28): se llama cuando cada frase empieza a sonar, con lo
    que dura su audio, para que el panel largo la escriba a ese ritmo. Si la frase ya había
    empezado (la primera suena mientras se genera), con lo que le queda."""

    def __init__(
        self,
        tts: TTSEngine,
        player: Player,
        on_start: Callable[[], Awaitable[None]],
        on_sentence: Callable[[str, float], Awaitable[None]] | None = None,
    ) -> None:
        self._tts = tts
        self._player = player
        self._on_start = on_start
        self._on_sentence = on_sentence
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.started = False
        self._announcing: set[asyncio.Task[None]] = set()
        self._task = asyncio.create_task(self._worker(), name="tts")

    def say(self, text: str) -> None:
        if not self.started and self._queue.empty():
            self._player.prepare()
        self._queue.put_nowait(text)

    async def _worker(self) -> None:
        loop = asyncio.get_running_loop()
        while (text := await self._queue.get()) is not None:
            starts_at: float | None = None
            samples = 0
            try:
                # Cada trozo suena en cuanto se genera (Pocket: el primero en ~0,08 s).
                async for audio in self._tts.stream(text):
                    if not self.started:
                        self.started = True
                        await self._on_start()
                    if starts_at is None:
                        starts_at = loop.time() + getattr(self._player, "queued_s", 0.0)
                    self._player.enqueue(audio)
                    samples += audio.shape[0]
            except TTSError:
                log.exception("Fallo de la voz con %r", text)
            if self._on_sentence is not None and starts_at is not None and samples:
                rate = self._tts.sample_rate or 1
                self._announce(text, starts_at, samples / rate)

    def _announce(self, text: str, starts_at: float, duration: float) -> None:
        assert self._on_sentence is not None
        on_sentence = self._on_sentence

        async def at_start() -> None:
            delay = starts_at - asyncio.get_running_loop().time()
            if delay > 0:
                await asyncio.sleep(delay)
            await on_sentence(text, max(0.2, duration + min(0.0, delay)))

        task = asyncio.create_task(at_start(), name="tts-sentence")
        self._announcing.add(task)
        task.add_done_callback(self._announcing.discard)

    async def finish(self) -> None:
        self._queue.put_nowait(None)
        await self._task
        if self.started:
            await self._player.drain()
        # La última frase ya ha sonado: su aviso tiene que haber salido.
        if self._announcing:
            await asyncio.gather(*self._announcing, return_exceptions=True)

    async def abort(self, *, fade: bool = False) -> None:
        """Para de hablar. `fade`: con un fundido de 150 ms en vez de cortar en seco."""
        self._task.cancel()
        for task in self._announcing:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        if fade:
            self._player.fade_out()
        else:
            self._player.clear()


class SetupHook(Protocol):
    """El primer arranque guiado (setup/flow.py): mientras está en marcha, lo que se oye o
    se escribe es para él, no para el router ni el cerebro."""

    active: bool

    @property
    def prompt(self) -> str:
        """Pista para whisper con las palabras que espera (los nombres de los colores…)."""
        ...

    def understands(self, text: str) -> bool: ...
    def wants(self, text: str) -> bool: ...
    async def dismiss(self) -> None: ...
    async def hear(self, text: str) -> bool: ...
    async def on_wake(self) -> None: ...


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
        refuse: Callable[[str], tuple[str, str] | None] | None = None,
        activations: ActivationLog | None = None,
        wake_phrase: WakePhrase | None = None,
        game: GameGate | None = None,
        phrases: PhraseBook | None = None,
        answers: Answers | None = None,
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
        self.refuse = refuse
        self.activations = activations
        self.wake_phrase = wake_phrase or WakePhrase()  # «Nyx» o la palabra personalizada
        self.game = game
        self.phrases = phrases or PhraseBook()
        # Respuestas habladas con variantes según el tono (6.26).
        self.answers = answers or Answers()
        # Umbral del detector sin el ajuste por errores (para recalcularlo al apuntar uno).
        threshold = getattr(wake, "threshold", None)
        offset = activations.offset if activations is not None else 0.0
        self._wake_threshold0 = threshold - offset if isinstance(threshold, float) else None
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
        self._agent = AgentRun()  # lo hecho en la petición en curso (bucle de agente, 6.01)
        self._wake_score: float | None = None  # del detector, al saltar (registro de activaciones)
        self._threshold_checked = time.time()
        self._side_tasks: set[asyncio.Task[None]] = set()
        self._barge: asyncio.Task[None] | None = None
        # Panel largo (6.28): lo que enseña, si sigue abierto y hasta cuándo un «sí» suelto
        # es «guárdamela» (solo tras ofrecerlo: recetas, pasos y listas).
        self._long: LongAnswer | None = None
        self._long_open = False
        self._offer_until = 0.0
        # Primer arranque guiado (9.10): lo pone main.py; `announce` y `hush` son su voz.
        self.setup: SetupHook | None = None
        self._announcing: asyncio.Task[None] | None = None
        self._announce_text = ""  # lo que está diciendo (para no tomar su voz por la tuya)
        if executor is not None and executor.confirm is None:
            executor.confirm = self.confirm
        self._unsubscribe = [
            bus.subscribe(TextEntered, self._on_text),
            bus.subscribe(TalkKey, self._on_talk),
            bus.subscribe(ActionChosen, self._on_action),
            bus.subscribe(Announce, self._on_announce),
            bus.subscribe(BubbleShown, self._on_any_bubble),
            bus.subscribe(BubbleHidden, self._on_any_bubble_hidden),
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

    def busy(self) -> str | None:
        """Por qué no es buen momento para reiniciar (actualizar), o None (SPEC §15)."""
        if self.state is not NyxState.IDLE:
            return "Nyx está atendiendo una petición"
        if self._actions:
            return "hay una confirmación o un deshacer en pantalla"
        return None

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
        if time.time() - self._threshold_checked >= THRESHOLD_CHECK_S:
            self._apply_threshold()  # la subida automática baja sola si no hay descartes
        if self.mode is Mode.LISTENING:
            await self._listen_frame(frame)
        elif (
            self.wake is not None
            and self.voice_enabled
            and not self._wake_off_in_game()
            and self.wake.process(frame)
        ):
            # La puntuación se guarda ya: tras la activación el detector se reinicia a 0 y el
            # registro apuntaba siempre 0,0.
            score = getattr(self.wake, "last_score", None)
            self._wake_score = score if isinstance(score, float) else None
            log.info(
                "Activación (%s)",
                f"{self._wake_score:.2f}" if self._wake_score is not None else "?",
            )
            clip = self.capture.prebuffer(VERIFY_CLIP_S) if self.capture is not None else []
            verifies = bool(clip) and self.stt is not None
            if self._announce_speaking():
                # Primer arranque: Nyx está hablando y el micrófono la oye. Solo se le corta si
                # whisper oye «Nyx» y no es lo que ella misma dice («¡Hola! Soy Nyx»).
                if verifies and (self._barge is None or self._barge.done()):
                    audio = np.concatenate(clip).astype(np.int16)
                    self._barge = asyncio.create_task(
                        self._announce_barge(audio), name="announce-barge"
                    )
                return
            if self.mode is Mode.BUSY and verifies:
                # Nyx está pensando o hablando: solo se le interrumpe si whisper confirma
                # «Nyx». Antes se cortaba al momento y, si era un falso aviso, la respuesta
                # se perdía y la forma desaparecía.
                if self._barge is None or self._barge.done():
                    audio = np.concatenate(clip).astype(np.int16)
                    self._barge = asyncio.create_task(self._barge_in(audio), name="barge-in")
                return
            if not verifies:
                self._record_activation(None, "")
            await self.start_listening(self.wake_prebuffer_s, show=not verifies)
            if self._listening is not None and clip:
                self._listening.verify = asyncio.create_task(
                    self._verify_wake(np.concatenate(clip).astype(np.int16)), name="verify"
                )

    async def _barge_in(self, clip: Any) -> None:
        """«Nyx» mientras Nyx piensa o habla: se confirma con whisper antes de cortar."""
        assert self.stt is not None
        try:
            text = await self.stt.transcribe(clip, prompt=STT_PROMPT)
        except STTError:
            return
        ok = self.wake_phrase.heard(text)
        log.info("Activación con Nyx ocupado: %r → %s", text, "interrumpe" if ok else "se ignora")
        self._record_activation(ok, text, clip)
        if ok and self.mode is Mode.BUSY:
            await self.start_listening(self.wake_prebuffer_s + VERIFY_CLIP_S / 2)

    async def _announce_barge(self, clip: Any) -> None:
        """«Nyx» mientras Nyx habla en el primer arranque: corta solo si no es su propio eco.
        No cuenta para la subida del umbral (sería su voz, no un falso aviso del detector)."""
        assert self.stt is not None
        spoken = self._announce_text
        try:
            text = await self.stt.transcribe(clip, prompt=STT_PROMPT)
        except STTError:
            return
        ok = self.wake_phrase.heard(text)
        echo = ok and is_echo(text, spoken)
        log.info(
            "Activación mientras Nyx habla: %r → %s",
            text,
            "su propia voz" if echo else "interrumpe" if ok else "se ignora",
        )
        if ok and not echo and self.mode is not Mode.LISTENING:
            await self.start_listening(self.wake_prebuffer_s + VERIFY_CLIP_S / 2)

    def _announce_speaking(self) -> bool:
        task = self._announcing
        return task is not None and not task.done()

    def _stt_prompt(self) -> str:
        """Con el primer arranque en marcha, la pista lleva las palabras del paso."""
        if self.setup is not None and self.setup.active:
            return self.setup.prompt
        return STT_PROMPT

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
            self._record_activation(None, "")
            if self._listening is not None and self.mode is Mode.LISTENING:
                await self._set_state(NyxState.LISTENING)
            return True
        ok = self.wake_phrase.heard(text)
        log.info("Verificación de «Nyx» (%d ms): %r → %s", _ms(self._clock() - t0), text, ok)
        self._record_activation(ok, text, clip)
        listening = self._listening
        if ok and listening is not None and self.mode is Mode.LISTENING:
            await self._set_state(NyxState.LISTENING)  # ahora sí: se enciende el indicador
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
        self,
        prebuffer_s: float = 0.0,
        *,
        followup: bool = False,
        manual: bool = False,
        show: bool = True,
        timeout_s: float | None = None,
    ) -> None:
        """`show=False`: se graba ya, pero el indicador espera a que whisper confirme «Nyx»
        (el detector propio salta más a menudo y whisper descarta casi todo). `timeout_s`:
        cuánto espera a que se empiece a hablar (por defecto, el de los ajustes)."""
        if followup and self._announce_speaking():
            # Lo dice el primer arranque o el panel suelto: escuchará él al acabar (si no, se
            # oiría a sí misma). Pasa al sacar el panel por voz (9.11).
            self.mode = Mode.IDLE
            return
        self.hush()  # si Nyx estaba diciendo algo del primer arranque, se calla al oírte
        self._drop_listening()
        await self._cancel_request()
        if self.vad is not None:
            self.vad.reset()
        frames = self.capture.prebuffer(prebuffer_s) if self.capture and prebuffer_s else []
        timeout = self.listen.followup_s if followup else self.listen.start_timeout_s
        if timeout_s is not None:
            timeout = timeout_s
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
        if show:
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
            raw = await self.stt.transcribe(audio, prompt=self._stt_prompt())
        except STTError:
            return
        listening.spec_text = raw
        if self._listening is listening and self._is_complete(raw):
            log.info("Petición completa tras una pausa: %r; dejo de escuchar", raw)
            await self._end_listening(EndReason.COMPLETE, transcript=raw)

    def _is_complete(self, raw: str) -> bool:
        """¿Es ya una petición entera? Una orden que el router entiende o una pregunta."""
        text = self.wake_phrase.without(normalize(raw))
        if not text:
            return False
        if self.setup is not None and self.setup.active and self.setup.understands(text):
            return True  # «siguiente», «coral»: no hay que esperar
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
            if listening.followup and self.setup is not None and self.setup.active:
                # Primer arranque: se le sigue escuchando sin «Nyx» hasta que acabe (un
                # «siguiente» tardío se perdía, ERRORES.md 2026-11-14).
                await self.start_listening(followup=True, timeout_s=SETUP_LISTEN_S)
                return
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
            p = self.phrases.pick("error_other")
            await self._fail(p.display, p.secondary, None)

    async def _cancel_request(self) -> None:
        task = self._request
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            # Un panel largo se queda (6.28): cortar la voz no es cerrar lo que se está leyendo,
            # y así «Nyx, ciérralo» le llega al panel y no cierra la última app.
            if not self._long_open:
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
                raw = await self.stt.transcribe(audio, prompt=self._stt_prompt())
            # Vale si whisper oyó «Nyx» en el fragmento corto o al principio de la frase.
            verified = verify is None or await verify or self.wake_phrase.heard(raw, first_words=3)
        except STTError:
            log.exception("Fallo al transcribir")
            p = self.phrases.pick("error_stt")
            await self._fail(p.display, p.secondary, None)
            return
        finally:
            thinking.cancel()
        marks.stt = self._clock()
        text = self.wake_phrase.without(normalize(raw))
        log.info("Transcripción (%d ms): %r → %r", _ms(marks.stt - marks.end), raw, text)
        if not verified:
            log.info("Activación descartada: whisper no ha oído «Nyx»")
            await self._go_idle()
            return
        if self.setup is not None and self.setup.active:
            # Primer arranque guiado: «Nyx» es la prueba de la activación y lo demás, una
            # respuesta a lo que ha preguntado (sin router ni cerebro). El panel suelto (9.11)
            # solo se queda con lo que entiende; lo demás se atiende como siempre.
            if verify is not None or self.wake_phrase.heard(raw, first_words=3):
                await self.setup.on_wake()
            if not text or looks_foreign(text) or self.setup.wants(text):
                await self._go_idle()
                if text and not looks_foreign(text):
                    await self.setup.hear(text)
                return
            await self.setup.dismiss()
        if not text:
            await self._go_idle()
            return
        # Con «Nyx, …» delante va a Nyx aunque sea en la ventana de seguimiento (ERRORES.md,
        # 2026-11-14: «Nix, ¿quién es tu creador?» se ignoraba).
        followup = listening is not None and listening.followup and not addressed_by_name(raw)
        if looks_foreign(text):
            # Mal oído (música o ruido): en seguimiento se ignora; si se llamó a Nyx, que lo
            # repita en vez de contestar a algo inventado.
            log.info("Transcripción en otro idioma: no se atiende (%r)", text)
            if followup:
                await self._go_idle()
            else:
                p = self.phrases.pick("not_understood")
                await self._fail(p.display, p.secondary, p.spoken)
            return
        # «Sí» tras ofrecer guardar la receta no es una coletilla: es la respuesta (6.28).
        if followup and is_filler(text) and self._panel_wants(text) is None:
            log.info("Seguimiento ignorado (coletilla): %r", text)
            await self._go_idle()
            return
        await self._handle_text(text, marks, from_voice=True, followup=followup)

    async def _thinking_later(self) -> None:
        await asyncio.sleep(THINKING_AFTER_S)
        # Una confirmación o una respuesta que ya está en marcha no se pisan.
        if self.state in (NyxState.LISTENING, NyxState.IDLE):
            await self._set_state(NyxState.THINKING)

    async def _handle_text(
        self, text: str, marks: _Marks, *, from_voice: bool, followup: bool = False
    ) -> None:
        """Router rápido primero (acciones sin LLM); si no encaja, el LLM."""
        marks.phrase = text
        self._agent = AgentRun()
        if self.setup is not None and self.setup.active:
            if self.setup.wants(text):
                await self._go_idle()
                await self.setup.hear(text)
                return
            await self.setup.dismiss()
        if self.ringer is not None and self.ringer.swallow(text):
            # «Nyx, para» con la alarma sonando: es para ella, no para la música.
            await self.ringer.stop()
            await self._hide_bubble()
            return
        if (command := self._panel_wants(text)) is not None:
            # Con un panel largo abierto, «ciérralo», «cópialo» o «guárdamela» son para él
            # (no para la última app o los últimos archivos).
            await self._panel(command, text, from_voice=from_voice)
            return
        if self.activations is not None and is_not_for_you(text):
            await self._false_activation(from_voice=from_voice)
            return
        if self.refuse is not None and (no := self.refuse(text)) is not None:
            # Lo que Nyx no hace nunca (vaciar la papelera, actuar dentro de un juego…).
            log.info("Negativa fija para %r: %s", text, no[0])
            spoken = f"{no[0]}." if from_voice or self.speak_typed else None
            await self._fail(no[0], no[1], spoken)
            return
        if (thanks := self.answers.thanks(text)) is not None:
            # «Gracias, Nyx»: se contesta sin el LLM, que alguna vez lo tomaba por una orden.
            log.info("Agradecimiento: %r", text)
            await self._show_bubble(thanks, "", spoken=thanks)
            self._schedule_bubble_hide(bubble_duration(thanks, ""))
            if from_voice or self.speak_typed:
                await self._say(thanks, marks)
            await self._go_idle()
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
        if (
            followup
            and not self._clearly_for_nyx(text)
            and (self._brain_off() or not await self.brain.addressed(text))
        ):
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
            steps = self.shortcuts.lookup_plan(text)
            if steps is not None:
                # 7.16: un plan que ya salió bien, sin el LLM y con los mismos riesgos.
                log.info("Plan aprendido: %r → %s", text, [(c.name, c.arguments) for c in steps])
                await self._act(
                    Route(with_waits(steps), "plan aprendido"), marks, from_voice=from_voice
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
            results = await self.executor.run_plan(
                routed.calls, phrase=marks.phrase, voice=from_voice
            )
        finally:
            thinking.cancel()
        log.info(
            "Latencia (acción, regla %s): fin de frase → hecho %d ms",
            routed.rule,
            _ms(self._clock() - marks.end),
        )
        speak = from_voice or self.speak_typed
        failed = next((r for r in results if not r.ok), None)
        self._agent.done += list(zip(routed.calls, results, strict=False))
        # Lo último que se hizo, con su ruta (6.02): «ábrela», «muévela», «ciérralo»…
        self.brain.remember_action(memory_note(self._agent.done))
        # Solo las reglas del router son preguntas concretas; un atajo aprendido o un plan del
        # LLM pueden venir de una pregunta más libre que la frase hecha no contesta.
        direct = routed.rule not in ("llm", "aprendido")
        if failed is None and await self._maybe_structured(routed.calls, results, marks):
            return results  # receta, pasos o lista: panel con formato y oferta de guardarla
        if failed is None and self._should_continue(routed.calls, marks, results, direct=direct):
            # Consultó algo (archivos, alarmas…): el resultado vuelve al LLM para contarlo o
            # para dar el siguiente paso (HOJA-DE-RUTA §3.1).
            self._agent.steps += 1
            hint = continuation_hint(self._agent)
            await self._respond(marks.phrase, marks, from_voice=from_voice, hint=hint)
            return results
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
        answer = " ".join(
            (self.answers.say(call.name, call.arguments, r) or r.message).strip()
            for call, r in zip(routed.calls, results, strict=False)
            if r.speak and r.message.strip()
        )
        if direct and answer and speak:
            # La respuesta ya está hecha (6.20a): se dice sin pasar por el LLM.
            await self._say(answer, marks)
        if from_voice and self.listen.followup_s > 0 and self.capture is not None:
            await self.start_listening(followup=True)
        else:
            await self._go_idle()
        return results

    def _clearly_for_nyx(self, text: str) -> bool:
        """Ventana de seguimiento: sin preguntar al clasificador, cuenta como dirigida a Nyx si
        dice «Nyx» en cualquier parte o empieza con una orden («reanúdalo», «súbelo», «pon…»).
        El clasificador ignoró «reanúdalo» (mal transcrito) y Nyx se fue mientras se le hablaba."""
        if self.wake_phrase.heard(text):
            return True
        # Las tres primeras palabras: «O sea, reanúdalo» también es una orden.
        return any(w in COMMAND_VERBS or _IMPERATIVE_CLITIC.match(w) for w in norm_words(text)[:3])

    def _wake_off_in_game(self) -> bool:
        """«Nyx en partida: desactivado»: solo el atajo de teclado (SPEC sección 9)."""
        return self.game is not None and self.game.active and self.game.mode == "off"

    def _record_activation(self, verified: bool | None, heard: str, clip: Any = None) -> None:
        if self.activations is None:
            return
        engine = type(self.wake).__name__ if self.wake is not None else "atajo"
        self.activations.record(engine, self._wake_score, verified, heard, clip)
        if verified is False:
            self._apply_threshold()

    def _apply_threshold(self) -> None:
        """Umbral del detector = el de la sensibilidad + errores apuntados + subida automática
        por descartes (6.22), que baja sola con el tiempo."""
        if self.activations is None or self.wake is None or self._wake_threshold0 is None:
            return
        self._threshold_checked = time.time()
        wanted = min(
            0.95,
            self._wake_threshold0 + self.activations.offset + self.activations.auto_offset(),
        )
        current = getattr(self.wake, "threshold", None)
        if isinstance(current, float) and abs(current - wanted) > 1e-6:
            log.info("Umbral de activación: %.2f → %.2f", current, wanted)
            self.wake.threshold = wanted  # type: ignore[attr-defined]

    async def _false_activation(self, *, from_voice: bool) -> None:
        """«Nyx, eso no era para ti»: la activación anterior fue un error (SPEC 4.7)."""
        assert self.activations is not None
        offset = self.activations.mark_previous_error()
        if offset is None:
            secondary = "no encuentro ninguna activación reciente"
        else:
            self._apply_threshold()
            secondary = "me costará un poco más activarme"
            log.info("Activación marcada como error: ajuste del umbral +%.2f", offset)
        await self._show_bubble("Vale, lo apunto", secondary)
        self._schedule_bubble_hide(NOTICE_BUBBLE_S)
        if from_voice and self.tts is not None and self.player is not None:
            with contextlib.suppress(TTSError):
                self.player.enqueue(await self.tts.synthesize("Vale, perdona."))
                await self.player.drain()
        await self._go_idle()

    def _learn(self, text: str, call: ToolCall) -> None:
        """SPEC sección 6: frase resuelta por el LLM con una sola acción → atajo."""
        if self.shortcuts is None or self.executor is None:
            return
        tool = self.executor.registry.get(call.name)
        key = self.shortcuts.learn(text, call, str(tool.risk) if tool else "red")
        if key is not None:
            self._learned_last = (key, self._clock())
            log.info("Atajo aprendido: %r → %s(%s)", key, call.name, call.arguments)

    def _learn_plan(self, text: str, calls: list[ToolCall]) -> None:
        """7.16: plan de varios pasos que ha salido bien → se repite sin LLM la próxima vez."""
        if self.shortcuts is None or self.executor is None:
            return
        risks = [
            str(tool.risk) if (tool := self.executor.registry.get(c.name)) else "red" for c in calls
        ]
        key = self.shortcuts.learn_plan(text, calls, risks)
        if key is not None:
            self._learned_last = (key, self._clock())
            log.info("Plan aprendido: %r → %s", key, [c.name for c in calls])

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
        if self.executor is not None:
            calls = fix_enums(calls, self.executor.registry)
        log.info("Plan del LLM: %s", [(c.name, c.arguments) for c in calls])
        if self._agent.steps and self._agent.repeats(calls):
            # Pide otra vez lo mismo: no avanza. Se enseña lo que ya se sabe.
            log.info("Bucle de agente: repite lo ya hecho; respondo con lo que hay")
            await self._show_known()
            return
        if not retried and self.executor is not None:
            # SPEC sección 6: si la llamada no es válida, se reintenta una vez con el error.
            invalid = self.executor.check(calls)
            if invalid and self._blocked_in_game(calls):
                # Pedía actuar dentro del juego: reintentar solo hace que el modelo insista
                # (y escriba la llamada como texto). Se dice la negativa y ya.
                log.info("Plan no válido y bloqueado en partida (%s): negativa", invalid)
                display, secondary = IN_GAME_REFUSAL
                await self._fail(display, secondary, f"{display}." if from_voice else None)
                return
            if invalid:
                log.info("Plan no válido (%s): se reintenta", invalid)
                hint = f"Tu llamada anterior no era válida: {invalid}. Corrígela."
                await self._respond(text, marks, from_voice=from_voice, hint=hint, retried=True)
                return
        results = await self._act(Route(calls, "llm"), marks, from_voice=from_voice)
        if (
            self._agent.steps == 0
            and len(plan.calls) == 1
            and results
            and all(r.ok for r in results)
            # Dejada para después de la partida: aún no se sabe si funciona (ERRORES.md,
            # 2026-11-14: «Põ muusiga» → la web «Spotify», que luego no existía).
            and not any(r.data.get("deferred") for r in results)
        ):
            self._learn(text, ToolCall(plan.calls[0].name, plan.calls[0].arguments))
        elif (
            self._agent.steps == 0
            and len(plan.calls) > 1
            and results
            and len(results) == len(calls)
            and all(r.ok and not r.data.get("deferred") for r in results)
            and not self._playing()
        ):
            self._learn_plan(text, calls)

    def _should_continue(
        self,
        calls: list[ToolCall],
        marks: _Marks,
        results: Sequence[ToolResult] = (),
        *,
        direct: bool = False,
    ) -> bool:
        """¿Hay que volver al LLM con lo consultado? Con límites de vueltas y de tiempo.

        `direct`: la petición la resolvió una regla del router; lo que ya trae su frase hecha
        (`ToolResult.speak`) se dice tal cual y no vuelve al LLM (6.20a)."""
        if self.executor is None or self._brain_off():
            return False
        if self._agent.steps >= MAX_STEPS or self._clock() - marks.end > MAX_SECONDS:
            log.info("Bucle de agente: límite alcanzado (%d vueltas)", self._agent.steps)
            return False
        tools = [self.executor.registry.get(c.name) for c in calls]
        if len(results) == len(tools):
            return any(
                t is not None and t.observe and r.observe and not (direct and r.speak)
                for t, r in zip(tools, results, strict=True)
            )
        return any(t is not None and t.observe for t in tools)

    def _tool_keys(self) -> frozenset[str]:
        if self.executor is None:
            return frozenset()
        return tool_keys(t.name for t in self.executor.registry.all())

    def _playing(self) -> bool:
        return self.game is not None and self.game.active

    def _brain_off(self) -> bool:
        return self.game is not None and self.game.active and self.game.brain_off

    def _blocked_in_game(self, calls: list[ToolCall]) -> bool:
        """¿Alguna llamada está bloqueada por la partida en curso?"""
        if self.game is None or not self.game.active or self.executor is None:
            return False
        for call in calls:
            tool = self.executor.registry.get(call.name)
            if tool is not None and self.game.policy_for(tool) is GamePolicy.BLOCKED:
                return True
        return False

    async def _show_known(self) -> None:
        """Lo último consultado, en su burbuja (cuando el modelo no sabe seguir)."""
        shown = next((r for _, r in reversed(self._agent.done) if r.display), None)
        if shown is not None and shown.display:
            await self._show_bubble(shown.display, shown.secondary or "")
            self._schedule_bubble_hide(bubble_duration(shown.display, shown.secondary or ""))
        await self._go_idle()

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
        if self._brain_off():
            # En partida sin cerebro (no cabe junto al juego): solo las reglas.
            log.info("En partida sin cerebro: %r se deja para después", text)
            spoken = "En partida no puedo pensarlo. Pregúntamelo al terminar."
            await self._fail(
                "En partida no puedo pensarlo",
                "pregúntamelo al terminar",
                spoken if from_voice or self.speak_typed else None,
            )
            return
        await self._set_state(NyxState.THINKING)
        plan: ToolPlan | None = None
        extra = "\n".join(part for part in (await self._context(), hint) if part)
        bubble: BubbleReady | None = None
        bubble_shown = False
        splitter = SentenceSplitter()
        level_task: asyncio.Task[None] | None = None

        first_said = ""  # primera frase dicha: detalle para una cabecera de una palabra
        # Respuesta larga (6.28): lo mandado a la voz, lo que ya ha empezado a sonar y, al
        # pasar del panel corto al largo, lo que enseña este.
        said: list[str] = []
        sounded: list[str] = []
        long_answer: LongAnswer | None = None
        typed_long: Reply | None = None

        async def show_bubble() -> None:
            nonlocal bubble_shown
            if long_answer is not None:
                return  # ya está el panel largo: no se vuelve al corto
            if bubble is not None and (bubble.display or bubble.secondary):
                bubble_shown = True
                await self._show_bubble(
                    bubble.display, bubble.secondary, spoken=final_spoken or first_said, asked=text
                )

        async def on_speech_start() -> None:
            nonlocal level_task
            marks.first_audio = self._clock()
            await self._set_state(NyxState.SPEAKING)
            await show_bubble()
            level_task = asyncio.create_task(self._speaking_levels())
            log.info("Latencia: %s", _latency(marks))

        long_ready = False  # el panel largo ya tiene escrito lo de antes: se sigue frase a frase

        async def on_sentence(sentence: str, duration: float) -> None:
            # Empieza a sonar: si ya es el panel largo, se escribe a lo que dura su audio.
            sounded.append(sentence)
            if long_answer is not None and long_ready:
                long_answer.sentences.append(sentence)
                await self.bus.publish(ReadingAppended(sentence, duration))

        async def open_long() -> None:
            """Pasa al panel largo con lo que ya ha sonado escrito de golpe."""
            nonlocal long_answer, bubble_shown, long_ready
            title = bubble.display if bubble is not None else ""
            long_answer = LongAnswer(title=panel_title(title), sources=self._web_sources())
            await self._show_long(long_answer, reading=True)
            bubble_shown = True
            # Lo que haya empezado a sonar mientras se enseñaba el panel también va aquí, en
            # orden (si no, salía antes que lo anterior y repetido). Sin esperas desde aquí
            # hasta `long_ready`: ninguna frase se cuela entre medias.
            earlier = list(sounded)
            long_answer.sentences = earlier
            long_ready = True
            if earlier:
                await self.bus.publish(ReadingAppended(" ".join(earlier), 0.0))

        # Si la petición se escribió, por defecto la respuesta va solo en la burbuja (quien
        # escribe suele querer silencio); el ajuste responses.speak_typed la hace hablada.
        speak = from_voice or self.speak_typed
        speech = (
            _Speech(self.tts, self.player, on_speech_start, on_sentence)
            if speak and self.tts is not None and self.player is not None
            else None
        )
        garbled = False
        # Nombres internos de herramientas: nunca en la burbuja ni en la voz (6.03: «[set_alarm
        # | …]», «listalarms, …»). Si la cabecera los trae, la burbuja sale de lo que se dice.
        keys = self._tool_keys()
        rebuild = False
        held: list[str] = []
        final_spoken = ""

        def say(sentence: str) -> None:
            nonlocal garbled, bubble, first_said
            if garbled or looks_like_code(sentence) or mentions_tool(sentence, keys):
                garbled = True
                return
            first_said = first_said or sentence
            if rebuild:
                held.append(sentence)
                return
            if speech is not None:
                marks.first_sentence = marks.first_sentence or self._clock()
                speech.say(sentence)
                said.append(sentence)

        def wants_long() -> bool:
            return long_answer is None and speech is not None and is_long(" ".join(said), len(said))

        try:
            continuing = self._agent.steps > 0
            # Tras leer internet, la vuelta siguiente va sin herramientas (6.06).
            read_web = any(call.name in TOOLS_OFF_AFTER for call, _ in self._agent.done)
            respond = self.brain.respond(
                text, extra, continuing=continuing, tools_off=continuing and read_web
            )
            async with contextlib.aclosing(respond) as events:
                async for event in events:
                    if marks.first_token is None:
                        marks.first_token = self._clock()
                    if isinstance(event, ToolPlan):
                        plan = event
                    elif isinstance(event, BubbleReady):
                        header = f"{event.display} {event.secondary}"
                        if looks_like_code(header):
                            garbled = True
                            continue
                        if mentions_tool(header, keys):
                            log.info("Cabecera con un nombre interno: %r", header)
                            rebuild = True
                            continue
                        bubble = event
                        if bubble_shown:
                            await show_bubble()
                    elif isinstance(event, SpokenDelta) and speech is not None:
                        for sentence in splitter.feed(event.text):
                            say(sentence)
                        if wants_long() and not garbled:
                            await open_long()
                    elif isinstance(event, SpokenEnd) and speech is not None:
                        if rest := splitter.flush():
                            say(rest)
                        if wants_long() and not garbled:
                            await open_long()
                    elif isinstance(event, ReplyDone):
                        log.info("Respuesta: %s", event.reply.model_dump_json())
                        reply = event.reply
                        final_spoken = reply.spoken.strip()
                        if looks_like_code(
                            f"{reply.display} {reply.secondary} {reply.spoken}"
                        ) or mentions_tool(reply.spoken, keys):
                            garbled = True
                        elif rebuild:
                            bubble = BubbleReady(first_sentence(reply.spoken), "")
                        elif speech is None:
                            bubble = text_bubble(reply)
                            if is_long(final_spoken, sentence_count(final_spoken)):
                                typed_long = reply
            if (
                plan is None
                and rebuild
                and self._agent.steps == 0
                and not final_spoken.endswith("?")
            ):
                # Ha escrito el nombre interno de la herramienta en la cabecera y una frase
                # afirmativa sin emitir tool_calls (p. ej. fingir una acción o inventar un dato).
                garbled = True
            if garbled and plan is None:
                # Nunca se dice ni se enseña código (ERRORES.md, 2026-11-11).
                log.warning("Respuesta con código o llamadas escritas: no se dice")
                if speech is not None:
                    await speech.abort()
                p = self.phrases.pick("garbled")
                await self._fail(p.display, p.secondary, p.spoken if speak else None)
                return
            if plan is not None:
                if speech is not None:
                    await speech.abort()
                await self._run_plan(plan, text, marks, from_voice=from_voice, retried=retried)
                return
            if speech is not None and (rest := splitter.flush()):
                say(rest)
            if speech is not None and held:
                if bubble is None:
                    bubble = BubbleReady(first_sentence(" ".join(held)), "")
                for sentence in held:
                    marks.first_sentence = marks.first_sentence or self._clock()
                    speech.say(sentence)
                    said.append(sentence)
            if wants_long():
                await open_long()
            if speech is not None:
                await speech.finish()
            if long_answer is not None:
                long_answer.text = " ".join(long_answer.sentences or said)
            elif not bubble_shown and typed_long is not None:
                # Escrita y larga: todo de golpe en el panel largo (6.28).
                long_answer = LongAnswer(
                    title=panel_title(typed_long.display),
                    text=typed_long.spoken.strip(),
                    sources=self._web_sources(),
                )
                await self._show_long(long_answer)
                bubble_shown = True
            if not bubble_shown:
                if speech is None or not speech.started:
                    log.info("Latencia (sin voz): %s", _latency(marks))
                await show_bubble()
        except LLMError as e:
            log.error("Fallo del LLM: %s", e)
            if speech is not None:
                await speech.abort()
            p = self.phrases.llm_error(e.kind)
            await self._fail(p.display, p.secondary, p.spoken if speak else None)
            return
        except asyncio.CancelledError:
            if speech is not None:
                await speech.abort()
            raise
        finally:
            if level_task is not None:
                level_task.cancel()
        # El panel largo no se va solo mientras se lee: lo cierra el usuario (o la interfaz,
        # tras 2 minutos sin tocarlo).
        if bubble_shown and bubble is not None and long_answer is None:
            self._schedule_bubble_hide(bubble_duration(bubble.display, bubble.secondary))
        if from_voice and self.listen.followup_s > 0 and self.capture is not None:
            await self.start_listening(followup=True)
        else:
            await self._go_idle()

    # --- primer arranque guiado (9.10) ---

    async def announce(self, text: str, *, listen_after: float = 0.0) -> None:
        """Nyx dice `text` sin esperar a que acabe; `hush()` la calla con un fundido. Con
        `listen_after` (segundos), al acabar escucha la respuesta sin que haya que decir «Nyx»."""
        self.hush()
        if self.tts is None or self.player is None:
            return
        if self.mode is Mode.LISTENING:
            # Se te escuchaba sin «Nyx» y se ha tocado un botón: mientras habla no se escucha,
            # que se oiría a sí misma («Azul. Clásico y seguro.» elegiría el azul).
            self._drop_listening()
            self.mode = Mode.IDLE
        self._announce_text = text
        self._announcing = asyncio.create_task(self._announce(text, listen_after), name="announce")

    def hush(self) -> None:
        task = self._announcing
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def _announce(self, text: str, listen_after: float) -> None:
        assert self.tts is not None and self.player is not None

        async def started() -> None:
            await self._set_state(NyxState.SPEAKING)

        speech = _Speech(self.tts, self.player, started)
        levels = asyncio.create_task(self._speaking_levels())
        splitter = SentenceSplitter()
        try:
            for sentence in splitter.feed(text):
                speech.say(sentence)
            if (rest := splitter.flush()) is not None:
                speech.say(rest)
            await speech.finish()
        except asyncio.CancelledError:
            await speech.abort(fade=True)
            raise
        finally:
            levels.cancel()
            if self.state is NyxState.SPEAKING and self.mode is not Mode.LISTENING:
                await self._set_state(NyxState.IDLE)
        if (
            listen_after > 0
            and self.voice_enabled
            and self.capture is not None
            and self.mode is Mode.IDLE
        ):
            await self.start_listening(followup=True, timeout_s=listen_after)

    async def _speaking_levels(self) -> None:
        assert self.player is not None
        while True:
            await self.bus.publish(AudioLevel(self.player.level))
            await asyncio.sleep(1 / LEVEL_HZ)

    async def _say(self, text: str, marks: _Marks) -> None:
        """Dice una frase ya hecha (la de una herramienta), con el orbe hablando."""
        if self.tts is None or self.player is None:
            return
        try:
            audio = await self.tts.synthesize(text)
        except TTSError:
            log.exception("No se pudo decir la respuesta")
            return
        marks.first_audio = self._clock()
        log.info("Latencia (respuesta directa): %s", _latency(marks))
        await self._set_state(NyxState.SPEAKING)
        levels = asyncio.create_task(self._speaking_levels())
        try:
            self.player.enqueue(audio)
            await self.player.drain()
        finally:
            levels.cancel()

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
        self,
        display: str,
        secondary: str,
        actions: tuple[BubbleAction, ...] = (),
        *,
        kind: BubbleKind = "response",
        expires_s: float | None = None,
        spoken: str = "",
        asked: str = "",
    ) -> None:
        # Criterio común de los paneles (6.23): mayúscula, punto solo en frases, la línea
        # pequeña solo si aporta y la grande con detalle (`spoken`: lo que dice la voz).
        # `asked` (lo pedido): solo para las cabeceras del modelo, que a veces no vienen a cuento.
        display, secondary = tidy(display, secondary, spoken, asked)
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        if not actions:
            self._actions.clear()  # una burbuja nueva sustituye a los botones anteriores
        await self.bus.publish(
            BubbleShown(
                display=display,
                secondary=secondary or None,
                actions=actions,
                kind=kind,
                expires_s=expires_s,
            )
        )

    # --- panel largo (6.28): explicación, receta, pasos o lista ---

    async def _show_long(self, answer: LongAnswer, *, reading: bool = False) -> None:
        """Panel largo con sus botones. `reading`: el texto llega frase a frase con la voz."""
        if self._bubble_timer is not None:
            self._bubble_timer.cancel()
            self._bubble_timer = None
        self._long = answer
        text = "" if reading or answer.structured else answer.text
        await self.bus.publish(
            BubbleShown(
                display=answer.title,
                secondary=" · ".join(answer.sources) or None,
                actions=LONG_ACTIONS,
                kind="long",
                text=text,
                sections=tuple(LongSection(s.title, s.items, s.ordered) for s in answer.sections),
                reading=reading,
            )
        )

    def _web_sources(self) -> tuple[str, ...]:
        """De dónde salió lo último buscado en internet en esta petición (para el panel)."""
        for call, result in reversed(self._agent.done):
            if call.name == "web_search" and result.ok and result.secondary:
                return tuple(s for s in result.secondary.split(" · ") if s)
        return ()

    def _panel_wants(self, text: str) -> PanelCommand | None:
        """Lo que `text` pide al panel largo abierto (cerrar, copiar, guardar), o None."""
        if not self._long_open or self._long is None:
            return None
        return panel_command(text, offered=self._clock() < self._offer_until)

    async def _panel(self, command: PanelCommand, text: str, *, from_voice: bool) -> None:
        log.info("Panel largo: %s (%r)", command, text)
        if command == "copy":
            await self._copy_long()
        elif command == "save":
            await self._save_long(phrase=text, voice=from_voice)
        else:
            await self._close_long()
        await self._go_idle()

    async def _copy_long(self) -> None:
        if self._long is None:
            return
        try:
            await asyncio.to_thread(write_clipboard_text, self._long.copy_text())
            note = "Copiado"
        except Exception:
            log.warning("No se pudo copiar el panel largo", exc_info=True)
            note = "No he podido copiarlo"
        await self.bus.publish(PanelNote(note))

    async def _save_long(self, *, phrase: str = "(botón Guardar)", voice: bool = False) -> None:
        self._offer_until = 0.0
        answer = self._long
        if answer is None or self.executor is None:
            return
        call = ToolCall(
            "save_note",
            {"title": answer.title or "Nota", "text": answer.note_text(date.today())},
        )
        result = await self.executor.run(call, phrase=phrase, voice=voice)
        if not result.ok:
            await self.bus.publish(PanelNote(result.display or result.message))
            return
        undo_id = result.data.get("undo_id")
        await self.bus.publish(
            PanelNote(
                "Nota guardada en Documentos › Notas de Nyx",
                f"long-undo-{undo_id}" if undo_id else None,
            )
        )

    async def _undo_long_note(self, undo_id: str) -> None:
        if self.executor is None:
            return
        result = await self.executor.run(
            ToolCall("undo", {"id": undo_id}), phrase="(botón Deshacer de la nota)"
        )
        # Sin Deshacer: vuelven los botones de siempre (se puede guardar otra vez).
        await self.bus.publish(PanelNote(result.display or result.message))

    async def _close_long(self) -> None:
        self._long_open = False
        self._offer_until = 0.0
        await self.bus.publish(BubbleHidden())

    async def _on_long_action(self, action: str) -> None:
        if action == "long-save":
            self._spawn(self._save_long())
        elif action == "long-copy":
            self._spawn(self._copy_long())
        elif action in ("long-close", "long-timeout"):
            # «long-timeout»: la interfaz lo cierra tras 2 minutos sin tocarlo.
            if self._long_open:
                self._spawn(self._close_long())
        elif action.startswith("long-undo-"):
            self._spawn(self._undo_long_note(action.removeprefix("long-undo-")))

    async def _on_any_bubble(self, event: BubbleShown) -> None:
        # Cualquier otro panel (una respuesta nueva, una alarma) sustituye al largo.
        self._long_open = event.kind == "long"
        if not self._long_open:
            self._offer_until = 0.0

    async def _on_any_bubble_hidden(self, _: BubbleHidden) -> None:
        self._long_open = False
        self._offer_until = 0.0

    async def _maybe_structured(
        self, calls: Sequence[ToolCall], results: Sequence[ToolResult], marks: _Marks
    ) -> bool:
        """Tras buscar en internet algo que pide receta, pasos o lista: panel estructurado,
        voz con el resumen y la oferta de guardarlo. False si no toca (o el modelo no lo
        estructura): entonces el modelo lo cuenta como siempre."""
        if (self.game is not None and self.game.active) or self._brain_off():
            return False  # en partida, solo la voz (se puede guardar al terminar)
        found_web = next(
            (
                r
                for c, r in zip(calls, results, strict=False)
                if c.name == "web_search"
                and r.ok
                and r.external
                and r.data.get("how") != "navegador"
            ),
            None,
        )
        if found_web is None or found_web.external is None:
            return False
        if len(found_web.external) < STRUCTURE_MIN_CHARS or not wants_structure(marks.phrase):
            return False
        await self._set_state(NyxState.THINKING)
        found = await structure(self.brain.llm, marks.phrase, found_web.external)
        if found is None:
            return False
        sources = tuple(s for s in (found_web.secondary or "").split(" · ") if s)
        answer = to_answer(found, sources)
        spoken = spoken_summary(found)
        log.info("Respuesta estructurada (%s): %s", found.tipo, answer.title)
        await self._show_long(answer)
        self.brain.memory.add(marks.phrase, f"{spoken}\n{answer.body_text()}")
        if self._from_voice or self.speak_typed:
            await self._say(spoken, marks)
        # Un «sí» suelto vale como «guárdamela» durante un rato (también si se dice tarde).
        self._offer_until = self._clock() + OFFER_S
        if self._from_voice and self.listen.followup_s > 0 and self.capture is not None:
            await self.start_listening(followup=True)
        else:
            await self._go_idle()
        return True

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
            kind="confirm",
            expires_s=CONFIRM_TIMEOUT_S,
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
        if event.id.startswith("long-"):
            # Botones del panel largo: no dependen de `_actions`, que cambia con cada burbuja.
            await self._on_long_action(event.id)
            return
        handler = self._actions.get(event.id)
        if handler is None:
            log.info("Botón %s ya no está activo", event.id)
            return
        handler()

    async def _offer_undo(self, result: ToolResult) -> None:
        undo_id = str(result.data["undo_id"])
        button = f"undo-{undo_id}"
        # Alarmas y temporizadores: aviso corto (se puede decir «deshaz» los 30 s igualmente).
        ttl = NOTICE_BUBBLE_S if "alarm_id" in result.data else UNDO_TTL_S
        await self._show_bubble(
            result.display or result.message,
            result.secondary or "",
            (BubbleAction(button, "Deshacer"),),
            kind="undo",
            expires_s=ttl,
        )
        self._actions = {button: lambda: self._spawn(self._undo(undo_id))}
        self._schedule_bubble_hide(ttl)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._side_tasks.add(task)
        task.add_done_callback(self._side_tasks.discard)

    async def _on_announce(self, event: Announce) -> None:
        """Lo dice solo si Nyx está libre: nunca corta una petición en curso."""
        if self.mode is not Mode.IDLE or self.tts is None or self.player is None:
            return
        try:
            self.player.enqueue(await self.tts.synthesize(event.text))
        except TTSError:
            log.exception("No se pudo decir el aviso")

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
