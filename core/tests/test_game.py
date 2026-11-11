"""Modo partida (SPEC sección 9), todo simulado: no se abre ningún juego."""

from pathlib import Path

import pytest

from nyx.bus import EventBus
from nyx.events import BubbleShown
from nyx.executor import Executor, ToolCall
from nyx.game.controller import GameController
from nyx.game.detector import GameDetector, GameStateChanged, Probe, looks_like_game
from nyx.game.policy import GameGate
from nyx.safety.action_log import ActionLog
from nyx.settings.model import GameSettings
from nyx.tools.base import GamePolicy, ToolContext
from nyx.tools.registry import default_registry


def no_game_window(hwnd: int, process: str, games: set[str]) -> bool:
    return False


def probe(process: str, d3d: bool = False) -> Probe:
    return Probe(process, "título", 1, d3d)


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (probe("valorant-win64-shipping.exe"), True),  # juego conocido
        (probe("hollow_knight.exe", d3d=True), True),  # pantalla completa Direct3D
        (probe("chrome.exe", d3d=True), False),  # un vídeo a pantalla completa no es partida
        (probe("code.exe"), False),
        (probe("mijuego.exe"), True),  # lista «siempre» del usuario
        (probe("valorant-win64-shipping.exe", d3d=True), True),
        (probe("emulador.exe", d3d=True), False),  # lista «nunca» del usuario
    ],
)
def test_looks_like_game(p: Probe, expected: bool) -> None:
    got = looks_like_game(
        p,
        always=frozenset({"mijuego.exe"}),
        never=frozenset({"emulador.exe"}),
        game_processes=frozenset(),
        is_game_window=no_game_window,
    )
    assert got is expected


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


async def test_detector_enters_at_once_and_leaves_after_hysteresis() -> None:
    bus, clock = EventBus(), Clock()
    seen: list[GameStateChanged] = []

    async def keep(e: GameStateChanged) -> None:
        seen.append(e)

    bus.subscribe(GameStateChanged, keep)
    current = [probe("valorant-win64-shipping.exe")]
    detector = GameDetector(
        bus, read=lambda: current[0], clock=clock, is_game_window=no_game_window,
        mode=lambda: "voice",
    )  # fmt: skip
    assert await detector.check()
    assert seen == [GameStateChanged(True, "valorant-win64-shipping.exe", "título", "voice")]
    current[0] = probe("discord.exe")  # Alt+Tab
    clock.t = 3.0
    assert await detector.check()  # aún dentro: 3 s < 5 s
    current[0] = probe("valorant-win64-shipping.exe")
    clock.t = 4.0
    assert await detector.check()
    current[0] = probe("explorer.exe")
    clock.t = 6.0
    assert await detector.check()
    clock.t = 9.5
    assert not await detector.check()  # 5,5 s sin juego: fin
    assert seen[-1].active is False and len(seen) == 2


def gate(**kw: object) -> GameGate:
    g = GameGate(GameSettings(**kw))  # type: ignore[arg-type]
    g.active = True
    return g


def test_policies() -> None:
    reg = default_registry()
    g = gate()
    assert g.policy_for(reg.get("set_volume")) is GamePolicy.ALLOWED  # type: ignore[arg-type]
    assert g.policy_for(reg.get("open_app")) is GamePolicy.DEFERRED  # type: ignore[arg-type]
    assert g.policy_for(reg.get("send_hotkey")) is GamePolicy.BLOCKED  # type: ignore[arg-type]
    # Lo rojo se difiere salvo en «normal» (la confirmación no se vería).
    delete = reg.get("delete_files")
    assert g.policy_for(delete) is not GamePolicy.ALLOWED  # type: ignore[arg-type]
    # El usuario puede mover una herramienta de columna.
    custom = gate(policies={"open_app": "allowed"})
    assert custom.policy_for(reg.get("open_app")) is GamePolicy.ALLOWED  # type: ignore[arg-type]
    g.active = False
    assert g.policy_for(reg.get("send_hotkey")) is GamePolicy.ALLOWED  # type: ignore[arg-type]


def read_logs(folder: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in folder.glob("*.jsonl"))


