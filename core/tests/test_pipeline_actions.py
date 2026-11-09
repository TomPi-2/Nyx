"""Bucle de voz con el router rápido y el ejecutor (bloque 3a)."""

from nyx.brain.router import Miss, Route
from nyx.events import NyxState, TextEntered
from nyx.executor import ToolCall
from nyx.index.service import SystemIndex
from nyx.pipeline import Mode
from nyx.tools.base import ToolResult
from tests.test_pipeline import Harness


class FakeExecutor:
    def __init__(self, results: list[ToolResult]) -> None:
        self.results = results
        self.calls: list[ToolCall] = []

    async def run_plan(self, calls: list[ToolCall]) -> list[ToolResult]:
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


async def test_miss_says_not_found_with_suggestion(index: SystemIndex) -> None:
    h = Harness()
    miss = Miss("spotifai premium", index.resolve("spotify"))
    with_router(h, miss, [])
    await h.bus.publish(TextEntered("abre spotifai premium"))
    await h.p.wait_idle()
    assert h.bubbles[-1] == ("No encuentro «spotifai premium»", "¿quizá Spotify?")
    assert h.tts.said == []  # escrito: sin voz
    assert h.llm.requests == []
    await h.p.close()


async def test_no_route_falls_back_to_llm() -> None:
    h = Harness()
    executor = with_router(h, None, [])
    await h.bus.publish(TextEntered("¿Cómo se dice hola en alemán?"))
    await h.p.wait_idle()
    assert executor.calls == []
    assert len(h.llm.requests) == 1
    await h.p.close()
