"""ui_action: pulsar un botón, marcar una casilla o leer un texto de una app por su nombre
(0.6, tarea 6.14), con UI Automation de Windows.

- Nunca en juegos ni en Nyx; bloqueada en partida.
- Leer es verde. Pulsar y marcar son amarillas (no se pueden deshacer: Nyx lo dice) y **rojas**
  si el control se llama como algo que no tiene vuelta atrás: eliminar, enviar, comprar,
  pagar, desinstalar… (`DANGER`).
- Si varios controles se parecen al nombre pedido, no se adivina: se dicen las opciones.
- Los objetos de UI Automation no pasan de un hilo a otro: al ejecutar se vuelve a buscar el
  control y tiene que ser el mismo que se confirmó (nombre y tipo); si no, no se hace nada.
- Lo que se lee de la app es contenido de fuera: va al LLM marcado como información.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.tools.base import (
    Category,
    GamePolicy,
    Params,
    Prepared,
    Risk,
    Tool,
    ToolContext,
    ToolResult,
)
from nyx.tools.focus_window import find_target_windows
from nyx.winapi import games, windows

log = logging.getLogger(__name__)

Action = Literal["click", "toggle", "read"]
MAX_READ = 2000

# Controles que no tienen vuelta atrás: pulsarlos es rojo (se confirma).
DANGER = re.compile(
    r"\b(?:eliminar|elimina|borrar|borra|suprimir|vaciar|enviar|envia|send|delete|remove|"
    r"comprar|compra|pagar|paga|pago|buy|pay|checkout|desinstalar|uninstall|formatear|"
    r"restablecer|reset|apagar|publicar|post|transferir|confirmar pedido|cerrar sesion)\b"
)

# Tipos de control de UI Automation (UIA_*ControlTypeId) por lo que se quiere hacer.
_CLICKABLE = {50000: "botón", 50002: "casilla", 50011: "menú", 50005: "enlace",
              50019: "pestaña", 50013: "opción", 50007: "elemento"}  # fmt: skip
_READABLE = {50020: "texto", 50004: "campo", 50030: "documento", 50000: "botón"}
_TYPES: dict[str, dict[int, str]] = {"click": _CLICKABLE, "toggle": {50002: "casilla"},
                                     "read": _READABLE}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Control:
    name: str
    kind: str  # «botón», «casilla»… (en español, para la confirmación)


@dataclass(frozen=True, slots=True)
class Found:
    control: Control | None = None
    options: tuple[str, ...] = ()  # varios parecidos: no se adivina


def _match(names: list[tuple[str, str]], wanted: str) -> Found:
    """El control que se llama así; si no hay uno exacto, el único que lo contiene."""
    want = normalize(wanted)
    exact = [(n, k) for n, k in names if normalize(n) == want]
    if len({n for n, _ in exact}) == 1:
        return Found(Control(*exact[0]))
    pool = exact or [(n, k) for n, k in names if want and want in normalize(n)]
    unique = list(dict.fromkeys(n for n, _ in pool))
    if len(unique) == 1:
        return Found(Control(*pool[0]))
    return Found(options=tuple(unique[:4]))


def uia(hwnd: int, wanted: str, action: Action, expect: Control | None) -> tuple[Found, str]:
    """Busca el control en la ventana. Con `expect`, hace la acción **solo si** lo encontrado
    es exactamente ese control (el que se confirmó); si no, no toca nada. Devuelve (lo
    encontrado, texto leído). Todo en el mismo hilo (COM)."""
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U

        auto: Any = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        root = auto.ElementFromHandle(hwnd)
        kinds = _TYPES[action]
        cond = auto.CreateFalseCondition()
        for type_id in kinds:
            cond = auto.CreateOrCondition(cond, auto.CreatePropertyCondition(30003, type_id))
        elements = root.FindAll(U.TreeScope_Descendants, cond)
        items: list[tuple[str, str, Any]] = []
        for i in range(min(elements.Length, 3000)):
            el = elements.GetElement(i)
            name = (el.CurrentName or "").strip()
            if name:
                items.append((name, kinds.get(el.CurrentControlType, "control"), el))
        found = _match([(n, k) for n, k, _ in items], wanted)
        if found.control is None or expect is None or found.control != expect:
            return found, ""  # sin acción, o la ventana ha cambiado: no se toca nada
        el = next(e for n, k, e in items if (n, k) == (found.control.name, found.control.kind))
        if action == "read":
            text = ""
            try:
                text = el.GetCurrentPattern(10002).QueryInterface(U.IUIAutomationValuePattern)
                text = text.CurrentValue
            except comtypes.COMError, AttributeError, ValueError:
                text = found.control.name
            return found, str(text or found.control.name)[:MAX_READ]
        if action == "toggle":
            el.GetCurrentPattern(10015).QueryInterface(U.IUIAutomationTogglePattern).Toggle()
        else:
            el.GetCurrentPattern(10000).QueryInterface(U.IUIAutomationInvokePattern).Invoke()
        return found, ""
    finally:
        comtypes.CoUninitialize()


class UiActionParams(Params):
    action: Action = Field(description="click (pulsar), toggle (marcar) o read (leer)")
    control: str = Field(min_length=1, max_length=80, description="Nombre del botón o texto")
    app: str | None = Field(default=None, max_length=100, description="App (vacío = activa)")


class UiAction(Tool[UiActionParams]):
    name = "ui_action"
    description = (
        "Pulsa un botón, marca una casilla o lee un texto de una app por su nombre. "
        "Ej.: «pulsa Aceptar» (action=click, control=Aceptar), «marca Recordarme» "
        "(action=toggle), «¿qué pone en el aviso?» (action=read)."
    )
    risk = Risk.YELLOW
    game_policy = GamePolicy.BLOCKED
    category = Category.WINDOWS
    params_model = UiActionParams
    observe = True  # leer: lo que pone vuelve al LLM para contarlo

    def __init__(
        self, backend: Callable[[int, str, Action, Control | None], tuple[Found, str]] = uia
    ) -> None:
        self._uia = backend

    async def prepare(self, params: UiActionParams, ctx: ToolContext) -> Prepared:
        verb = {"click": "Pulsar", "toggle": "Marcar", "read": "Leer"}[params.action]
        summary = f"{verb} «{params.control}»"
        if params.app:
            found_windows = await asyncio.to_thread(find_target_windows, ctx, params.app)
            if not found_windows:
                return Prepared(
                    summary=summary,
                    error=ToolResult.fail(f"No veo ninguna ventana de {params.app}"),
                )
            target = found_windows[0]
        else:
            fg = await asyncio.to_thread(windows.foreground)
            if fg is None or not fg.title:
                return Prepared(summary=summary, error=ToolResult.fail("¿En qué app?"))
            target = fg

        from nyx.tools.app_action import game_processes
        from nyx.tools.type_text import _NOT_TARGETS

        if target.process in _NOT_TARGETS:
            return Prepared(summary=summary, error=ToolResult.fail("Eso no lo toco en Nyx"))
        if await asyncio.to_thread(
            games.window_is_game, target.hwnd, target.process, game_processes(ctx)
        ):
            return Prepared(
                summary=summary, error=ToolResult.fail("Dentro de los juegos no toco nada")
            )
        try:
            found, _ = await asyncio.to_thread(
                self._uia, target.hwnd, params.control, params.action, None
            )
        except Exception:
            log.warning("UI Automation no responde", exc_info=True)
            return Prepared(summary=summary, error=ToolResult.fail("No puedo ver esa ventana"))
        if found.control is None:
            if found.options:
                return Prepared(
                    summary=summary,
                    error=ToolResult.fail(
                        "Hay varios parecidos", f"¿Cuál? {', '.join(found.options)}"
                    ),
                )
            return Prepared(
                summary=summary,
                error=ToolResult.fail(f"No veo «{params.control}» en {target.title}"),
            )
        control = found.control
        risk = Risk.GREEN if params.action == "read" else Risk.YELLOW
        if params.action != "read" and DANGER.search(normalize(control.name)):
            risk = Risk.RED  # no tiene vuelta atrás: se confirma
        return Prepared(
            summary=f"{verb} el {control.kind} «{control.name}» en {target.title}",
            risk=risk,
            payload=(target.hwnd, control),
        )

    async def execute(
        self, params: UiActionParams, ctx: ToolContext, prepared: Prepared
    ) -> ToolResult:
        hwnd, control = prepared.payload
        try:
            found, text = await asyncio.to_thread(
                self._uia, hwnd, control.name, params.action, control
            )
        except Exception:
            log.warning("ui_action falló", exc_info=True)
            return ToolResult.fail("No he podido hacerlo", "la ventana ha cambiado")
        if found.control != control:
            return ToolResult.fail("La ventana ha cambiado", "no he tocado nada")
        if params.action == "read":
            return ToolResult(
                ok=True,
                message=f"He leído lo que pone en «{control.name}».",
                display=control.name,
                external=text or None,
                data={"action": "read", "chars": len(text)},
            )
        done = "Pulsado" if params.action == "click" else "Marcado"
        return ToolResult(
            ok=True,
            message=f"{done} «{control.name}».",
            display=f"{done} «{control.name}»",
            secondary="no se puede deshacer",
            observe=False,
            data={"action": params.action},
        )