async def test_executor_defers_and_blocks(ctx: ToolContext, tmp_path: Path) -> None:
    g = gate()
    ex = Executor(default_registry(), ctx, action_log=ActionLog(tmp_path), game=g)
    deferred = await ex.run(ToolCall("open_app", {"name": "Discord"}), phrase="abre discord")
    assert (
        deferred.ok and deferred.data["deferred"] and deferred.display == "Al terminar la partida"
    )
    assert [d.call.name for d in g.queue] == ["open_app"]
    blocked = await ex.run(ToolCall("send_hotkey", {"keys": "ctrl+t"}))
    assert not blocked.ok and "En partida" in blocked.message
    assert '"deferred"' in read_logs(tmp_path)


async def test_controller_runs_deferred_after_game(ctx: ToolContext) -> None:
    bus = EventBus()
    g = gate()
    priorities: list[bool] = []

    class FakeExecutor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def run(self, call: ToolCall, *, phrase: str = "", voice: bool = False) -> object:
            from nyx.tools.base import ToolResult

            self.calls.append(call.name)
            return ToolResult(ok=True, message="ok")

    executor = FakeExecutor()
    controller = GameController(
        bus,
        g,
        executor,
        set_priority=priorities.append,  # type: ignore[arg-type]
        after_game_s=0,
    )
    bubbles: list[BubbleShown] = []

    async def keep(e: BubbleShown) -> None:
        bubbles.append(e)

    bus.subscribe(BubbleShown, keep)
    g.active = False
    await bus.publish(GameStateChanged(True, "valorant-win64-shipping.exe"))
    assert g.active and priorities == [True]
    g.defer(ToolCall("open_app", {"name": "Discord"}), "abre discord", "open app Discord")
    await bus.publish(GameStateChanged(False, "valorant-win64-shipping.exe"))
    assert not g.active and priorities == [True, False]
    assert executor.calls == ["open_app"] and g.queue == []
    assert bubbles[-1].display == "Al terminar la partida"
    await controller.close()


async def test_controller_unloads_llm_after_a_while() -> None:
    bus = EventBus()
    g = gate(unload_llm_after_min=1)
    events: list[str] = []

    async def unload() -> None:
        events.append("unload")

    async def reload() -> None:
        events.append("reload")

    controller = GameController(
        bus, g, None, unload_llm=unload, reload_llm=reload, set_priority=lambda low: None
    )
    await controller._unload_later(0)  # sin esperar el minuto
    await bus.publish(GameStateChanged(False, "x"))
    assert events == ["unload", "reload"]
    await controller.close()


async def test_pipeline_ignores_wake_word_in_game_when_off() -> None:
    from tests.test_pipeline import WAKE, Harness

    h = Harness()
    h.p.game = gate(mode="off")
    await h.feed(WAKE)
    assert h.states == [] and h.p.mode.name == "IDLE"
    await h.p.close()


async def test_detector_reports_the_game_monitor() -> None:
    """v11: el monitor del juego va en el aviso; si el juego cambia de monitor, se avisa."""
    bus, clock = EventBus(), Clock()
    seen: list[GameStateChanged] = []

    async def keep(e: GameStateChanged) -> None:
        seen.append(e)

    bus.subscribe(GameStateChanged, keep)
    current = [Probe("valorant-win64-shipping.exe", "título", 1, True, r"\.\DISPLAY1")]
    detector = GameDetector(
        bus, read=lambda: current[0], clock=clock, is_game_window=no_game_window
    )
    assert await detector.check()
    assert await detector.check()  # mismo monitor: no se repite el aviso
    current[0] = Probe("valorant-win64-shipping.exe", "título", 1, True, r"\.\DISPLAY2")
    clock.t = 1.0
    assert await detector.check()
    assert [e.monitor for e in seen] == [r"\.\DISPLAY1", r"\.\DISPLAY2"]
    assert all(e.active for e in seen)


