r"""Tarjeta gráfica y modelo de lenguaje recomendado (asistente, paso de modelos).

La memoria de la tarjeta gráfica (VRAM) se lee del registro de Windows
(HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-…}\00NN →
HardwareInformation.qwMemorySize), que la da exacta; WMI se queda en 4 GB como mucho. Se
elige la tarjeta con más memoria: en un portátil con dos, la dedicada.

Modelos (SPEC sección 2): todos con licencia Apache 2.0. La recomendación va por la memoria
de la tarjeta, que es lo que decide si el modelo cabe entero en la GPU (y va rápido).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

log = logging.getLogger(__name__)

_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
GB = 1024**3


@dataclass(frozen=True, slots=True)
class Gpu:
    name: str
    vram_gb: float


@dataclass(frozen=True, slots=True)
class LlmChoice:
    id: str  # nombre en Ollama
    label: str
    size_gb: float  # lo que se descarga
    min_vram_gb: float  # para que quepa entero en la GPU
    note: str
    tested: bool  # pasado por la batería de frases de Nyx


#: Los modelos que se ofrecen. En la primera versión, uno solo (decisión 2026-11-11): el 14B
#: era 8 veces más lento en la batería de frases sin acertar más, no cabe en tarjetas de 8 GB
#: y junto a un juego da tirones. Para respuestas más elaboradas, la nube opcional (2.0).
LLM_CHOICES: tuple[LlmChoice, ...] = (
    LlmChoice(
        "qwen2.5:7b",
        "Qwen 2.5 · 7B",
        4.7,
        6,
        "Rápido y fiable con las acciones y las preguntas. Cabe junto a tus juegos.",
        True,
    ),
)


def gpus() -> list[Gpu]:
    """Tarjetas gráficas con su memoria, de más a menos."""
    try:
        import winreg
    except ImportError:
        return []
    found: list[Gpu] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS)
    except OSError:
        return []
    with root:
        for i in range(32):
            try:
                with winreg.OpenKey(root, f"{i:04d}") as key:
                    name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                    memory = _memory(winreg, key)
            except OSError:
                continue
            if memory:
                found.append(Gpu(name, round(memory / GB, 1)))
    return sorted(found, key=lambda g: g.vram_gb, reverse=True)


def _memory(winreg: object, key: object) -> int:
    for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
        try:
            raw = winreg.QueryValueEx(key, value)[0]  # type: ignore[attr-defined]
        except OSError:
            continue
        if isinstance(raw, bytes):
            return int.from_bytes(raw[:8], "little")
        return int(raw)
    return 0


def recommend(vram_gb: float | None) -> str:
    """El modelo más capaz que cabe entero en la GPU; si no se sabe, el de por defecto."""
    if vram_gb is None:
        return LLM_CHOICES[0].id
    fitting = [c for c in LLM_CHOICES if vram_gb >= c.min_vram_gb]
    return (fitting[-1] if fitting else LLM_CHOICES[0]).id


def llm_status() -> dict[str, object]:
    """Para el asistente: la tarjeta, los modelos posibles y el recomendado."""
    try:
        cards = gpus()
    except Exception:
        log.debug("No se pudo leer la tarjeta gráfica", exc_info=True)
        cards = []
    best = cards[0] if cards else None
    return {
        "gpu": None if best is None else asdict(best),
        "choices": [asdict(c) for c in LLM_CHOICES],
        "recommended": recommend(best.vram_gb if best else None),
    }
