"""El gestor de modos (tareas 8.10 y 8.11; docs/MODOS.md, aprobado el 2026-11-17).

Un solo modo elegido a la vez (Trabajo, Noche, Privacidad o uno de una extensión). **Partida no
pasa por aquí**: sigue igual por dentro (`game/`) y manda sobre cualquier modo; solo se mira
para no hacer nada del modo mientras se juega (lo que se pida jugando, al acabar).

- Al entrar se ejecutan acciones de la lista cerrada con las herramientas de Nyx y se guarda su
  «Deshacer»; al salir se deshacen al revés (vuelve el volumen, vuelven las apps ocultas…).
- Cómo es Nyx en cada modo: el volumen de su voz (`voice_gain`; las alarmas suenan como
  siempre), si se activa por voz, si las burbujas llevan contenido y si usa la red.
- Privacidad corta **toda la red de Nyx**: búsqueda, webs, el tiempo, instalar y actualizar, la
  red de las extensiones y los datos de uso (respuesta del usuario del 2026-11-17).
- Automáticos (apagados por defecto): Noche de una hora a otra y Trabajo al abrir una app.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Literal

from nyx.bus import EventBus
from nyx.game.detector import ForegroundChanged, GameStateChanged
from nyx.index.aliases import normalize
from nyx.settings.model import Settings
from nyx.tools.base import ToolResult

log = logging.getLogger(__name__)

Bubbles = Literal["all", "no_content"]
#: Herramientas que usan internet (Privacidad las bloquea).
NETWORK_TOOLS = frozenset({"web_search", "open_url", "get_weather", "install_app", "nyx_update"})
#: Lo que abre ventanas: un modo automático no lo hace (solo pedido por voz o «Activar»).
OPENS_WINDOWS = frozenset({"open_app", "open_settings"})
#: Lo que un modo puede hacer al entrar (también los de extensiones, 8.11). Nunca borrar,
#: escribir, mandar nada ni tocar la seguridad.
ACTION_TOOLS = frozenset(
    {"open_app", "window_layout", "set_volume", "media_control", "hide_apps", "open_settings"}
)


@dataclass(frozen=True, slots=True)
class ModeChanged:
    """El modo elegido ha cambiado (None: ninguno)."""

    mode: str | None
    name: str = ""


@dataclass(frozen=True, slots=True)
class ModeDef:
    id: str
    name: str
    voice_gain: float = 1.0
    wake: bool = True
    bubbles: Bubbles = "all"
    network: bool = True
    #: (herramienta, argumentos) al entrar; lo de Nyx sale de los ajustes (`actions_for`).
    actions: tuple[tuple[str, dict[str, Any]], ...] = ()
    #: De una extensión (8.11): nunca cambia la activación por voz, las burbujas ni la red.
    extension: str | None = None


BUILTIN = {
    "trabajo": ModeDef("trabajo", "Trabajo", voice_gain=0.6),
    "noche": ModeDef("noche", "Noche", voice_gain=0.5),
    "privacidad": ModeDef(
        "privacidad", "Privacidad", wake=False, bubbles="no_content", network=False
    ),
}
#: Cómo se dicen los modos de Nyx.
SAID = {
    "trabajo": "trabajo",
    "trabajar": "trabajo",
    "concentracion": "trabajo",
    "noche": "noche",
    "nocturno": "noche",
    "privacidad": "privacidad",
    "privado": "privacidad",
}

#: Ejecuta una herramienta de Nyx y devuelve su resultado entero (con su «Deshacer»).
Runner = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


def actions_for(mode: ModeDef, settings: Settings) -> list[tuple[str, dict[str, Any]]]:
    """Lo que hace el modo al entrar, con los ajustes de ahora (Ajustes → Modos)."""
    m = settings.modes
    if mode.id == "trabajo":
        steps: list[tuple[str, dict[str, Any]]] = [
            ("open_app", {"name": a, "focus": False}) for a in m.work_apps
        ]
        # Dos apps: una a cada lado.
        if len(m.work_apps) == 2:
            steps += [
                ("window_layout", {"action": "left", "name": m.work_apps[0]}),
                ("window_layout", {"action": "right", "name": m.work_apps[1]}),
            ]
        return steps + [("set_volume", {"app": a, "mute": True}) for a in m.work_mute]
    if mode.id == "noche":
        return [
            ("set_volume", {"level": m.night_volume}),
            # Windows no deja a una app cambiar la luz nocturna ni «no molestar» (7.10).
            ("open_settings", {"page": "luz nocturna"}),
            ("open_settings", {"page": "notificaciones", "focus": False}),
        ]
    if mode.id == "privacidad":
        return [("hide_apps", {"action": "hide", "app": a}) for a in m.privacy_hide]
    return [(t, a) for t, a in mode.actions if t in ACTION_TOOLS]


def _in_range(now: time, start: time, end: time) -> bool:
    return start <= now < end if start < end else now >= start or now < end


@dataclass
class _Active:
    mode: ModeDef
    undos: list[Callable[[], Awaitable[str]]] = field(default_factory=list)
    auto: bool = False


class ModeManager:
    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        run: Runner,
        *,
        playing: Callable[[], bool] = lambda: False,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.bus = bus
        self.settings = settings
        self._run = run
        self._playing = playing
        self._clock = clock
        # Los de extensiones (8.11): «id/nombre» → su especificación (lo pone services.py).
        self.ext_source: Callable[[], dict[str, Any]] = dict
        self._active: _Active | None = None
        self._pending: tuple[str, bool] | None = None  # pedido jugando: al acabar
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        bus.subscribe(GameStateChanged, self._on_game)
        bus.subscribe(ForegroundChanged, self._on_foreground)

    # --- Qué modo hay y cómo es Nyx en él -------------------------------------------------------

    @property
    def current(self) -> ModeDef | None:
        return self._active.mode if self._active else None

    def all_modes(self) -> dict[str, ModeDef]:
        extra = {
            key: ModeDef(
                key,
                spec.name,
                voice_gain=0.6 if spec.voice == "baja" else 1.0,
                actions=tuple((a.tool, dict(a.args)) for a in spec.actions),
                extension=key.split("/")[0],
            )
            for key, spec in self.ext_source().items()
        }
        return {**extra, **BUILTIN}  # los de Nyx no se pueden pisar

    def find(self, said: str) -> ModeDef | None:
        key = normalize(said).removeprefix("modo ").strip()
        key = SAID.get(key, key)
        modes = self.all_modes()
        if key in modes:
            return modes[key]
        return next((m for m in modes.values() if normalize(m.name) == key), None)

    def voice_gain(self) -> float:
        return self.current.voice_gain if self.current else 1.0

    def wake_on(self) -> bool:
        return self.current.wake if self.current else True

    def private(self) -> bool:
        return self.current is not None and self.current.bubbles == "no_content"

    def offline(self) -> bool:
        return self.current is not None and not self.current.network

    def blocked(self, tool: str) -> str | None:
        """Por qué el modo no deja usar esta herramienta (None: sí deja)."""
        if self.offline() and tool in NETWORK_TOOLS:
            return f"En modo {self.current.name if self.current else ''} no uso internet"
        return None

    # --- Entrar y salir -------------------------------------------------------------------------

    async def enter(self, mode_id: str, *, auto: bool = False) -> str:
        mode = self.all_modes().get(mode_id)
        if mode is None:
            return "Ese modo no existe"
        if self._playing():
            self._pending = (mode_id, auto)
            return f"Al acabar la partida paso a modo {mode.name}"
        async with self._lock:
            if self._active is not None and self._active.mode.id == mode.id:
                return f"Ya estoy en modo {mode.name}"
            await self._leave()
            active = _Active(mode, auto=auto)
            self._active = active
            failed = 0
            for tool, args in actions_for(mode, self.settings):
                if auto and tool in OPENS_WINDOWS:
                    continue  # sin pedirlo, nada se abre solo (decisión 2026-11-15)
                try:
                    result = await self._run(tool, args)
                except Exception:
                    log.exception("Modo %s: falló %s", mode.id, tool)
                    failed += 1
                    continue
                if result.undo is not None:
                    active.undos.append(result.undo.action)
                failed += not result.ok
            log.info(
                "Modo %s (%s, %d acciones sin hacer)", mode.id, "auto" if auto else "voz", failed
            )
        await self.bus.publish(ModeChanged(mode.id, mode.name))
        return f"Modo {mode.name} activado"

    async def exit(self) -> str:
        self._pending = None
        async with self._lock:
            name = self._active.mode.name if self._active else None
            await self._leave()
        if name is None:
            return "No hay ningún modo activado"
        await self.bus.publish(ModeChanged(None))
        return f"He salido del modo {name}"

    async def _leave(self) -> None:
        active, self._active = self._active, None
        if active is None:
            return
        for undo in reversed(active.undos):
            try:
                await undo()
            except Exception as e:
                log.warning("Al salir del modo %s no se pudo deshacer algo: %s", active.mode.id, e)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        with contextlib.suppress(Exception):
            await self.exit()  # al cerrar Nyx, el PC queda como estaba

    # --- Partida y automáticos ------------------------------------------------------------------

    async def _on_game(self, event: GameStateChanged) -> None:
        if not event.active and self._pending is not None:
            mode_id, auto = self._pending
            self._pending = None
            await self.enter(mode_id, auto=auto)

    async def _on_foreground(self, event: ForegroundChanged) -> None:
        wanted = [normalize(a) for a in self.settings.modes.work_auto_apps]
        if not wanted or self._active is not None:
            return
        process = normalize(event.process.lower().removesuffix(".exe"))
        if any(w and (w in process or w in normalize(event.title)) for w in wanted):
            await self.enter("trabajo", auto=True)

    def start(self) -> None:
        self._task = asyncio.create_task(self._night_loop(), name="modes-night")

    async def _night_loop(self) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self.check_night()
            await asyncio.sleep(60)

    async def check_night(self) -> None:
        m = self.settings.modes
        if m.night_from is None:
            return
        start = time.fromisoformat(m.night_from)
        end = time.fromisoformat(m.night_to)
        inside = _in_range(self._clock().time(), start, end)
        if inside and self._active is None:
            await self.enter("noche", auto=True)
        elif not inside and self._active and self._active.auto and self._active.mode.id == "noche":
            await self.exit()


class GainPlayer:
    """El reproductor de la voz de Nyx con el volumen del modo (las alarmas usan el de
    siempre, sin tocar: suenan igual en cualquier modo)."""

    def __init__(self, player: Any, gain: Callable[[], float]) -> None:
        self._player = player
        self._gain = gain

    def enqueue(self, samples: Any) -> None:
        gain = self._gain()
        self._player.enqueue(samples * gain if gain != 1.0 else samples)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._player, name)
