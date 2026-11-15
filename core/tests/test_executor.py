import asyncio
from typing import ClassVar

from nyx.executor import Executor, ToolCall
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.registry import ToolRegistry, default_registry


class EchoParams(Params):
    text: str


class Echo(Tool[EchoParams]):
    name = "echo"
    description = "repite"
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.SYSTEM
    params_model = EchoParams
    calls: ClassVar[list[str]] = []

    async def run(self, params: EchoParams, ctx: ToolContext) -> ToolResult:
        type(self).calls.append(params.text)
        if params.text == "boom":
            raise RuntimeError("boom")
        if params.text == "lento":
            await asyncio.sleep(1)
        if params.text == "falla":
            return ToolResult.fail("no")
        return ToolResult(ok=True, message=params.text)


class Danger(Echo):
    name = "danger"
    risk = Risk.RED


def make(ctx: ToolContext) -> Executor:
    Echo.calls = []
    return Executor(ToolRegistry([Echo(), Danger()]), ctx)


async def test_runs_and_validates(ctx: ToolContext) -> None:
    ex = make(ctx)
    assert (await ex.run(ToolCall("echo", {"text": "hola"}))).ok
    bad = await ex.run(ToolCall("echo", {"texto": "hola"}))
    assert not bad.ok and Echo.calls == ["hola"]
    assert not (await ex.run(ToolCall("no_existe"))).ok


async def test_tool_errors_and_timeouts_are_contained(ctx: ToolContext) -> None:
    ex = make(ctx)
    assert not (await ex.run(ToolCall("echo", {"text": "boom"}))).ok
    Echo.timeout_s = 0.05
    try:
        assert not (await ex.run(ToolCall("echo", {"text": "lento"}))).ok
    finally:
        Echo.timeout_s = 10.0


async def test_non_green_is_blocked_until_safety_guard(ctx: ToolContext) -> None:
    ex = make(ctx)
    result = await ex.run(ToolCall("danger", {"text": "x"}))
    assert not result.ok and Echo.calls == []


async def test_plan_stops_at_first_failure(ctx: ToolContext) -> None:
    ex = make(ctx)
    calls = [ToolCall("echo", {"text": t}) for t in ("a", "falla", "c")]
    results = await ex.run_plan(calls)
    assert [r.ok for r in results] == [True, False]
    assert Echo.calls == ["a", "falla"]


def test_default_registry_tools_are_complete() -> None:
    tools = default_registry().all()
    # las 20 de la fase 3 + undo + send_hotkey y app_action + open_nyx_settings (5c) + 0.6
    # + run_powershell (6.13), install_app y ui_action (6.14), web_search (6.06), save_note (6.28)
    # + nyx_panel (9.11)
    assert len(tools) == 49  # + nyx_update (9.06), list_items y task (8.01)
    for tool in tools:
        assert tool.description and tool.risk and tool.game_policy and tool.category
        assert tool.schema()["function"]["name"] == tool.name


def test_every_tool_has_a_spanish_verb() -> None:
    # Sin verbo, la descripción de lo hecho llevaba el nombre interno y el modelo lo copiaba
    # en la burbuja («[nyxinfo quien eres | …]», 6.03). Al añadir una herramienta, añade su
    # verbo en _VERBS de nyx/executor.py.
    from nyx.executor import _VERBS

    missing = [t.name for t in default_registry().all() if t.name not in _VERBS]
    assert missing == []


def test_describe_call_translates_enum_values_without_touching_user_text() -> None:
    from nyx.executor import describe_call

    assert describe_call(ToolCall("system_info", {"what": "battery"})) == "mirar la batería"
    assert describe_call(ToolCall("clipboard", {"action": "read"})) == "leer el portapapeles"
    assert describe_call(ToolCall("media_control", {"action": "pause", "source": "spotify"})) == (
        "pausar la música spotify"
    )
    assert describe_call(ToolCall("system_power", {"action": "shutdown"})) == "apagar el equipo"
    assert describe_call(ToolCall("type_text", {"text": "stop battery"})) == "escribir stop battery"
    # Un valor que coincide con una opción de otra herramienta no se toca (antes «top» salía
    # como «los procesos» y «stop» como «parar» en cualquier parámetro).
    assert describe_call(ToolCall("open_url", {"target": "top"})) == "abrir top"
    assert describe_call(ToolCall("set_alarm", {"time": "07:30", "repeat": True})) == (
        "poner una alarma a las 07:30"
    )


def test_every_closed_option_has_its_phrase() -> None:
    """Las opciones de `action`/`what` de una herramienta, todas o ninguna, con su frase."""
    from typing import get_args

    from nyx.executor import _OPTION_ARGS, _OPTION_VERBS

    for tool in default_registry().all():
        if not any(name == tool.name for name, _ in _OPTION_VERBS):
            continue
        fields = tool.params_model.model_fields
        arg = next(a for a in _OPTION_ARGS if a in fields)
        options = set(get_args(fields[arg].annotation))
        assert options == {o for name, o in _OPTION_VERBS if name == tool.name}, tool.name
