"""Elección de dispositivos de audio por nombre, siempre a través de WASAPI.

WASAPI da los nombres completos y la menor latencia; con `auto_convert` Windows hace el
cambio de frecuencia y de canales (el micrófono puede ir a 48 kHz estéreo y Nyx pide 16 kHz mono).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

log = logging.getLogger(__name__)

Kind = Literal["input", "output"]


def _wasapi_index(hostapis: Any) -> int | None:
    for i, api in enumerate(hostapis):
        if "WASAPI" in str(api["name"]):
            return i
    return None


def pick_device(
    devices: list[dict[str, Any]],
    hostapis: list[dict[str, Any]],
    kind: Kind,
    name: str | None,
) -> int | None:
    """Índice del dispositivo WASAPI cuyo nombre contiene `name`, o el predeterminado.

    Devuelve None si no hay WASAPI (se usará el predeterminado de PortAudio).
    """
    api = _wasapi_index(hostapis)
    if api is None:
        return None
    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    candidates = [i for i, d in enumerate(devices) if d["hostapi"] == api and int(d[channels]) > 0]
    if name:
        wanted = name.casefold()
        for i in candidates:
            if wanted in str(devices[i]["name"]).casefold():
                return i
        log.warning("No encuentro el dispositivo de %s «%s»: uso el predeterminado", kind, name)
    default = int(hostapis[api][f"default_{kind}_device"])
    return default if default in candidates else (candidates[0] if candidates else None)


def resolve(kind: Kind, name: str | None) -> tuple[int | None, Any]:
    """(índice, extra_settings) para abrir un stream de sounddevice."""
    import sounddevice as sd

    devices = [dict(d) for d in sd.query_devices()]
    hostapis = [dict(a) for a in sd.query_hostapis()]
    index = pick_device(devices, hostapis, kind, name)
    if index is None:
        return None, None
    log.info("Audio %s: %s", "entrada" if kind == "input" else "salida", devices[index]["name"])
    return index, sd.WasapiSettings(auto_convert=True)


def device_names(kind: Kind) -> list[str]:
    """Nombres de los dispositivos de entrada o salida (WASAPI), para Ajustes → Voz."""
    try:
        import sounddevice as sd

        devices = [dict(d) for d in sd.query_devices()]
        hostapis = [dict(a) for a in sd.query_hostapis()]
    except Exception:
        log.warning("No se pudo listar los dispositivos de audio", exc_info=True)
        return []
    api = _wasapi_index(hostapis)
    if api is None:
        return []
    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    names = {str(d["name"]) for d in devices if d["hostapi"] == api and int(d[channels]) > 0}
    return sorted(names, key=str.casefold)
