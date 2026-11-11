"""nyx_control: cambiar ajustes de Nyx por voz (verde, tarea 6.04).

«Baja la calidad del cristal al mínimo», «habla más despacio», «ponte en turquesa», «modo
partida solo voz», «no me contestes en voz a lo que escribo». Solo una **lista cerrada** de
ajustes (`SETTINGS`), y todos están también en `EDITABLE` de `settings/live.py`: se aplican
por el mismo camino que la ventana de Ajustes (`apply_patch`). Nada de rutas, direcciones,
seguridad o privacidad. Tampoco «dejar de escuchar» por voz: luego no podrías volver a
llamarla con la voz (para eso está Ajustes).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.settings.live import SettingsError
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

_YES = ("si", "activa", "activar", "enciende", "pon", "on", "true", "vale")
_NO = ("no", "desactiva", "desactivar", "apaga", "quita", "off", "false", "nunca")
_UP = ("mas", "sube", "aumenta", "subir", "rapid", "grande", "alt", "maxim", "sensible")
_DOWN = ("menos", "baja", "reduce", "bajar", "despacio", "lent", "pequen", "minim")

COLORS = {
    "blanco": "blanco", "perla": "perla", "arena": "arena", "melocoton": "melocoton",
    "coral": "coral", "rojo": "rojo", "rosa": "rosa", "fucsia": "fucsia", "lavanda": "lavanda",
    "violeta": "violeta", "azul cielo": "azul_cielo", "azul": "azul", "turquesa": "turquesa",
    "menta": "menta", "verde": "verde", "lima": "lima", "amarillo": "amarillo",
    "ambar": "ambar", "grafito": "grafito",
}  # fmt: skip
TINTS = {
    "gris": "gris", "grafito": "grafito", "azul noche": "azul_noche", "oceano": "oceano",
    "bosque": "bosque", "salvia": "salvia", "ciruela": "ciruela", "vino": "vino", "rosa": "rosa",
    "arena": "arena", "cobre": "cobre", "lavanda": "lavanda",
}  # fmt: skip


@dataclass(frozen=True)
class Setting:
    path: str  # «appearance.glass.quality»
    label: str  # cómo se dice
    parse: Callable[[str, Any], Any]  # (lo dicho, valor actual) → valor nuevo; None si no vale
    say: Callable[[Any], str] = str  # valor → cómo se dice


def _choice(options: dict[str, Any]) -> Callable[[str, Any], Any]:
    def parse(said: str, _: Any) -> Any:
        # La más larga primero: «azul cielo» antes que «azul».
        for word in sorted(options, key=len, reverse=True):
            if re.search(rf"\b{word}\b", said):
                return options[word]
        return None

    return parse


def _switch(said: str, _: Any) -> bool | None:
    words = said.split()
    if any(w in _NO for w in words):
        return False
    if any(w in _YES for w in words):
        return True
    return None


def _step(low: float, high: float, step: float, normal: float) -> Callable[[str, Any], Any]:
    def parse(said: str, current: Any) -> Any:
        if number := re.search(r"\d+(?:[.,]\d+)?", said):
            value = float(number.group().replace(",", "."))
        elif "normal" in said:
            value = normal
        elif any(w in said for w in _DOWN):
            value = float(current) - step
        elif any(w in said for w in _UP):
            value = float(current) + step
        else:
            return None
        value = min(high, max(low, value))
        return int(value) if float(step).is_integer() else round(value, 2)

    return parse


_QUALITY = {
    "auto": "auto", "automatic": "auto", "alto": "alto", "alta": "alto", "maxim": "alto",
    "medio": "medio", "media": "medio", "bajo": "bajo", "baja": "bajo", "minim": "bajo",
}  # fmt: skip


def _quality(said: str, _: Any) -> Any:
    for word, value in _QUALITY.items():
        if word in said:
            return value
    return None


SETTINGS: dict[str, Setting] = {
    "calidad del cristal": Setting(
        "appearance.glass.quality",
        "calidad del cristal",
        _quality,
        {"auto": "automática", "alto": "alta", "medio": "media", "bajo": "baja"}.__getitem__,
    ),
    "velocidad de la voz": Setting(
        "tts.speed", "velocidad de la voz", _step(0.5, 2.0, 0.15, 1.0), lambda v: f"{v:g}"
    ),
    "respuestas habladas": Setting(
        "tts.enabled", "respuestas habladas", _switch, lambda v: "sí" if v else "no"
    ),
    "voz al escribir": Setting(
        "responses.speak_typed",
        "responder en voz a lo escrito",
        _switch,
        lambda v: "sí" if v else "no",
    ),
    "modo partida": Setting(
        "game.mode",
        "Nyx en partida",
        _choice(
            {
                "desactivado": "off",
                "apagado": "off",
                "solo voz": "voice",
                "voz": "voice",
                "normal": "normal",
            }
        ),
        {"off": "desactivado", "voice": "solo voz", "normal": "normal"}.__getitem__,
    ),
    "cerebro en partida": Setting(
        "game.brain",
        "cerebro en partida",
        _choice({"solo ordenes": "off", "ordenes": "off", "no": "off", "si": "auto"}),
        {"auto": "sí", "off": "solo órdenes"}.__getitem__,
    ),
    "tamaño": Setting("appearance.indicator_size", "tamaño", _step(44, 260, 20, 100)),
    "sensibilidad": Setting("wake.sensitivity", "sensibilidad", _step(1, 10, 1, 6)),
    "color": Setting(
        "appearance.nyx_color", "color", _choice(COLORS), lambda v: v.replace("_", " ")
    ),
    "tono de los paneles": Setting(
        "appearance.panel_tint",
        "tono de los paneles",
        _choice(TINTS),
        lambda v: v.replace("_", " "),
    ),
}

SettingName = Literal[
    "calidad del cristal",
    "velocidad de la voz",
    "respuestas habladas",
    "voz al escribir",
    "modo partida",
    "cerebro en partida",
    "tamaño",
    "sensibilidad",
    "color",
    "tono de los paneles",
]


def _get(data: dict[str, Any], path: str) -> Any:
    for part in path.split("."):
        data = data[part]
    return data


def _patch(path: str, value: Any) -> dict[str, Any]:
    *parents, last = path.split(".")
    patch: dict[str, Any] = {last: value}
    for part in reversed(parents):
        patch = {part: patch}
    return patch


class NyxControlParams(Params):
    setting: SettingName = Field(description="Ajuste de Nyx")
    value: str = Field(
        min_length=1,
        max_length=40,
        description="Valor dicho: «mínimo», «más despacio», «solo voz», «turquesa»…",
    )


class NyxControl(Tool[NyxControlParams]):
    name = "nyx_control"
    description = (
        "Cambia un ajuste tuyo, de Nyx. Ej.: «habla más despacio» (setting=velocidad de la "
        "voz, value=más despacio), «cuando juegue, solo por voz» (setting=modo partida, "
        "value=solo voz)."
    )
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = NyxControlParams

    async def run(self, params: NyxControlParams, ctx: ToolContext) -> ToolResult:
        if ctx.apply_settings is None:
            return ToolResult.fail("No puedo cambiar mis ajustes ahora")
        setting = SETTINGS[params.setting]
        current = _get(ctx.settings.model_dump(mode="json"), setting.path)
        value = setting.parse(normalize(params.value), current)
        if value is None:
            return ToolResult.fail(
                f"No sé qué poner en {setting.label}", f"has dicho «{params.value}»"
            )
        if value == current:
            return ToolResult(
                ok=True,
                message=f"{setting.label[:1].upper()}{setting.label[1:]} ya está en "
                f"{setting.say(value)}",
                display=setting.say(value),
                secondary=f"{setting.label} · ya estaba así",
            )
        try:
            restart = await ctx.apply_settings(_patch(setting.path, value))
        except SettingsError as err:
            return ToolResult.fail("No he podido cambiarlo", str(err))
        later = " (al reiniciarme)" if restart else ""
        return ToolResult(
            ok=True,
            message=f"{setting.label[:1].upper()}{setting.label[1:]}: {setting.say(value)}{later}",
            display=setting.say(value),
            secondary=setting.label + (" · se aplica al reiniciarme" if restart else ""),
        )
