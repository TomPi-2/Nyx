"""8.10 y 8.11: modos de Nyx (Trabajo, Noche, Privacidad y los de extensiones)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pytest

from nyx.brain.router import Route, route
from nyx.bus import EventBus
from nyx.ext.content import ModeAction, ModeSpec
from nyx.game.detector import ForegroundChanged, GameStateChanged
from nyx.index.service import SystemIndex
from nyx.modes.manager import GainPlayer, ModeChanged, ModeManager
from nyx.safety.undo import Undo
from nyx.settings.model import Settings
from nyx.tools.base import ToolContext, ToolResult
from nyx.tools.mode_tool import ModeParams, ModeTool


class Tools:
    """Herramientas falsas: apuntan lo que se hace y lo que se deshace."""

    def __init__(self) -> None:
        self.done: list[tuple[str, dict[str, Any]]] = []
        self.undone: list[str] = []

    async def __call__(self, name: str, args: dict[str, Any]) -> ToolResult:
        self.done.append((name, args))

        async def back() -> str:
            self.undone.append(name)
            return "deshecho"

        return ToolResult(ok=True, message="hecho", undo=Undo(name, back))


def make(
    settings: Settings | None = None,
    *,
    playing: list[bool] | None = None,
    now: list[datetime] | None = None,
) -> tuple[ModeManager, Tools, EventBus, list[ModeChanged]]:
    bus = EventBus()
    tools = Tools()
    flags = playing if playing is not None else [False]
    clock = now if now is not None else [datetime(2026, 11, 17, 12, 0)]
    modes = ModeManager(
        bus, settings or Settings(), tools, playing=lambda: flags[0], clock=lambda: clock[0]
    )
    changes: list[ModeChanged] = []

    async def seen(e: ModeChanged) -> None:
        changes.append(e)

    bus.subscribe(ModeChanged, seen)
    return modes, tools, bus, changes


async def test_work_opens_mutes_and_undoes_on_exit() -> None:
    settings = Settings()
    settings.modes.work_apps = ["Word", "Chrome"]
    modes, tools, _, changes = make(settings)
    assert await modes.enter("trabajo") == "Modo Trabajo activado"
    assert [n for n, _ in tools.done] == [
        "open_app", "open_app", "window_layout", "window_layout", "set_volume", "set_volume"
    ]  # fmt: skip
    assert modes.voice_gain() == 0.6 and modes.wake_on() and not modes.private()
    assert await modes.exit() == "He salido del modo Trabajo"
    assert tools.undone == [n for n, _ in reversed(tools.done)]  # al revés
    assert [c.mode for c in changes] == ["trabajo", None]


async def test_night_keeps_alarms_and_opens_settings() -> None:
    modes, tools, _, _ = make()
    await modes.enter("noche")
    assert tools.done[0] == ("set_volume", {"level": 20})
    assert [a["page"] for n, a in tools.done[1:]] == ["luz nocturna", "notificaciones"]
    assert modes.voice_gain() == 0.5


async def test_privacy_cuts_the_network_and_the_wake_word() -> None:
    settings = Settings()
    settings.modes.privacy_hide = ["Discord"]
    modes, tools, _, _ = make(settings)
    await modes.enter("privacidad")
    assert tools.done == [("hide_apps", {"action": "hide", "app": "Discord"})]
    assert modes.offline() and modes.private() and not modes.wake_on()
    for tool in ("web_search", "open_url", "get_weather", "install_app", "nyx_update"):
        assert modes.blocked(tool) == "En modo Privacidad no uso internet"
    assert modes.blocked("read_text") is None and modes.blocked("clipboard") is None
    # Cambiar de modo sale del anterior (las apps vuelven).
    await modes.enter("trabajo")
    assert tools.undone == ["hide_apps"] and not modes.offline()


async def test_game_comes_first() -> None:
    playing = [True]
    modes, tools, bus, _ = make(playing=playing)
    assert await modes.enter("trabajo") == "Al acabar la partida paso a modo Trabajo"
    assert modes.current is None and tools.done == []
    playing[0] = False
    await bus.publish(GameStateChanged(False, "juego.exe"))
    assert modes.current is not None and modes.current.id == "trabajo"


async def test_automatic_ones_are_off_by_default() -> None:
    now = [datetime(2026, 11, 17, 23, 30)]
    modes, _, bus, _ = make(now=now)
    await modes.check_night()
    await bus.publish(ForegroundChanged("code.exe", "VS Code"))
    assert modes.current is None
    settings = Settings()
    settings.modes.night_from = "23:00"
    settings.modes.work_auto_apps = ["code"]
    modes, _, bus, _ = make(settings, now=now)
    await modes.check_night()
    assert modes.current is not None and modes.current.id == "noche"
    now[0] = datetime(2026, 11, 18, 7, 5)
    await modes.check_night()
    assert modes.current is None  # entró sola, sale sola
    await bus.publish(ForegroundChanged("Code.exe", "proyecto - Visual Studio Code"))
    assert modes.current is not None and modes.current.id == "trabajo"


async def test_extension_modes() -> None:
    modes, tools, _, _ = make()
    spec = ModeSpec(
        name="Estudio",
        voice="baja",
        actions=(ModeAction(tool="set_volume", args={"level": 25}),),
    )
    modes.ext_source = lambda: {"autor.estudio/estudio": spec, "malo/trabajo": spec}
    assert modes.find("modo estudio") is not None
    await modes.enter("autor.estudio/estudio")
    assert tools.done == [("set_volume", {"level": 25})]
    assert modes.voice_gain() == 0.6 and modes.wake_on() and not modes.offline()
    assert modes.all_modes()["trabajo"].extension is None  # los de Nyx no se pisan


def test_gain_player_only_lowers_nyx() -> None:
    class Player:
        sample_rate = 22050

        def __init__(self) -> None:
            self.got: list[float] = []

        def enqueue(self, samples: Any) -> None:
            self.got.append(float(samples.max()))

    raw = Player()
    gain = [0.5]
    voice = GainPlayer(raw, lambda: gain[0])
    voice.enqueue(np.ones(4, dtype=np.float32))
    raw.enqueue(np.ones(4, dtype=np.float32))  # las alarmas, sin tocar
    assert raw.got == [0.5, 1.0] and voice.sample_rate == 22050


async def test_tool_and_router(ctx: ToolContext, index: SystemIndex) -> None:
    modes, _, _, _ = make()
    ctx.modes = modes
    tool = ModeTool()
    assert (await tool.run(ModeParams(action="enter", mode="nocturno"), ctx)).ok
    status = await tool.run(ModeParams(action="status"), ctx)
    assert status.message == "Estoy en modo Noche."
    assert (await tool.run(ModeParams(action="exit"), ctx)).message == "He salido del modo Noche."
    for text, args in (
        ("Modo trabajo", {"action": "enter", "mode": "trabajo"}),
        ("Activa el modo privacidad", {"action": "enter", "mode": "privacidad"}),
        ("Sal del modo noche", {"action": "exit"}),
        ("¿En qué modo estás?", {"action": "status"}),
    ):
        routed = route(text, index)
        assert isinstance(routed, Route) and routed.calls[0].arguments == args, text
    routed = route("Activa el modo avión", index)
    assert not (isinstance(routed, Route) and routed.calls[0].name == "mode")


async def test_bridge_hides_content_in_privacy(monkeypatch: pytest.MonkeyPatch) -> None:
    from nyx.bridge.server import UIBridge
    from nyx.events import BubbleShown

    bridge = UIBridge(EventBus(), "token")
    sent: list[Any] = []

    async def broadcast(msg: Any) -> None:
        sent.append(msg)

    monkeypatch.setattr(bridge, "broadcast", broadcast)
    bridge.private = lambda: True
    await bridge._on_bubble(BubbleShown(display="Cita apuntada", secondary="Dentista · jueves"))
    await bridge._on_bubble(BubbleShown(display="¿Borro 3 archivos?", kind="confirm"))
    assert (sent[0].display, sent[0].secondary) == ("Hecho", None)
    assert sent[1].display == "¿Borro 3 archivos?"  # lo que se confirma, sí