async def test_nonsense_is_not_deferred(
    ctx: ToolContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ERRORES.md, 2026-11-11: «muéstrame los FPS en el Rocket League» se dejaba para después
    # como focus_window y fallaba al terminar. Ahora se dice en el momento.
    from nyx.winapi import windows

    monkeypatch.setattr(windows, "find_windows", lambda name, process=None: [])
    g = gate()
    ex = Executor(default_registry(), ctx, action_log=ActionLog(tmp_path), game=g)
    result = await ex.run(ToolCall("focus_window", {"name": "los fps en el rocket league"}))
    assert not result.ok and "No veo" in result.message
    assert g.queue == []


def test_queue_survives_restart_and_can_be_cancelled(tmp_path: Path) -> None:
    path = tmp_path / "game-queue.json"
    g = GameGate(GameSettings(), path=path)
    g.defer(ToolCall("open_app", {"name": "Discord"}), "abre discord", "abrir Discord")
    g.defer(ToolCall("open_nyx_settings", {}), "abre tus ajustes", "abrir mis ajustes", voice=True)
    again = GameGate(GameSettings(), path=path)
    again.load()
    assert [d.summary for d in again.queue] == ["abrir Discord", "abrir mis ajustes"]
    assert again.queue[1].voice and again.queue[1].call.name == "open_nyx_settings"
    assert [d.summary for d in again.cancel(0)] == ["abrir Discord"]
    assert len(again.cancel()) == 1 and again.queue == []
    third = GameGate(GameSettings(), path=path)
    third.load()
    assert third.queue == []


async def test_pending_tool_lists_and_cancels(ctx: ToolContext) -> None:
    from nyx.tools.pending import Pending, PendingParams

    g = gate()
    ctx.game = g
    tool = Pending()
    empty = await tool.run(PendingParams(), ctx)
    assert empty.ok and "nada" in empty.message
    g.defer(ToolCall("open_app", {"name": "Discord"}), "abre discord", "abrir Discord")
    g.defer(ToolCall("open_nyx_settings", {}), "abre tus ajustes", "abrir mis ajustes")
    listed = await tool.run(PendingParams(), ctx)
    assert "1. abrir Discord" in listed.message and "2. abrir mis ajustes" in listed.message
    gone = await tool.run(PendingParams(action="cancel", which="ajustes"), ctx)
    assert gone.ok and [d.summary for d in g.queue] == ["abrir Discord"]
    await tool.run(PendingParams(action="cancel"), ctx)
    assert g.queue == []


async def test_summary_is_spoken_when_asked_by_voice() -> None:
    from nyx.events import Announce
    from nyx.tools.base import ToolResult

    bus = EventBus()
    g = gate()

    class FakeExecutor:
        async def run(self, call: ToolCall, *, phrase: str = "", voice: bool = False) -> object:
            return ToolResult(ok=call.name == "open_app", message="")

    controller = GameController(
        bus,
        g,
        FakeExecutor(),  # type: ignore[arg-type]
        set_priority=lambda _: None,
        after_game_s=0,
    )
    said: list[str] = []
    bubbles: list[BubbleShown] = []

    async def on_say(e: Announce) -> None:
        said.append(e.text)

    async def on_bubble(e: BubbleShown) -> None:
        bubbles.append(e)

    bus.subscribe(Announce, on_say)
    bus.subscribe(BubbleShown, on_bubble)
    g.defer(ToolCall("open_app", {"name": "Discord"}), "abre discord", "abrir Discord", voice=True)
    g.defer(ToolCall("focus_window", {"name": "x"}), "ve a x", "ir a x")
    await bus.publish(GameStateChanged(False, "rocketleague.exe"))
    assert said == ["Ya he hecho lo pendiente: abrir Discord. No he podido ir a x."]
    assert bubbles[-1].secondary == "Hecho: abrir Discord · No pude: ir a x"
    await controller.close()


async def test_same_action_is_not_queued_twice(ctx: ToolContext, tmp_path: Path) -> None:
    # ERRORES.md, 2026-11-11: «abre tus ajustes» dos veces abría dos ventanas al terminar.
    g = gate()
    ex = Executor(default_registry(), ctx, action_log=ActionLog(tmp_path), game=g)
    first = await ex.run(ToolCall("open_nyx_settings", {}))
    second = await ex.run(ToolCall("open_nyx_settings", {}))
    assert first.ok and second.ok and second.message == "Ya lo tengo pendiente"
    assert len(g.queue) == 1
