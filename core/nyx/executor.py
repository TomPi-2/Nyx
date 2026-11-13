"""Executor: valida, revisa y ejecuta llamadas a herramientas, una tras otra (SPEC sección 3).

Por cada llamada:
1. Valida los parámetros con el esquema de la herramienta.
2. `prepare`: resuelve exactamente qué se va a tocar (archivos, ventanas…).
3. SafetyGuard decide: ejecutar, ejecutar con deshacer, pedir confirmación o bloquear.
4. Si es roja, pide confirmación (clic o voz) y ejecuta exactamente lo preparado.
5. Ejecuta con tiempo máximo; un fallo nunca tumba el núcleo.
6. Si es amarilla y salió bien, guarda cómo deshacerla (30 s).
7. Todo queda en el registro de acciones.

En un plan de varios pasos, el primer fallo (o una cancelación) detiene los siguientes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from nyx.brain.phrases import PhraseBook
from nyx.game.policy import GameGate
from nyx.safety.action_log import ActionLog, Decision
from nyx.safety.guard import SafetyGuard, Verdict
from nyx.tools.base import GamePolicy, Prepared, Risk, Tool, ToolContext, ToolResult
from nyx.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Confirmation:
    summary: str  # «Mandar a la papelera 3 archivos»
    detail: str  # «de Descargas: a.pdf, b.pdf, c.pdf»
    click_only: bool  # más de 50 elementos o fuera de las carpetas del usuario


ConfirmFn = Callable[[Confirmation], Awaitable[bool]]


def cancelled_result(summary: str) -> ToolResult:
    return ToolResult(
        ok=False,
        message="Cancelado",
        display="Cancelado",
        secondary=summary,
        data={"cancelled": True},
    )


# Tras abrir una app, estas herramientas necesitan que su ventana ya exista.
_NEEDS_WINDOW = {
    "focus_window",
    "window_layout",
    "close_app",
    "wait_for_window",
    "send_hotkey",
    "app_action",
}


def _enum_options(schema: dict[str, Any], prop: dict[str, Any]) -> list[str]:
    """Valores permitidos de un parámetro (enum directo, anyOf o referencia a $defs)."""
    if "$ref" in prop:
        prop = schema.get("$defs", {}).get(prop["$ref"].rsplit("/", 1)[-1], {})
    options = list(prop.get("enum", []))
    for alt in prop.get("anyOf", []):
        options += _enum_options(schema, alt)
    return [o for o in options if isinstance(o, str)]


def fix_enums(calls: list[ToolCall], registry: ToolRegistry) -> list[ToolCall]:
    """«playpause» → «play_pause»: el modelo a veces escribe una opción sin guiones bajos o
    con otras mayúsculas. Se corrige solo si queda exactamente una opción equivalente."""

    def key(v: str) -> str:
        return v.replace("_", "").replace("-", "").replace(" ", "").lower()

    fixed: list[ToolCall] = []
    for call in calls:
        tool = registry.get(call.name)
        if tool is None:
            fixed.append(call)
            continue
        schema = tool.params_model.model_json_schema()
        args = dict(call.arguments)
        for name, value in call.arguments.items():
            prop = schema.get("properties", {}).get(name)
            if not isinstance(value, str) or prop is None:
                continue
            options = _enum_options(schema, prop)
            if options and value not in options:
                same = [o for o in options if key(o) == key(value)]
                if len(same) == 1:
                    args[name] = same[0]
        fixed.append(ToolCall(call.name, args))
    return fixed


def with_waits(calls: list[ToolCall]) -> list[ToolCall]:
    """SPEC sección 6: «el ejecutor hace las esperas, no el LLM». Tras open_app, si el paso
    siguiente usa ventanas, se espera a que la app abra la suya."""
    out: list[ToolCall] = []
    for i, call in enumerate(calls):
        out.append(call)
        following = calls[i + 1] if i + 1 < len(calls) else None
        name = call.arguments.get("name")
        if (
            call.name == "open_app"
            and isinstance(name, str)
            and following is not None
            and following.name in _NEEDS_WINDOW
            and following.name != "wait_for_window"
        ):
            out.append(ToolCall("wait_for_window", {"name": name}))
    return out


_VERBS = {
    "open_app": "abrir",
    "close_app": "cerrar",
    "focus_window": "ir a",
    "window_layout": "colocar",
    "open_url": "abrir",
    "open_path": "abrir",
    "open_settings": "abrir la configuración de",
    "open_nyx_settings": "abrir mis ajustes",
    "create_folder": "crear la carpeta",
    "move_files": "mover",
    "copy_files": "copiar",
    "rename_file": "renombrar",
    "delete_files": "mandar a la papelera",
    "app_action": "hacer en",
    "send_hotkey": "pulsar",
    "list_files": "mirar la carpeta",
    "find_files": "buscar",
    "list_alarms": "mirar las alarmas",
    "cancel_alarm": "quitar la alarma",
    "set_alarm": "poner una alarma a las",
    "set_timer": "poner un temporizador",
    "stopwatch": "usar el cronómetro",
    "nyx_info": "consultar cómo funciono, sobre",
    "get_weather": "mirar el tiempo",
    "system_info": "mirar el estado del equipo",
    "system_power": "controlar el encendido del equipo",
    "run_powershell": "ejecutar un comando de PowerShell",
    "install_app": "instalar o desinstalar un programa",
    "ui_action": "pulsar o leer algo en una app",
    "web_search": "buscar en internet",
    "save_note": "guardar la nota",
    "set_brightness": "cambiar el brillo",
    "toggle_wifi": "cambiar el Wi-Fi",
    "toggle_bluetooth": "cambiar el Bluetooth",
    "clipboard": "usar el portapapeles",
    "type_text": "escribir",
    "pending": "mirar lo pendiente",
    "media_control": "controlar la música",
    "now_playing": "ver qué suena",
    "audio_output": "abrir los ajustes de salida de audio",
    "set_volume": "cambiar el volumen",
    "screenshot": "hacer una captura",
    "wait_for_window": "esperar a que se abra",
    "undo": "deshacer",
    "nyx_control": "cambiar mi ajuste de",
}


# Herramientas con una opción cerrada (`action`, `what`): la frase entera según la opción.
# Por herramienta y opción, nunca por el valor suelto: «top» o «stop» pueden ser también el
# nombre de una ventana, una carpeta o lo que el usuario ha dictado.
_OPTION_VERBS: dict[tuple[str, str], str] = {
    ("system_info", "battery"): "mirar la batería",
    ("system_info", "cpu"): "mirar el uso del procesador",
    ("system_info", "ram"): "mirar la memoria RAM",
    ("system_info", "disk"): "mirar el espacio en disco",
    ("system_info", "top"): "mirar qué programa consume más",
    ("clipboard", "read"): "leer el portapapeles",
    ("clipboard", "write"): "copiar al portapapeles",
    ("stopwatch", "start"): "poner el cronómetro",
    ("stopwatch", "stop"): "parar el cronómetro",
    ("stopwatch", "status"): "mirar el cronómetro",
    ("system_power", "lock"): "bloquear el equipo",
    ("system_power", "sleep"): "suspender el equipo",
    ("system_power", "restart"): "reiniciar el equipo",
    ("system_power", "shutdown"): "apagar el equipo",
    ("media_control", "pause"): "pausar la música",
    ("media_control", "play"): "reanudar la música",
    ("media_control", "play_pause"): "pausar o reanudar la música",
    ("media_control", "next"): "pasar a la siguiente canción",
    ("media_control", "previous"): "volver a la canción anterior",
    ("media_control", "stop"): "parar la música",
    ("pending", "list"): "mirar lo pendiente",
    ("pending", "cancel"): "olvidar lo pendiente",
}
_OPTION_ARGS = ("action", "what")


def describe_call(call: ToolCall) -> str:
    """«open_app Discord» → «abrir Discord»: legible para la burbuja y la voz de lo diferido."""
    # Nunca el nombre interno: el modelo lo vería en los resultados y lo escribiría en la
    # burbuja (pasó en la 6.03). Cada herramienta tiene su verbo (lo exige una prueba).
    verb = _VERBS.get(call.name, "hacer lo pedido")
    option = next((k for k in _OPTION_ARGS if k in call.arguments), None)
    if option and (phrase := _OPTION_VERBS.get((call.name, str(call.arguments[option])))):
        verb = phrase
    else:
        option = None
    values = [
        str(v)
        for k, v in call.arguments.items()
        if k != option and isinstance(v, str | int) and not isinstance(v, bool) and v != ""
    ]
    return " ".join([verb, *values[:2]])


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        ctx: ToolContext,
        *,
        guard: SafetyGuard | None = None,
        action_log: ActionLog | None = None,
        confirm: ConfirmFn | None = None,
        game: GameGate | None = None,
        phrases: PhraseBook | None = None,
    ) -> None:
        self.registry = registry
        self.ctx = ctx
        self.guard = guard or SafetyGuard(ctx.paths)
        self.log = action_log
        self.confirm = confirm
        self.game = game  # modo partida: permitida, diferida o bloqueada (SPEC sección 9)
        self.phrases = phrases or PhraseBook()

    def _record(
        self,
        tool: Tool[Any] | None,
        name: str,
        params: dict[str, Any],
        decision: Decision,
        result: ToolResult | None,
        phrase: str,
        risk: Risk | None = None,
    ) -> None:
        # `risk`: el que decidió SafetyGuard con lo preparado (apagar es rojo aunque la
        # herramienta sea verde por «bloquear»); sin él, el de la herramienta.
        if self.log is None:
            return
        if risk is None and tool is not None:
            risk = tool.risk
        self.log.write(
            tool=name,
            params=params,
            decision=decision,
            ok=None if result is None else result.ok,
            message="" if result is None else result.message,
            phrase=phrase,
            risk=str(risk) if risk is not None else "",
        )

    def check(self, calls: list[ToolCall]) -> str:
        """Primer problema de un plan (herramienta desconocida o parámetros), o «»."""
        for call in calls:
            tool = self.registry.get(call.name)
            if tool is None:
                return f"la herramienta {call.name} no existe"
            try:
                tool.params_model.model_validate(call.arguments)
            except ValidationError as e:
                first = e.errors()[0]
                where = ".".join(str(x) for x in first["loc"]) or "parámetros"
                return f"{call.name}: {where}: {first['msg']}"
        return ""

    async def run(self, call: ToolCall, *, phrase: str = "", voice: bool = False) -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            log.warning("Herramienta desconocida: %s", call.name)
            result = ToolResult.fail("No sé hacer eso todavía")
            self._record(None, call.name, call.arguments, Decision.INVALID, result, phrase)
            return result
        try:
            params = tool.params_model.model_validate(call.arguments)
        except ValidationError as e:
            log.warning("Parámetros no válidos para %s: %s", call.name, e)
            p = self.phrases.pick("not_understood")
            result = ToolResult.fail(p.display, p.secondary)
            self._record(tool, call.name, call.arguments, Decision.INVALID, result, phrase)
            return result
        args = params.model_dump(exclude_none=True)
        if self.game is not None:
            policy = self.game.policy_for(tool)
            if policy is GamePolicy.BLOCKED:
                result = ToolResult.fail("En partida no hago eso", "pídemelo al terminar")
                self._record(tool, call.name, args, Decision.BLOCKED, result, phrase)
                return result
            if policy is GamePolicy.DEFERRED:
                # Se comprueba ya si tiene sentido («no veo esa ventana»), para no descubrirlo
                # al terminar la partida (ERRORES.md, 2026-11-11). Preparar no cambia nada.
                try:
                    early = await asyncio.wait_for(tool.prepare(params, self.ctx), tool.timeout_s)
                except Exception:
                    log.exception("Fallo comprobando %s antes de diferirlo", call.name)
                    early = Prepared("")
                if early.error is not None:
                    self._record(tool, call.name, args, Decision.EXECUTED, early.error, phrase)
                    return early.error
                if any(
                    d.call.name == call.name and d.call.arguments == call.arguments
                    for d in self.game.queue
                ):
                    result = ToolResult(
                        ok=True,
                        message="Ya lo tengo pendiente",
                        display="Ya lo tengo pendiente",
                        secondary=describe_call(call),
                        data={"deferred": True},
                    )
                    self._record(tool, call.name, args, Decision.DEFERRED, result, phrase)
                    return result
                summary = describe_call(call)
                self.game.defer(
                    ToolCall(call.name, dict(call.arguments)), phrase, summary, voice=voice
                )
                result = ToolResult(
                    ok=True,
                    message="Te lo hago al terminar la partida",
                    display="Al terminar la partida",
                    secondary=summary,
                    data={"deferred": True},
                )
                self._record(tool, call.name, args, Decision.DEFERRED, result, phrase)
                return result
        t0 = time.perf_counter()
        try:
            prepared = await asyncio.wait_for(tool.prepare(params, self.ctx), tool.timeout_s)
        except TimeoutError:
            p = self.phrases.pick("error_timeout")
            prepared = Prepared("", error=ToolResult.fail(p.display, p.secondary))
        except Exception:
            log.exception("Fallo preparando %s", call.name)
            p = self.phrases.pick("error_other")
            prepared = Prepared("", error=ToolResult.fail(p.display, p.secondary))
        if prepared.error is not None:
            self._record(tool, call.name, args, Decision.EXECUTED, prepared.error, phrase)
            return prepared.error

        decision = self.guard.evaluate(
            tool.risk, prepared, green_when_read_only=tool.green_when_read_only
        )
        logged = Decision.EXECUTED
        if decision.verdict is Verdict.BLOCK:
            log.warning("SafetyGuard bloquea %s: %s", call.name, decision.reason)
            result = ToolResult.fail(decision.reason, "por seguridad")
            self._record(tool, call.name, args, Decision.BLOCKED, result, phrase, decision.risk)
            return result
        if decision.verdict is Verdict.CONFIRM:
            if self.confirm is None:
                result = ToolResult.fail("Necesito que lo confirmes y ahora no puedo preguntarte")
                self._record(tool, call.name, args, Decision.BLOCKED, result, phrase, decision.risk)
                return result
            ok = await self.confirm(
                Confirmation(prepared.summary, prepared.detail, decision.click_only)
            )
            if not ok:
                result = cancelled_result(prepared.summary)
                self._record(
                    tool, call.name, args, Decision.CANCELLED, result, phrase, decision.risk
                )
                return result
            logged = Decision.CONFIRMED

        try:
            result = await asyncio.wait_for(
                tool.execute(params, self.ctx, prepared), tool.timeout_s
            )
        except TimeoutError:
            p = self.phrases.pick("error_timeout")
            result = ToolResult.fail(p.display, p.secondary)
        except Exception:
            log.exception("Fallo en la herramienta %s", call.name)
            p = self.phrases.pick("error_other")
            result = ToolResult.fail(p.display, p.secondary)
        if result.ok and result.undo is not None:
            entry = self.ctx.undo.push(result.undo)
            result.data["undo_id"] = entry.id
        log.info(
            "Acción %s(%s) → %s en %d ms: %s",
            call.name,
            args,
            "ok" if result.ok else "fallo",
            round((time.perf_counter() - t0) * 1000),
            result.message,
        )
        self._record(tool, call.name, args, logged, result, phrase, decision.risk)
        return result

    async def run_plan(
        self, calls: list[ToolCall], *, phrase: str = "", voice: bool = False
    ) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in calls:
            result = await self.run(call, phrase=phrase, voice=voice)
            results.append(result)
            if not result.ok:
                break
        return results
