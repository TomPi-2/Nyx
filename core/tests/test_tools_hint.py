"""Aviso de «esto se resuelve con herramientas» en el mensaje del usuario (6.21)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from nyx.brain.base import ChatMessage, LLMToolCall
from nyx.brain.prompts import SYSTEM, TOOLS_HINT
from nyx.brain.select import ToolSelector
from nyx.brain.service import Brain
from nyx.tools.registry import default_registry


class RecordingLLM:
    def __init__(self) -> None:
        self.asked: list[list[ChatMessage]] = []

    async def chat(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        self.asked.append(list(messages))
        yield "[vale | prueba]\nVale."


async def last_user_message(text: str, *, continuing: bool = False) -> ChatMessage:
    llm = RecordingLLM()
    brain = Brain(llm, selector=ToolSelector(default_registry()), tools_hint=True)  # type: ignore[arg-type]
    async for _ in brain.respond(text, continuing=continuing):
        pass
    return llm.asked[-1][-1]


async def test_state_questions_get_the_hint() -> None:
    for text in ("¿cuánto marca el crono?", "¿cuántos grados hará mañana?", "sube el brillo"):
        assert TOOLS_HINT in (await last_user_message(text)).content, text


async def test_no_hint_for_general_questions_or_about_nyx() -> None:
    for text in ("¿quién pintó las Meninas?", "¿qué puedes hacer?"):
        assert TOOLS_HINT not in (await last_user_message(text)).content, text


async def test_no_hint_in_another_turn_and_never_in_the_system_prompt() -> None:
    message = await last_user_message("¿cuánto marca el crono?", continuing=True)
    assert TOOLS_HINT not in message.content
    assert TOOLS_HINT not in SYSTEM  # la caché del prefijo no cambia
