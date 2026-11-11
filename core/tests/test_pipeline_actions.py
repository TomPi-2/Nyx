"""Bucle de voz con el router rápido y el ejecutor (bloque 3a)."""

from nyx.brain.base import LLMToolCall
from nyx.brain.router import Miss, Route
from nyx.events import NyxState, TextEntered
from nyx.executor import ToolCall, with_waits
from nyx.index.service import SystemIndex
from nyx.pipeline import Mode
from nyx.tools.base import ToolResult
from nyx.tools.registry import default_registry
from tests.test_pipeline import Harness


class FakeExecutor:
    def __init__(self, results: list[ToolResult]) -> None:
        self.results = results
        self.calls: list[ToolCall] = []
        self.confirm = None
        self.invalid: list[str] = []  # respuestas sucesivas de check()
        self.registry = default_registry()

    def check(self, calls: list[ToolCall]) -> str:
        return self.invalid.pop(0) if self.invalid else ""

    async def run_plan(
        self, calls: list[ToolCall], *, phrase: str = "", voice: bool = False
    ) -> list[ToolResult]:
        self.calls += calls
        return self.results


def with_router(h: Harness, routed: Route | Miss | None, results: list[ToolResult]) -> FakeExecutor:
    executor = FakeExecutor(results)
    h.p.router = lambda text: routed
    h.p.executor = executor  # type: ignore[assignment]
    return executor


OPEN = Route([ToolCall("open_app", {"name": "Spotify"})], "open")


async def test_voice_action_is_silent_and_skips_llm() -> None:
    h = Harness()
    executor = with_router(h, OPEN, [ToolResult(ok=True, message="Abriendo Spotify")])
    await h.say()
    await h.p.wait_idle()
    assert executor.calls == OPEN.calls
    assert h.llm.requests == []  # sin LLM
    assert h.tts.said == [] and h.bubbles == []  # éxito: ni voz ni burbuja
    assert h.p.mode is Mode.LISTENING  # ventana de seguimiento («y ahora…»)
    await h.p.close()


async def test_action_with_result_shows_bubble() -> None:
    h = Harness()
    result = ToolResult(ok=True, message="ok", display="Captura guardada", secondary="copiada")
    with_router(h, Route([ToolCall("screenshot")], "screenshot"), [result])
    await h.bus.publish(TextEntered("haz una captura"))
    await h.p.wait_idle()
    assert h.bubbles == [("Captura guardada", "copiada")]
    assert h.tts.said == []
    await h.p.close()


async def test_failed_action_is_explained() -> None:
    h = Harness()
    with_router(h, OPEN, [ToolResult.fail("No he podido abrir Spotify")])
    await h.say()
    await h.p.wait_idle()
    assert NyxState.ERROR in h.states
    assert h.bubbles[-1][0] == "No he podido abrir Spotify"
    assert h.tts.said == ["No he podido abrir Spotify"]  # por voz, se dice
    await h.p.close()


async def test_miss_goes_to_llm_with_candidates(index: SystemIndex) -> None:
    # SPEC sección 6: si el router duda, pasa al LLM con los candidatos como pista.
    h = Harness()
    miss = Miss("spotifai premium", index.resolve("spotify"))
    with_router(h, miss, [])
    await h.bus.publish(TextEntered("abre spotifai premium"))
    await h.p.wait_idle()
    context = h.llm.requests[0][-1].content
    assert "«spotifai premium» no coincide" in context and "Spotify" in context
    await h.p.close()


async def test_weak_miss_says_not_found_without_llm(index: SystemIndex) -> None:
    # Nada se parece de verdad: respuesta directa, sin preguntar al LLM.
    h = Harness()
    miss = Miss("xyzzy", index.resolve("xyzzy"))
    with_router(h, miss, [])
    await h.bus.publish(TextEntered("abre xyzzy"))
    await h.p.wait_idle()
    assert h.llm.requests == []
    assert any("No encuentro" in display for display, _ in h.bubbles)
    await h.p.close()


async def test_no_route_falls_back_to_llm() -> None:
    h = Harness()
    executor = with_router(h, None, [])
    await h.bus.publish(TextEntered("¿Cómo se dice hola en alemán?"))
    await h.p.wait_idle()
    assert executor.calls == []
    assert len(h.llm.requests) == 1
    await h.p.close()


async def test_llm_plan_runs_through_executor_with_waits() -> None:
    h = Harness()
    executor = with_router(h, None, [ToolResult(ok=True, message="ok")])
    h.llm.plans = [
        [
            LLMToolCall("open_app", {"name": "Spotify"}),
            LLMToolCall("window_layout", {"action": "maximize", "name": "Spotify"}),
        ]
    ]
    await h.bus.publish(TextEntered("abre Spotify y maximízalo"))
    await h.p.wait_idle()
    assert [c.name for c in executor.calls] == ["open_app", "wait_for_window", "window_layout"]
    assert h.tts.said == []  # acción: sin voz
    # La memoria corta sabe qué se hizo («y ahora ciérralo»).
    assert h.p.brain.memory.action() == "ok"  # lo último hecho, como contexto (6.02)
    await h.p.close()


async def test_invalid_plan_is_retried_once_with_the_error() -> None:
    h = Harness()
    executor = with_router(h, None, [ToolResult(ok=True, message="ok")])
    executor.invalid = ["open_app: name: Field required"]
    h.llm.plans = [[LLMToolCall("open_app", {})], [LLMToolCall("open_app", {"name": "Spotify"})]]
    await h.bus.publish(TextEntered("abre Spotify"))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 2
    retry_context = h.llm.requests[1][-1].content
    assert "no era válida" in retry_context
    assert executor.calls == [ToolCall("open_app", {"name": "Spotify"})]
    await h.p.close()


def test_with_waits_only_when_next_step_needs_the_window() -> None:
    plan = [ToolCall("open_app", {"name": "Spotify"}), ToolCall("set_volume", {"level": 30})]
    assert with_waits(plan) == plan
    plan2 = [
        ToolCall("open_app", {"name": "Discord"}),
        ToolCall("focus_window", {"name": "Discord"}),
    ]
    assert [c.name for c in with_waits(plan2)] == ["open_app", "wait_for_window", "focus_window"]


async def test_tool_names_never_reach_the_bubble_or_the_voice() -> None:
    # 6.03: «[set_alarm | establece una alarma]» en la burbuja y «listalarms, …» en voz.
    h = Harness(speak_typed=True)
    with_router(h, None, [ToolResult(ok=True, message="ok")])
    h.llm.replies = ["[set_alarm | establece una alarma]\n¿A qué hora quieres la alarma?"]
    await h.bus.publish(TextEntered("pon una alarma"))
    await h.p.wait_idle()
    assert h.bubbles[-1][0] == "¿A qué hora quieres la alarma?"
    assert h.tts.said == ["¿A qué hora quieres la alarma?"]
    h.llm.replies = ["[list_alarms | dices las alarmas]\nlistalarms, dices las alarmas"]
    await h.bus.publish(TextEntered("qué alarmas hay"))
    await h.p.wait_idle()
    assert h.tts.said[-1] == "No he podido hacerlo."
    assert all("list" not in b[0] and "set_alarm" not in b[0] for b in h.bubbles)
    await h.p.close()
