"""«Dice que lo hace pero no lo hace» (registros del usuario, 2026-11-15).

Si el modelo contesta «Vale, la guardo en tus favoritos» sin llamar a nada, no se dice: se le
pide otra vez con herramientas y, si sigue sin actuar, Nyx dice la verdad.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from nyx.brain.base import ChatMessage, LLMToolCall
from nyx.brain.reply import SpokenDelta
from nyx.brain.service import HONEST, Brain, ReplyDone, ToolPlan, claims_action

TOOLS = [{"type": "function", "function": {"name": n}} for n in ("app_action", "obs_mute")]


class TwoTurnLLM:
    """Contesta con `turns[0]` la primera vez y con `turns[1]` la segunda."""

    def __init__(self, *turns: list[str | list[LLMToolCall]]) -> None:
        self.turns = list(turns)
        self.asked: list[Sequence[ChatMessage]] = []

    async def warmup(self, prefix: Sequence[ChatMessage] = (), *, tools: Any = ()) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def stream(self, messages: Any, *, schema: Any = None) -> AsyncIterator[str]:
        if False:
            yield ""

    async def chat(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AsyncIterator[str | list[LLMToolCall]]:
        self.asked.append(messages)
        for piece in self.turns.pop(0) if self.turns else []:
            yield piece


async def run(llm: TwoTurnLLM) -> list[object]:
    return [e async for e in Brain(llm, tools=TOOLS).respond("guarda esta canción en favoritos")]


def spoken(events: list[object]) -> str:
    return "".join(e.text for e in events if isinstance(e, SpokenDelta))


@pytest.mark.parametrize(
    "text",
    [
        "Vale, la guardo en tus favoritos.",
        "Vale, lo muteo de nuevo.",
        "Vale, te cierro los ajustes.",
        "Vale, pasa la canción.",
        "Deshago eso y te desmuto el micrófono.",
        "Vale, activo la extensión.",
        "Voy a bajarlo un poco.",
        "Bajamos el volumen.",
    ],
)
def test_claims(text: str) -> None:
    assert claims_action(text)


@pytest.mark.parametrize(
    "text",
    [
        "Vale, te propongo «El padrino». Es un clásico.",
        "Claro, en alemán se dice Hallo.",
        "Son las siete y media.",
        "Te cuento un chiste: ¿por qué…?",
        "Voy a contarte un chiste.",
    ],
)
def test_not_claims(text: str) -> None:
    assert not claims_action(text)


async def test_second_try_acts_and_nothing_false_is_said() -> None:
    call = [LLMToolCall("app_action", {"app": "Spotify", "action": "like"})]
    llm = TwoTurnLLM(["[Spotify | favoritos]\n", "Vale, la guardo ", "en tus favoritos."], [call])
    events = await run(llm)
    assert spoken(events) == ""  # el «vale» falso no se dice
    assert events[-1] == ToolPlan(call)
    assert "IMPORTANTE" in llm.asked[1][-1].content


async def test_if_it_still_cannot_it_says_the_truth() -> None:
    llm = TwoTurnLLM(["Vale, lo muteo ", "de nuevo."], ["Vale, lo muteo."])
    events = await run(llm)
    assert spoken(events) == HONEST
    assert isinstance(events[-1], ReplyDone)


async def test_an_honest_second_answer_is_used() -> None:
    llm = TwoTurnLLM(["Vale, te cierro ", "los ajustes."], ["Eso aún no sé hacerlo."])
    assert spoken(await run(llm)) == "Eso aún no sé hacerlo."


async def test_normal_replies_are_not_held_back() -> None:
    llm = TwoTurnLLM(["Vale, te propongo ", "«El padrino». ", "Es un clásico."])
    events = await run(llm)
    assert spoken(events) == "Vale, te propongo «El padrino». Es un clásico."
    assert len(llm.asked) == 1  # sin segundo intento


@pytest.mark.parametrize(
    "said",
    [
        "He borrado el contenido del portapapeles.",
        "He actualizado tu ciudad en la Configuración.",
        "Ya he guardado tu ciudad.",
        "Te he puesto el volumen al 30.",
    ],
)
def test_past_tense_claims(said: str) -> None:
    # Prueba del 2026-11-17: decía que lo había hecho sin llamar a ninguna herramienta.
    assert claims_action(said)


def test_past_tense_that_is_not_an_action() -> None:
    assert not claims_action("He visto que te gusta el rock.")
