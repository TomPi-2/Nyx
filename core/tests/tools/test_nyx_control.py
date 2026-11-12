"""nyx_control (6.04): cambiar ajustes de Nyx por voz, por el mismo camino que Ajustes."""

from typing import Any

import pytest

from nyx.executor import Executor, ToolCall
from nyx.settings.live import SettingsError, apply_patch
from nyx.settings.model import Settings
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry


@pytest.fixture
def applied(ctx: ToolContext, tmp_path: Any) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def apply(patch: dict[str, Any]) -> list[str]:
        seen.append(patch)
        return apply_patch(ctx.settings, patch, tmp_path / "settings.json")

    ctx.apply_settings = apply
    return seen


async def run(ctx: ToolContext, setting: str, value: str) -> Any:
    return await Executor(default_registry(), ctx).run(
        ToolCall("nyx_control", {"setting": setting, "value": value})
    )


@pytest.mark.parametrize(
    ("setting", "value", "path", "expected"),
    [
        # ERRORES.md, 2026-11-11: «bájate la calidad del cristal al mínimo».
        ("calidad del cristal", "al mínimo", ("appearance", "glass", "quality"), "bajo"),
        ("calidad del cristal", "automática", ("appearance", "glass", "quality"), "auto"),
        ("velocidad de la voz", "más despacio", ("tts", "speed"), 0.85),
        ("respuestas habladas", "no", ("tts", "enabled"), False),
        ("voz al escribir", "sí", ("responses", "speak_typed"), True),
        ("modo partida", "solo voz", ("game", "mode"), "voice"),
        ("cerebro en partida", "solo órdenes", ("game", "brain"), "off"),
        ("tamaño", "más grande", ("appearance", "indicator_size"), 120),
        ("sensibilidad", "baja", ("wake", "sensitivity"), 5),
        ("color", "azul cielo", ("appearance", "nyx_color"), "azul_cielo"),
        ("tono de los paneles", "océano", ("appearance", "panel_tint"), "oceano"),
        ("ciudad", "Valencia", ("general", "city"), "Valencia"),
        ("ciudad", "A Coruña", ("general", "city"), "A Coruña"),
    ],
)
async def test_changes_settings(
    ctx: ToolContext,
    applied: list[dict[str, Any]],
    setting: str,
    value: str,
    path: tuple[str, ...],
    expected: Any,
) -> None:
    result = await run(ctx, setting, value)
    assert result.ok, result.message
    current: Any = ctx.settings.model_dump(mode="json")
    for part in path:
        current = current[part]
    assert current == expected


async def test_restart_is_said(ctx: ToolContext, applied: list[dict[str, Any]]) -> None:
    result = await run(ctx, "velocidad de la voz", "más rápido")
    assert result.ok and "al reiniciarme" in result.message


async def test_unclear_value_changes_nothing(
    ctx: ToolContext, applied: list[dict[str, Any]]
) -> None:
    result = await run(ctx, "color", "el de siempre")
    assert not result.ok and applied == []


async def test_already_set(ctx: ToolContext, applied: list[dict[str, Any]]) -> None:
    result = await run(ctx, "modo partida", "solo voz")  # es el predeterminado
    assert result.ok and "ya está" in result.message and applied == []


def test_only_editable_settings() -> None:
    # Lo que no se puede cambiar desde Ajustes tampoco se puede por voz.
    with pytest.raises(SettingsError):
        apply_patch(Settings(), {"llm": {"host": "http://otro:1"}})
