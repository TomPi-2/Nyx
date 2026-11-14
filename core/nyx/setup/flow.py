"""Primer arranque guiado por Nyx (tarea 9.10; SPEC §13; `docs/prototipos/instalador.html`).

No es una ventana con pasos: Nyx aparece en su sitio, habla y saca debajo un panel propio para
cada paso. El orden aprobado (2026-11-14) es bienvenida, micrófono (primero, para que todo lo
demás se pueda contestar hablando), su color, su tamaño, el color de los paneles, el escaneo
del equipo y los datos anónimos. Cada cambio se aplica al momento por el mismo camino que
Ajustes y Nyx lo comenta.

- Lo que se toca en el panel llega como `SetupFlowRequested`; lo que se dice, por `hear()`
  (la canalización de voz se lo pasa mientras el primer arranque está en marcha).
- Si se pasa de paso mientras Nyx habla, se calla con un fundido de 150 ms y empieza con el
  siguiente al momento (`Speaker.hush`).
- El estado entero sale en `SetupFlowChanged` para el panel (`setup_flow_state`).
- `start(mode=...)` con un paso suelto («color», «size», «tint») es la 9.11: «Nyx, quiero
  cambiarte el color» saca el mismo panel, sin el resto del primer arranque.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

from nyx.bus import EventBus
from nyx.events import (
    MicLevelChanged,
    NyxState,
    SettingsRequested,
    SetupFlowChanged,
    SetupFlowRequested,
    SetupRequested,
    SetupResult,
    StateChanged,
)
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.settings.model import Settings
from nyx.setup import everything
from nyx.setup.answers import (
    SIZE_DEFAULT,
    SIZE_MAX,
    SIZE_MIN,
    Answer,
    understand,
    vocabulary,
)

log = logging.getLogger(__name__)

STEPS = ("welcome", "mic", "color", "size", "tint", "scan", "data")
Mode = Literal["first_run", "color", "size", "tint"]

#: Nivel del micrófono a partir del cual «te oigo» (0–1, el de la prueba).
HEARD_LEVEL = 0.25
#: Mientras está el primer arranque, Nyx te escucha sin «Nyx» al acabar de hablar. Es la
#: espera de cada tanda: si no dices nada, la canalización vuelve a escuchar (antes eran 8 s y
#: un «siguiente» algo tardío se perdía, ERRORES.md 2026-11-14).
LISTEN_AFTER_S = 30.0
#: La interfaz pide empezar en cuanto conecta, antes de que la voz esté cargada: se espera.
SPEAKER_WAIT_S = 60.0


class Speaker(Protocol):
    """Quien pone la voz (la canalización): dice algo y se calla al momento si se le pide."""

    async def announce(self, text: str, *, listen_after: float = 0.0) -> None: ...
    def hush(self) -> None: ...


# --- Lo que dice Nyx -----------------------------------------------------------------------------

SAY: dict[str, Sequence[str]] = {
    "welcome": (
        "¡Hola! Soy Nyx. Mientras bajo lo que me falta, vamos a dejarme a tu gusto. Son "
        "seis pasos y todo se puede cambiar luego.",
    ),
    "mic": (
        "Primero, el oído: así lo demás me lo puedes decir hablando. Habla un poco y mira "
        "cómo se mueve la barra.",
    ),
    "color": ("Ahora, mi color. Dime cuál, por ejemplo «ponte coral», o tócalo.",),
    "size": ("¿Y de tamaño? Dime «más grande» o «más pequeña», o arrastra.",),
    "tint": ("Ahora el color de mis paneles, como este en el que te hablo. Dime cuál o tócalo.",),
    "scan": (
        "Ahora miro qué tienes instalado, para abrirlo cuando me lo pidas. No sale nada de tu PC.",
    ),
    "data": (
        "Última pregunta: ¿me dejas enviar datos de uso anónimos para mejorar? Tú decides; no "
        "cambia nada de lo que hago.",
    ),
    "color_again": ("¿De qué color me quieres? Dímelo o tócalo y me lo pruebo.",),
    "size_again": ("¿Más grande o más pequeña? Dímelo o arrastra.",),
    "tint_again": ("¿De qué color quieres mis paneles?",),
}

COLOR_SAYS = {
    "blanco": "El de siempre. Limpio y elegante.",
    "perla": "Perla: casi blanco, pero con un punto cálido.",
    "arena": "Arena. Tranquila, como una tarde de playa.",
    "melocoton": "Melocotón… me siento dulce.",
    "coral": "¡Coral! Me da energía.",
    "rojo": "Rojo. Atrevida, me gusta.",
    "rosa": "Rosa suave. Muy amable.",
    "fucsia": "¡Fucsia! Imposible no verme.",
    "lavanda": "Lavanda: calma total.",
    "violeta": "Violeta. Un poco misteriosa.",
    "azul_cielo": "Azul cielo, como un día despejado.",
    "azul": "Azul. Clásico y seguro.",
    "turquesa": "Turquesa: fresca como el mar.",
    "menta": "Menta. Me siento recién estrenada.",
    "verde": "Verde. Todo en marcha.",
    "lima": "¡Lima! Con chispa.",
    "amarillo": "Amarillo: alegría pura.",
    "ambar": "Ámbar, cálida como una lámpara.",
    "grafito": "Grafito: discreta, casi una sombra.",
}

TINT_SAYS = {
    "gris": "Gris, el de siempre: va con todo.",
    "grafito": "Grafito: más oscuro, más serio.",
    "azul_noche": "Azul noche. Elegante.",
    "oceano": "Océano: profundo.",
    "bosque": "Bosque. Me relaja.",
    "salvia": "Salvia, suave y natural.",
    "ciruela": "Ciruela: con personalidad.",
    "vino": "Vino. Con clase.",
    "rosa": "Rosa: cálido y cercano.",
    "arena": "Arena, luminoso.",
    "cobre": "Cobre: cálido como el ámbar.",
    "lavanda": "Lavanda, a juego con la calma.",
}

NOT_UNDERSTOOD = (
    "Perdona, eso no lo he entendido. Puedes decirlo de otra forma o tocarlo.",
    "No te he pillado. Prueba de otra forma, o tócalo en el panel.",
)


def size_says(size: int) -> str:
    if size <= 70:
        return "Así de pequeña casi ni se me ve. Pero me vale."
    if size < SIZE_DEFAULT:
        return "Discreta. Bien."
    if size == SIZE_DEFAULT:
        return "Mi tamaño de siempre."
    if size <= 130:
        return "Un poco más grande: así me ves mejor."
    return "¡Qué grande me siento! Ojo, que así tapo más."


# --- El primer arranque -------------------------------------------------------------------------


class GuidedSetup:
    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        *,
        speaker: Callable[[], Speaker | None] = lambda: None,
        index: Callable[[], SystemIndex | None] = lambda: None,
        mics: Callable[[], list[str]] = lambda: [],
        switch_mic: Callable[[str], None] | None = None,
        speakers: Callable[[], list[str]] = lambda: [],
        switch_output: Callable[[str], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.bus = bus
        self.settings = settings
        self._speaker = speaker
        self._index = index
        self._mics = mics
        self._switch_mic = switch_mic
        self._speakers = speakers
        self._switch_output = switch_output
        self._rng = rng or random.Random()
        self.active = False
        self.mode: Mode = "first_run"
        self.step = 0
        self.said = ""
        self.heard = False  # el micrófono ha oído algo
        self.woke = False  # se ha activado con «Nyx»
        self.mic_names: list[str] = []
        self.speaker_names: list[str] = []
        self.scan: dict[str, Any] | None = None  # None: aún no; {"running": True}: escaneando
        self.everything: dict[str, Any] = {}
        self.installing_everything = False
        self.usage: bool | None = None  # ninguna opción viene marcada
        self.downloading = False
        self.finished = False
        self._nyx_state = NyxState.IDLE
        # main.py lo marca cuando la canalización (la voz) está lista.
        self.speaker_ready = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()
        self._unsubscribe = [
            bus.subscribe(SetupFlowRequested, self._on_request),
            bus.subscribe(MicLevelChanged, self._on_mic_level),
            bus.subscribe(StateChanged, self._on_state),
            bus.subscribe(SetupResult, self._on_setup_result),
        ]

    async def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        for task in list(self._tasks):
            task.cancel()
        await self._mic_test(False)

    @property
    def key(self) -> str:
        return STEPS[self.step] if self.mode == "first_run" else self.mode

    @property
    def prompt(self) -> str:
        """Pista para whisper con las palabras del paso (los nombres de los colores…)."""
        return vocabulary(self.key)

    def understands(self, text: str) -> bool:
        """¿Es ya una respuesta completa? Para dejar de escuchar en cuanto se dice."""
        return self.active and self._understand(text) is not None

    def _understand(self, text: str) -> Answer | None:
        return understand(
            self.key,
            text,
            size=self.settings.appearance.indicator_size,
            mics=self.mic_names,
            speakers=self.speaker_names,
            data_chosen=self.usage is not None,
        )

    # --- Empezar y terminar ---------------------------------------------------------------------

    async def start(self, mode: Mode = "first_run") -> None:
        """Empieza el primer arranque o, con un paso suelto, ese panel solo (9.11)."""
        self.mode = mode
        self.active = True
        self.finished = False
        self.step = 0
        await self._wait_speaker()
        if mode == "first_run":
            self.heard = self.woke = False
            self.usage = None
            self.scan = None
            self.mic_names = self._mics()
            self.speaker_names = self._speakers()
            self.downloading = True
            await self.bus.publish(SetupRequested("download"))  # lo que falte (voz, cerebro)
        log.info("Primer arranque guiado: %s", mode)
        await self._enter()

    async def _wait_speaker(self) -> None:
        if self._speaker() is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.speaker_ready.wait(), SPEAKER_WAIT_S)

    async def _finish(self) -> None:
        await self._mic_test(False)
        if self.mode == "first_run":
            await self._apply({"onboarding": {"done": True}})
            self.finished = True
            self.active = False
            text = (
                "¡Ya está todo! Termino de bajar lo que me falta y te aviso. Puedes seguir con lo "
                "tuyo."
                if self.downloading
                else "¡Lista! Llámame diciendo «Nyx» o con Win + Alt + H."
            )
            await self._say(text)
        else:
            self.active = False
            await self._say("¡Me encanta cómo he quedado!")
        log.info("Primer arranque guiado terminado (%s)", self.mode)

    async def cancel(self) -> None:
        """Se cierra sin acabar (la app se cierra): la próxima vez vuelve a salir."""
        self._hush()
        await self._mic_test(False)
        self.active = False
        await self._publish()

    # --- Lo que llega -----------------------------------------------------------------------------

    async def hear(self, text: str) -> bool:
        """Lo que el usuario ha dicho (o escrito) con el primer arranque en marcha."""
        if not self.active:
            return False
        answer = self._understand(text)
        log.info("Primer arranque, %s: %r → %s", self.key, text, answer)
        if answer is None:
            await self._say(self._pick(NOT_UNDERSTOOD))
            return True
        await self._act(answer)
        return True

    async def on_wake(self) -> None:
        """«Nyx» (la palabra de activación) con el primer arranque en marcha."""
        if self.active and self.key == "mic":
            await self._act(Answer("wake"))

    async def _on_request(self, event: SetupFlowRequested) -> None:
        action, value = event.action, event.value
        if action == "start":
            mode = value if value in ("color", "size", "tint") else "first_run"
            # Aparte: puede esperar a que la voz esté lista sin parar los demás mensajes.
            self._spawn(self.start(mode))  # type: ignore[arg-type]
            return
        if not self.active:
            return
        if action == "size_live" and isinstance(value, int):
            await self._apply({"appearance": {"indicator_size": _clamp(value)}})
            return
        if action == "install_everything":
            self._spawn(self._install_everything())
            return
        if action == "close":
            await self.cancel()
            return
        kinds = (
            "next", "back", "skip", "pick", "size", "mic", "speaker", "wake", "data", "done",
            "heard",
        )  # fmt: skip
        if action in kinds:
            await self._act(Answer(action, value))  # type: ignore[arg-type]

    # --- Hacer lo pedido --------------------------------------------------------------------------

    async def _act(self, answer: Answer) -> None:
        kind, value = answer.kind, answer.value
        if kind in ("next", "done") and self.mode != "first_run":
            await self._finish()  # el panel suelto (9.11): «listo» lo cierra
        elif kind == "next":
            await self._go(self.step + 1)
        elif kind == "back":
            await self._go(self.step - 1)
        elif kind == "skip":
            await self._say("Vale, me quedo como estoy. Todo se cambia luego en Ajustes.")
            await self._finish()
        elif kind == "done":
            if self.mode != "first_run" or self.usage is not None:
                await self._finish()
        elif kind == "pick" and isinstance(value, str):
            await self._pick_look(value)
        elif kind == "size" and isinstance(value, int):
            size = _clamp(value)
            await self._apply({"appearance": {"indicator_size": size}})
            await self._react(size_says(size))
        elif kind == "mic" and isinstance(value, int) and 0 <= value < len(self.mic_names):
            name = self.mic_names[value]
            await self._apply({"audio": {"input_device": name}})
            if self._switch_mic is not None:  # también para «Nyx»: se usa ya, sin reiniciar
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(self._switch_mic, name)
            await self._mic_test(True)  # con el micrófono nuevo
            await self._react(f"Vale, te escucho por «{self.mic_names[value]}».")
        elif kind == "speaker" and isinstance(value, int) and 0 <= value < len(self.speaker_names):
            name = self.speaker_names[value]
            await self._apply({"audio": {"output_device": name}})
            if self._switch_output is not None:  # la siguiente frase ya suena por ahí
                with contextlib.suppress(Exception):
                    self._switch_output(name)
            await self._react("¿Me oyes bien por aquí?")
        elif kind == "heard":
            await self._on_heard()
        elif kind == "wake":
            self.heard = self.woke = True
            await self._react(
                "¡Aquí estoy! Me activo bien con tu voz. Desde ahora puedes contestarme "
                "hablando: «siguiente», «atrás» o lo que elijas."
            )
        elif kind == "data" and isinstance(value, bool):
            self.usage = value
            await self._apply({"privacy": {"usage_data": value}})
            await self._react(
                "¡Gracias! Así mejoro más rápido." if value else "Sin problema: nada sale de tu PC."
            )
        await self._publish()

    async def _pick_look(self, value: str) -> None:
        if self.key == "color" and value in COLOR_SAYS:
            await self._apply({"appearance": {"nyx_color": value}})
            await self._react(COLOR_SAYS[value])
        elif self.key == "tint" and value in TINT_SAYS:
            await self._apply({"appearance": {"panel_tint": value}})
            await self._react(TINT_SAYS[value])

    async def _go(self, step: int) -> None:
        if self.mode != "first_run":
            return
        if step >= len(STEPS):
            if self.usage is not None:
                await self._finish()
            return
        if step < 0 or step == self.step:
            return
        self._hush()  # se calla en 150 ms y empieza con lo siguiente al momento
        if self.key == "mic":
            await self._mic_test(False)
        self.step = step
        await self._enter()

    async def _enter(self) -> None:
        key = self.key
        said = SAY.get(key if self.mode == "first_run" else f"{key}_again", ("",))
        await self._publish()
        await self._say(self._pick(said))
        if key == "mic":
            await self._mic_test(True)
        elif key == "scan" and self.scan is None:
            self._spawn(self._scan())

    # --- Micrófono ----------------------------------------------------------------------------

    async def _mic_test(self, on: bool) -> None:
        await self.bus.publish(SetupRequested("mic_test_start" if on else "mic_test_stop"))

    async def _on_mic_level(self, event: MicLevelChanged) -> None:
        # Mientras habla Nyx, el micrófono la oye a ella: no cuenta.
        if (
            self.active
            and self.key == "mic"
            and not self.heard
            and event.rms >= HEARD_LEVEL
            and self._nyx_state is not NyxState.SPEAKING
        ):
            await self._on_heard()

    async def _on_heard(self) -> None:
        if self.heard:
            return
        self.heard = True
        await self._react("¡Te oigo alto y claro! Ahora llámame: di «Nyx».")
        await self._publish()

    async def _on_state(self, event: StateChanged) -> None:
        self._nyx_state = event.state

    # --- Escaneo y Everything -------------------------------------------------------------------

    async def _scan(self) -> None:
        self.scan = {"running": True}
        self.everything = await asyncio.to_thread(everything.status)
        await self._publish()
        index = self._index()
        if index is not None:
            with contextlib.suppress(Exception):
                await index.refresh()
        self.scan = _scan_counts(index)
        if self.key != "scan" or not self.active:
            await self._publish()
            return
        apps, games = self.scan["apps"], self.scan["games"]
        text = f"Listo: {apps} programas y {games} juegos."
        if self.scan.get("game"):
            text += f" Por cierto, veo {self.scan['game']}: ¿partida luego?"
        if self.everything.get("installed"):
            text += " Con Everything encuentro cualquier archivo del disco al instante."
        else:
            text += (
                " Los archivos los busco con el índice de Windows; si quieres buscar en todo el "
                "disco al instante, puedo instalar Everything."
            )
        await self._react(text)
        await self._publish()

    async def _install_everything(self) -> None:
        if self.installing_everything:
            return
        self.installing_everything = True
        await self._publish()
        await self._say("Vale. Windows te pedirá permiso una vez.")
        try:
            ok = await everything.install()
        finally:
            self.installing_everything = False
        self.everything = await asyncio.to_thread(everything.status)
        await self._react(
            "Hecho: ahora encuentro cualquier archivo al momento."
            if ok
            else "No he podido instalarlo. Puedes hacerlo luego en Ajustes → Caché."
        )
        await self._publish()

    async def _on_setup_result(self, event: SetupResult) -> None:
        if event.action != "download":
            return
        self.downloading = False
        if self.finished and event.ok:
            await self._say("¡Lista! Ya tengo todo. Llámame diciendo «Nyx» o con Win + Alt + H.")
        await self._publish()

    # --- Voz, ajustes y estado ------------------------------------------------------------------

    async def _say(self, text: str) -> None:
        self.said = text
        await self._publish()
        speaker = self._speaker()
        if speaker is not None and text:
            # Mientras dura, se le contesta sin decir «Nyx» (también antes de probar el
            # micrófono: así se puede decir «empezar» en la bienvenida).
            listen = LISTEN_AFTER_S if self.active else 0.0
            await speaker.announce(text, listen_after=listen)

    async def _react(self, text: str) -> None:
        self._hush()
        await self._say(text)

    def _hush(self) -> None:
        speaker = self._speaker()
        if speaker is not None:
            speaker.hush()

    async def _apply(self, patch: dict[str, Any]) -> None:
        await self.bus.publish(SettingsRequested(patch))

    def _pick(self, options: Sequence[str]) -> str:
        return self._rng.choice(list(options)) if options else ""

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro, name="setup-flow")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def snapshot(self) -> dict[str, Any]:
        look = self.settings.appearance
        return {
            "active": self.active,
            "finished": self.finished,
            "mode": self.mode,
            "step": self.key,
            "index": self.step,
            "total": len(STEPS),
            "say": self.said,
            "color": look.nyx_color,
            "size": look.indicator_size,
            "tint": look.panel_tint,
            "mics": self.mic_names,
            "mic": self.settings.audio.input_device,
            "speakers": self.speaker_names,
            "speaker": self.settings.audio.output_device,
            "heard": self.heard,
            "woke": self.woke,
            "scan": self.scan,
            "everything": self.everything,
            "installing_everything": self.installing_everything,
            "usage": self.usage,
            "downloading": self.downloading,
        }

    async def _publish(self) -> None:
        await self.bus.publish(SetupFlowChanged(self.snapshot()))


def _clamp(size: int) -> int:
    return max(SIZE_MIN, min(SIZE_MAX, int(size)))


def _scan_counts(index: SystemIndex | None) -> dict[str, Any]:
    if index is None:
        return {"running": False, "apps": 0, "games": 0, "folders": 0, "game": None}
    games = index.entries({Kind.GAME})
    return {
        "running": False,
        "apps": len(index.entries({Kind.APP})),
        "games": len(games),
        "folders": len(index.entries({Kind.FOLDER})),
        "game": games[0].name if games else None,
    }
