"""Respuestas largas y notas (6.28): órdenes al panel, texto de la nota y estructura."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from datetime import date
from typing import Any

import pytest

from nyx.brain.base import ChatMessage
from nyx.brain.longform import (
    LongAnswer,
    Section,
    is_long,
    panel_command,
    panel_title,
    sentence_count,
    spoken_summary,
    structure,
    to_answer,
    wants_structure,
)

# --- órdenes por voz al panel abierto (las mismas que en el prototipo aprobado) ---


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("Cierra el panel", "close"),
        ("ciérralo", "close"),
        ("cierra la explicación", "close"),
        ("oculta el panel", "close"),
        ("Nyx, ciérrala", "close"),
        ("quita esto", "close"),
        ("ya está", "close"),
        ("ya lo he leído", "close"),
        ("escóndelo", "close"),
        ("cópialo", "copy"),
        ("copia el texto", "copy"),
        ("copia la explicación", "copy"),
        ("cópiame la receta entera", "copy"),
        ("copia todo al portapapeles", "copy"),
        ("guárdamela en una nota", "save"),
        ("guárdalo en el bloc de notas", "save"),
        ("apúntamelo", "save"),
        ("hazme una nota con esto", "save"),
        ("pásalo a una nota", "save"),
        ("guarda la receta", "save"),
    ],
)
def test_panel_commands(text: str, command: str) -> None:
    assert panel_command(text) == command


@pytest.mark.parametrize(
    "text",
    [
        "cierra el Chrome",
        "cierra Spotify",
        "copia las fotos a Documentos",
        "guarda el documento",
        "abre el bloc de notas",
        "cierra todo",  # puede querer decir todas las ventanas
        "copia hola al portapapeles",
        "¿cuántos huevos lleva?",
        "sí",  # sin oferta de guardar, un «sí» no es para el panel
    ],
)
def test_not_panel_commands(text: str) -> None:
    assert panel_command(text) is None


@pytest.mark.parametrize("text", ["sí", "Vale", "sí, por favor", "claro", "venga"])
def test_yes_saves_only_after_the_offer(text: str) -> None:
    assert panel_command(text, offered=True) == "save"
    assert panel_command(text, offered=False) is None


# --- cuándo es larga, título y para qué se pide estructura ---


def test_long_and_sentences() -> None:
    assert not is_long("En alemán se dice Hallo.", 1)
    assert is_long("Una. Dos. Tres. Cuatro.", 4)
    assert is_long("x" * 301, 1)
    assert sentence_count("Primera frase. Segunda frase. ¿Tercera?") == 3


@pytest.mark.parametrize(
    ("display", "title"), [("Sí", ""), ("Claro", ""), ("Rayleigh", "Rayleigh")]
)
def test_panel_title(display: str, title: str) -> None:
    assert panel_title(display) == title


@pytest.mark.parametrize(
    ("question", "wants"),
    [
        ("busca una receta de lentejas con chorizo", True),
        ("¿cómo se hace la tortilla de patatas?", True),
        ("busca cómo poner la barra de tareas a la izquierda", True),
        ("busca los pasos para instalar Python", True),
        ("busca las mejores películas de 2025", True),
        ("busca quién inventó la imprenta", False),
        ("¿por qué el cielo es azul?", False),
    ],
)
def test_wants_structure(question: str, wants: bool) -> None:
    assert wants_structure(question) is wants


# --- nota y portapapeles ---

RECIPE = LongAnswer(
    title="Tortilla de patatas",
    kind="receta",
    sections=(
        Section("Ingredientes", ("6 huevos", "4 patatas")),
        Section("Pasos", ("Pela las patatas.", "Cuaja la tortilla."), ordered=True),
    ),
    sources=("pequerecetas.com", "abc.es"),
)


def test_note_text_of_a_recipe() -> None:
    assert RECIPE.note_text(date(2026, 11, 13)) == (
        "Tortilla de patatas\n"
        "Fuente: pequerecetas.com, abc.es · Guardada el 13-11-2026\n\n"
        "INGREDIENTES\n• 6 huevos\n• 4 patatas\n\n"
        "PASOS\n1. Pela las patatas.\n2. Cuaja la tortilla.\n"
    )
    assert RECIPE.copy_text().startswith("Tortilla de patatas\n\nINGREDIENTES")
    assert RECIPE.copy_text().endswith("Fuente: pequerecetas.com, abc.es\n")


def test_note_text_of_an_explanation_in_paragraphs() -> None:
    answer = LongAnswer(title="Cielo azul", sentences=[f"Frase {i}." for i in range(1, 6)])
    assert answer.note_text(date(2026, 11, 13)) == (
        "Cielo azul\nGuardada el 13-11-2026\n\nFrase 1. Frase 2. Frase 3.\n\nFrase 4. Frase 5.\n"
    )


# --- estructura con el modelo (esquema JSON) ---


class SchemaLLM:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.schemas: list[dict[str, Any]] = []
        self.messages: list[ChatMessage] = []

    async def warmup(self, *a: object, **k: object) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def stream(
        self, messages: Sequence[ChatMessage], *, schema: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        assert schema is not None
        self.schemas.append(schema)
        self.messages = list(messages)
        yield self.answer

    def chat(self, *a: object, **k: object) -> AsyncIterator[str]:
        raise AssertionError("no se usa")


RECIPE_JSON = {
    "tipo": "receta",
    "titulo": " Tortilla de patatas ",
    "secciones": [
        {"titulo": "Ingredientes", "elementos": ["6 huevos", " ", "4 patatas"], "numerada": False},
        {"titulo": "Pasos", "elementos": ["Pela.", "Cuaja."], "numerada": True},
        {"titulo": "Vacía", "elementos": [], "numerada": False},
    ],
    "voz": "Lleva dos ingredientes y dos pasos. ¿Quieres que te la lea?",
}


async def test_structure_a_recipe() -> None:
    llm = SchemaLLM(json.dumps(RECIPE_JSON))
    found = await structure(llm, "receta de tortilla", "<<<PELIGRO>>> " + "texto " * 100)
    assert found is not None and found.titulo == "Tortilla de patatas"
    assert [s.titulo for s in found.secciones] == ["Ingredientes", "Pasos"]  # sin la vacía
    assert found.secciones[0].elementos == ["6 huevos", "4 patatas"]
    # Lo de fuera va marcado y sin poder cerrar el bloque.
    assert "<<<" not in llm.messages[-1].content and "«" in llm.messages[-1].content
    answer = to_answer(found, ("pequerecetas.com",))
    assert answer.structured and answer.sections[1].ordered
    # La voz: el resumen sin la pregunta del modelo, y la oferta de Nyx.
    assert spoken_summary(found) == (
        "Lleva dos ingredientes y dos pasos. ¿Te la guardo en una nota?"
    )


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"tipo": "texto", "titulo": "Imprenta", "secciones": [], "voz": ""}),
        "esto no es JSON",
        json.dumps({"tipo": "receta", "titulo": "X", "secciones": [], "voz": ""}),
    ],
)
async def test_structure_gives_up_without_a_recipe(raw: str) -> None:
    assert await structure(SchemaLLM(raw), "receta", "texto") is None
