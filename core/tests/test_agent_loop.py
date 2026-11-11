"""Bucle de agente (0.6, tarea 6.01): lo consultado vuelve al LLM para contarlo o seguir."""

from nyx.brain.agent import MAX_STEPS, AgentRun, observation
from nyx.brain.base import LLMToolCall
from nyx.brain.router import Route
from nyx.events import TextEntered
from nyx.executor import ToolCall
from nyx.tools.base import ToolResult
from tests.test_pipeline import Harness
from tests.test_pipeline_actions import with_router

LISTED = ToolResult(
    ok=True,
    message="3 archivos en Descargas",
    display="3 archivos",
    secondary="factura.pdf, foto.png…",
    data={"paths": [r"C:\D\factura.pdf", r"C:\D\foto.png", r"C:\D\notas.txt"]},
)
ANSWER = "[3 archivos | en Descargas]\nTienes una factura, una foto y unas notas."


async def test_query_from_the_router_is_told_by_the_llm() -> None:
    h = Harness(speak_typed=True)
    route = Route([ToolCall("list_files", {"folder": "Descargas"})], "list")
    with_router(h, route, [LISTED])
    h.llm.replies = [ANSWER]
    await h.bus.publish(TextEntered("¿qué hay en Descargas?"))
    await h.p.wait_idle()
    assert len(h.llm.requests) == 1
    asked = h.llm.requests[0][-1].content
    assert "factura (pdf), foto (png), notas (txt)" in asked and "<<<" in asked
    assert "C:\\" not in asked  # sin rutas: se leerían en voz alta
    assert "list_files" not in asked  # en español, sin nombres internos
    assert h.tts.said == ["Tienes una factura, una foto y unas notas."]
    assert h.bubbles[-1] == ("3 archivos", "en Descargas")
    await h.p.close()


async def test_two_steps_from_the_llm() -> None:
    h = Harness(speak_typed=True)
    executor = with_router(h, None, [LISTED])
    h.llm.plans = [
        [LLMToolCall("list_files", {"folder": "Descargas"})],
        [LLMToolCall("open_path", {"target": "factura.pdf"})],
    ]
    h.llm.replies = [ANSWER]
    await h.bus.publish(TextEntered("abre la factura que tengo en Descargas"))
    await h.p.wait_idle()
    # open_path no consulta: tras abrirla no se vuelve a preguntar al LLM.
    assert [c.name for c in executor.calls] == ["list_files", "open_path"]
    assert len(h.llm.requests) == 2
    await h.p.close()


async def test_actions_do_not_go_back_to_the_llm() -> None:
    h = Harness()
    with_router(h, Route([ToolCall("open_app", {"name": "Spotify"})], "open"), [LISTED])
    await h.bus.publish(TextEntered("abre Spotify"))
    await h.p.wait_idle()
    assert h.llm.requests == []  # lo frecuente sigue sin LLM
    await h.p.close()


async def test_loop_stops_after_max_steps() -> None:
    h = Harness()
    executor = with_router(h, None, [LISTED])
    # Un modelo que nunca termina: cada vez consulta otra carpeta.
    h.llm.plans = [
        [LLMToolCall("list_files", {"folder": f"Carpeta {i}"})] for i in range(MAX_STEPS + 3)
    ]
    await h.bus.publish(TextEntered("busca en todas partes"))
    await h.p.wait_idle()
    assert len(executor.calls) == MAX_STEPS + 1  # la primera + MAX_STEPS vueltas
    assert h.bubbles[-1][0] == "3 archivos"  # al final, lo último consultado
    await h.p.close()


async def test_repeating_the_same_call_ends_the_loop() -> None:
    h = Harness()
    executor = with_router(h, None, [LISTED])
    same = [LLMToolCall("list_files", {"folder": "Descargas"})]
    h.llm.plans = [same, same, same]
    await h.bus.publish(TextEntered("¿qué hay en Descargas?"))
    await h.p.wait_idle()
    assert len(executor.calls) == 1  # no se repite
    assert h.bubbles[-1] == ("3 archivos", "factura.pdf, foto.png…")
    await h.p.close()


async def test_memory_keeps_one_turn_per_request() -> None:
    h = Harness(speak_typed=True)
    with_router(h, None, [LISTED])
    h.llm.plans = [[LLMToolCall("list_files", {"folder": "Descargas"})]]
    h.llm.replies = [ANSWER]
    await h.bus.publish(TextEntered("¿qué hay en Descargas?"))
    await h.p.wait_idle()
    turns = h.p.brain.memory.messages()
    assert [m.role for m in turns] == ["user", "assistant"]
    assert "Tienes una factura" in turns[-1].content
    await h.p.close()


def test_observation_is_plain_spanish() -> None:
    text = observation(ToolCall("list_files", {"folder": "Descargas"}), LISTED)
    assert "{" not in text and "list_files" not in text
    assert text.startswith("- ") and "notas (txt)" in text and "en la carpeta D" in text
    many = ToolResult(ok=True, message="x", data={"paths": [f"f{i}.txt" for i in range(20)]})
    assert "y 5 más" in observation(ToolCall("find_files", {"query": "f"}), many)


def test_spoken_names() -> None:
    from nyx.brain.agent import spoken_name

    assert spoken_name(r"C:\x\factura_luz-2026.pdf") == "factura luz 2026 (pdf)"
    assert spoken_name("Nueva carpeta") == "Nueva carpeta"


def test_repeats() -> None:
    run = AgentRun()
    run.done.append((ToolCall("list_files", {"folder": "A"}), LISTED))
    assert run.repeats([ToolCall("list_files", {"folder": "A"})])
    assert not run.repeats([ToolCall("list_files", {"folder": "B"})])
    assert not run.repeats([])
