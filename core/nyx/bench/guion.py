"""Guion de la batería de audio: cada frase que se graba y lo que debe hacer Nyx con ella.

Una línea por frase en `tests/battery/audio/guion.jsonl`:

    {"id": "a001", "categoria": "orden", "frase": "Nyx, abre Spotify",
     "tool": "open_app", "args": {"name": "Spotify"}}

Lo esperado, uno de (igual que `scripts/battery.py`, más dos tipos nuevos):

- `tool` (`"a|b"` si vale cualquiera) y `args` parciales: una acción;
- `plan`: varios pasos en orden;
- `tipo`: `respuesta` (contesta en texto, sin actuar), `no_sabe` (no actúa),
  `preguntar` (no actúa y pregunta: lo que falta o lo dudoso) o `ignorar` (no era para Nyx:
  ni se activa ni contesta).

Otros campos:

- `como`: cómo decirla al grabar («haz una pausa en los puntos suspensivos»…);
- `nyx`: si se dice con «Nyx» (por defecto, sí). Las de `ignorar` suelen ir sin él;
- `grupo`: frases seguidas de la misma conversación («abre Spotify» → «no, el otro»). Las
  siguientes del grupo se dicen tras la respuesta, en la ventana de seguimiento.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

GUION = Path(__file__).resolve().parents[2] / "tests" / "battery" / "audio" / "guion.jsonl"

Tipo = Literal["respuesta", "no_sabe", "preguntar", "ignorar"]
CATEGORIAS = (
    "activacion",  # «Nyx» suelto, de varias formas
    "orden",  # órdenes normales
    "nombre",  # nombres difíciles de apps, juegos y webs
    "compuesta",  # varias órdenes en una frase
    "pausa",  # con pausas para pensar a mitad
    "a_medias",  # se deja a medias: Nyx debe esperar y preguntar
    "correccion",  # «no, el otro», «más alto»… (en grupo)
    "pregunta",  # preguntas y charla
    "ambigua",  # falta información: debe preguntar
    "no_para_nyx",  # conversación con otros, aunque se nombre a Nyx
    "dictado",  # notas y dictado
    "registro",  # sacadas de fallos reales (ERRORES.md, registros)
)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    categoria: str
    frase: str
    como: str = ""
    nyx: bool = True
    grupo: str | None = None
    tool: str | None = None
    args: dict[str, Any] = {}
    plan: list[str] | None = None
    tipo: Tipo | None = None

    @model_validator(mode="after")
    def _one_expectation(self) -> Item:
        given = [self.tool is not None, self.plan is not None, self.tipo is not None]
        if sum(given) != 1:
            raise ValueError(f"{self.id}: hace falta uno (y solo uno) de tool, plan o tipo")
        if self.args and self.tool is None:
            raise ValueError(f"{self.id}: args solo con tool")
        if self.categoria not in CATEGORIAS:
            raise ValueError(f"{self.id}: categoría desconocida {self.categoria!r}")
        return self

    @property
    def expected(self) -> dict[str, Any]:
        """Lo esperado con el formato de `scripts/battery.py`."""
        if self.tool is not None:
            return {"tool": self.tool, "args": self.args}
        if self.plan is not None:
            return {"plan": self.plan}
        return {"tipo": self.tipo}


def load(path: Path = GUION) -> list[Item]:
    items = [
        Item.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"ids repetidos: {dup}")
    return items
