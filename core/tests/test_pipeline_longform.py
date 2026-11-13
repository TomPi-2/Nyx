"""Panel largo en el pipeline (6.28): lectura al ritmo de la voz, órdenes, notas y recetas."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from nyx.events import (
    ActionChosen,
    BubbleHidden,
    BubbleShown,
    PanelNote,
    ReadingAppended,
    TextEntered,
)
from nyx.executor import ToolCall
from nyx.pipeline import _Marks
from nyx.tools.base import ToolResult
from nyx.tools.registry import default_registry
from tests.test_pipeline import FakeLLM, Harness

SENTENCES = [f"Esta es la frase número {i} de la explicación." for i in range(1, 7)]
LONG = "[Rayleigh | por qué el cielo es azul]\n" + " ".join(SENTENCES)


class Seen:
    """Lo que el pipeline publica para la interfaz."""

    def __init__(self, h: Harness) -> None:
        self.shown: list[BubbleShown] = []
        self.readings: list[ReadingAppended] = []
        self.notes: list[PanelNote] = []
        self.hidden = 0

        async def shown(e: BubbleShown) -> None:
            self.shown.append(e)

        async def reading(e: ReadingAppended) -> None:
            self.readings.append(e)

        async def note(e: PanelNote) -> None:
            self.notes.append(e)

        async def hidden(_: BubbleHidden) -> None:
            self.hidden += 1

        h.bus.subscribe(BubbleShown, shown)
        h.bus.subscribe(ReadingAppended, reading)
        h.bus.subscribe(PanelNote, note)
        h.bus.subscribe(BubbleHidden, hidden)

    @property
    def long(self) -> BubbleShown:
        return next(b for b in self.shown if b.kind == "long")


class NoteExecutor:
    """Lo justo para guardar y deshacer una nota."""

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self.confirm = None
        self.registry = default_registry()

    async def run(self, call: ToolCall, *, phrase: str = "", voice: bool = False) -> ToolResult:
        self.calls.append(call)
        if call.name == "undo":
            return ToolResult(ok=True, message="Nota enviada a la papelera")
        return ToolResult(ok=True, message="Guardada", data={"undo_id": "u1"})


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def ask(h: Harness, text: str) -> None:
    await h.bus.publish(TextEntered(text))
    await h.p.wait_idle()
    await settle()


async def test_spoken_explanation_is_written_as_it_is_said() -> None:
    h = Harness(llm=FakeLLM(LONG), speak_typed=True)
    seen = Seen(h)
    await ask(h, "¿por qué el cielo es azul?")
    long = seen.long
    assert long.kind == "long" and long.reading and long.display == "Rayleigh"
    assert [a.id for a in long.actions] == ["long-save", "long-copy", "long-close"]
    # Lo ya dicho antes de pasar al panel largo, de golpe; lo demás, frase a frase.
    assert " ".join(r.text for r in seen.readings) == " ".join(SENTENCES)
    assert seen.readings[0].duration_s == 0.0 or len(seen.readings) == len(SENTENCES)
    assert all(r.duration_s > 0 for r in seen.readings[1:])
    assert h.tts.said == SENTENCES  # la voz lo lee entero
    # No se va solo mientras se lee.
    assert h.p._long_open and h.p._bubble_timer is None
    await h.p.close()


async def test_written_explanation_comes_all_at_once() -> None:
    h = Harness(llm=FakeLLM(LONG))
    seen = Seen(h)
    await ask(h, "¿por qué el cielo es azul?")
    long = seen.long
    assert not long.reading and long.text == " ".join(SENTENCES)
    assert seen.readings == [] and h.tts.said == []
    await h.p.close()


async def test_short_answers_stay_as_they_were() -> None:
    h = Harness()
    seen = Seen(h)
    await ask(h, "¿Cómo se dice hola en alemán?")
    assert [b.kind for b in seen.shown] == ["response"]
    await h.p.close()


async def test_copy_and_close_by_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr("nyx.pipeline.write_clipboard_text", copied.append)
    h = Harness(llm=FakeLLM(LONG))
    seen = Seen(h)
    await ask(h, "¿por qué el cielo es azul?")
    asked = len(h.llm.requests)

    await ask(h, "cópialo")
    assert copied and copied[0].startswith("Rayleigh\n\nEsta es la frase número 1")
    assert [n.text for n in seen.notes] == ["Copiado"]

    await ask(h, "Cierra el panel")
    assert seen.hidden == 1 and not h.p._long_open
    assert len(h.llm.requests) == asked  # nada de esto pasa por el modelo

    # Sin panel, «ciérralo» vuelve a ser una petición normal.
    await ask(h, "ciérralo")
    assert len(h.llm.requests) == asked + 1
    await h.p.close()


async def test_save_and_undo_with_the_buttons() -> None:
    h = Harness(llm=FakeLLM(LONG))
    seen = Seen(h)
    executor = NoteExecutor()
    h.p.executor = executor  # type: ignore[assignment]
    await ask(h, "¿por qué el cielo es azul?")

    await h.bus.publish(ActionChosen("long-save"))
    await settle()
    call = executor.calls[0]
    assert call.name == "save_note" and call.arguments["title"] == "Rayleigh"
    assert call.arguments["text"].startswith("Rayleigh\nGuardada el ")
    assert seen.notes[-1] == PanelNote("Nota guardada en Documentos › Notas de Nyx", "long-undo-u1")

    await h.bus.publish(ActionChosen("long-undo-u1"))
    await settle()
    assert executor.calls[-1] == ToolCall("undo", {"id": "u1"})
    # Sin Deshacer: la interfaz vuelve a enseñar los botones de siempre.
    assert seen.notes[-1] == PanelNote("Nota enviada a la papelera")
    assert h.p._long_open  # el panel sigue abierto
    await h.p.close()


async def test_yes_saves_only_after_the_offer() -> None:
    h = Harness(llm=FakeLLM(LONG))
    executor = NoteExecutor()
    h.p.executor = executor  # type: ignore[assignment]
    await ask(h, "¿por qué el cielo es azul?")
    asked = len(h.llm.requests)

    await ask(h, "sí")  # sin oferta (una explicación): no es para el panel
    assert executor.calls == [] and len(h.llm.requests) == asked + 1

    await ask(h, "¿por qué el cielo es azul?")
    h.p._offer_until = h.now + 60  # como tras una receta
    await ask(h, "sí")
    assert [c.name for c in executor.calls] == ["save_note"]
    await h.p.close()


RECIPE_JSON: dict[str, Any] = {
    "tipo": "receta",
    "titulo": "Tortilla de patatas",
    "secciones": [
        {"titulo": "Ingredientes", "elementos": ["6 huevos", "4 patatas"], "numerada": False},
        {"titulo": "Pasos", "elementos": ["Pela.", "Cuaja."], "numerada": True},
    ],
    "voz": "Lleva dos ingredientes y dos pasos.",
}


async def test_recipe_from_the_web_is_shown_structured_and_offered() -> None:
    h = Harness(speak_typed=True)
    seen = Seen(h)
    h.llm.replies = [json.dumps(RECIPE_JSON)]
    marks = _Marks(end=0.0, phrase="busca una receta de tortilla de patatas")
    calls = [ToolCall("web_search", {"query": "receta tortilla de patatas"})]
    results = [
        ToolResult(
            ok=True,
            external="[pequerecetas.com] Tortilla: " + "texto " * 100,
            secondary="pequerecetas.com · abc.es",
            data={"how": "resumen"},
        )
    ]
    assert await h.p._maybe_structured(calls, results, marks)
    long = seen.long
    assert long.display == "Tortilla de patatas" and long.secondary == "pequerecetas.com · abc.es"
    assert [(s.title, s.ordered) for s in long.sections] == [
        ("Ingredientes", False),
        ("Pasos", True),
    ]
    assert h.tts.said == ["Lleva dos ingredientes y dos pasos. ¿Te la guardo en una nota?"]
    assert h.p._offer_until > h.now
    await h.p.close()


async def test_no_structure_for_other_questions() -> None:
    h = Harness(speak_typed=True)
    marks = _Marks(end=0.0, phrase="busca quién inventó la imprenta")
    results = [ToolResult(ok=True, external="texto " * 100, secondary="es.wikipedia.org")]
    calls = [ToolCall("web_search", {"query": "inventor imprenta"})]
    assert not await h.p._maybe_structured(calls, results, marks)
    assert h.llm.requests == []  # ni siquiera se pregunta al modelo
    await h.p.close()
