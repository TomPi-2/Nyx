"""Prueba de humo en Windows: las herramientas que solo consultan, ejecutadas de verdad.

No cambia nada del PC (ni volumen, ni ventanas, ni archivos): solo lee. Sirve para ver en un
equipo concreto qué funciona y qué da error (Everything sin instalar, brillo de un monitor
externo, la música que suena, la red…). Lo que leen no se enseña: solo si ha ido bien, cuánto
ha tardado y el principio del mensaje con los datos personales tapados.

    uv run python scripts/smoke_tools.py
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nyx.alarms.scheduler import AlarmScheduler
from nyx.alarms.store import AlarmStore
from nyx.bus import EventBus
from nyx.index.service import SystemIndex
from nyx.organizer.store import OrganizerStore
from nyx.settings.model import load_settings
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry

#: (herramienta, argumentos): solo lectura.
CASES: list[tuple[str, dict[str, Any]]] = [
    *[("system_info", {"what": w}) for w in ("battery", "cpu", "ram", "disk", "top", "ip")],
    ("get_weather", {}),
    ("now_playing", {}),
    ("list_alarms", {}),
    ("stopwatch", {"action": "status"}),
    ("clipboard", {"action": "read"}),
    ("nyx_info", {"topic": "quién eres"}),
    ("list_files", {"folder": "Descargas", "newest": 3}),
    ("find_files", {"query": "factura", "limit": 3}),
    ("recent_files", {"action": "list", "kind": "any", "count": 3}),
    ("privacy_check", {"device": "both", "when": "now"}),
    ("list_items", {"action": "lists"}),
    ("task", {"action": "read"}),
    ("run_powershell", {"command": "Get-Date"}),
]

_PRIVATE = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I), r"C:\\Users\\<usuario>"),
]


def tidy(text: str) -> str:
    for pattern, repl in _PRIVATE:
        text = pattern.sub(repl, text)
    return " ".join(text.split())[:90]


async def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    settings = load_settings()
    index = SystemIndex.open()
    await index.refresh()
    registry = default_registry()
    ctx = ToolContext(
        index=index,
        settings=settings,
        alarms=AlarmScheduler(AlarmStore.default(), EventBus()),
        organizer=OrganizerStore.default(),
    )
    failed = 0
    print(f"{'Herramienta':<36} {'':<5} {'ms':>6}  Mensaje")
    for name, args in CASES:
        tool = registry.get(name)
        label = f"{name}({', '.join(f'{k}={v}' for k, v in args.items())})"
        if tool is None:
            print(f"{label:<36} FALTA")
            failed += 1
            continue
        t0 = time.perf_counter()
        try:
            params = tool.params_model.model_validate(args)
            result = await asyncio.wait_for(tool.run(params, ctx), timeout=30)
            ok, message = result.ok, result.message or (result.display or "")
            # «No he encontrado ninguna factura»: la herramienta funciona, no hay nada.
            ok = ok or message.startswith(("No he encontrado", "No encuentro"))
        except Exception as e:  # una herramienta que revienta es justo lo que se busca
            ok, message = False, f"{type(e).__name__}: {e}"
        ms = (time.perf_counter() - t0) * 1000
        failed += not ok
        print(f"{label[:36]:<36} {'ok' if ok else 'FALLO':<5} {ms:>6.0f}  {tidy(message)}")
    index.close()
    print(f"\n{len(CASES) - failed}/{len(CASES)} bien")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
