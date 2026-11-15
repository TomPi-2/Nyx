# SPDX-License-Identifier: MIT
"""Tipos del módulo `nyx` que ve una extensión dentro de Nyx (runner.py del núcleo).

Solo para el editor y mypy: el módulo de verdad lo pone Nyx al arrancar la extensión, y en las
pruebas, `nyx_sdk.testing.FakeNyx`.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

#: Versión de la API de extensiones.
API: str
#: Carpeta de datos propia de la extensión (la única donde puede escribir por su cuenta).
data_dir: Path

class Error(Exception):
    """Lánzala con un texto para el usuario («OBS no está abierto»): Nyx lo enseña tal cual.
    Cualquier otra excepción sale con su tipo y va al registro con su traza."""

def tool[F: Callable[..., Any]](fn: F) -> F:
    """Marca una función como herramienta. Su nombre es el de la función y tiene que estar
    descrita en `tools/tools.json`."""

async def ask(method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0) -> Any:
    """Pide algo a Nyx (`net.fetch`, `ws.open`, `secrets.get`…). Lanza RuntimeError si Nyx
    dice que no (por ejemplo, sin el permiso en el manifiesto)."""

def ask_sync(method: str, params: dict[str, Any] | None = None, timeout_s: float = 30.0) -> Any:
    """Lo mismo desde una herramienta normal (no asíncrona)."""
