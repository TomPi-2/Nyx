"""Grupos de herramientas y selector (0.6, tarea 6.20b)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, ClassVar

from nyx.brain.select import MAX_GROUPS, ToolSelector, tools_budget
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.groups import FIXED, GROUPS, MAX_FIXED_CHARS, MAX_GROUP_CHARS, Group
from nyx.tools.registry import ToolRegistry, default_registry

PHRASES = Path(__file__).parent / "battery" / "frases.jsonl"
# Frases cuya herramienta no se puede deducir por palabras: necesitan saber qué carpetas o
# apps hay (el índice). Las cubre el router o, si no, la lista que ya estaba (6.20c).
KNOWN_GAPS = {"ábreme lo de Pruebas Nyx"}


def names(tools: list[dict[str, Any]]) -> list[str]:
    return [t["function"]["name"] for t in tools]


def size(registry: ToolRegistry, tools: tuple[str, ...]) -> int:
    schemas = {t.name: t.schema() for t in registry.all()}
    return sum(len(json.dumps(schemas[n], ensure_ascii=False)) for n in tools)


# --- los grupos ---


def test_every_visible_tool_is_fixed_or_in_exactly_one_group() -> None:
    registry = default_registry()
    visible = {t.name for t in registry.all() if t.llm_visible}
    placed = [*FIXED, *(n for g in GROUPS for n in g.tools)]
    assert sorted(placed) == sorted(set(placed)), "una herramienta en dos sitios"
    assert set(placed) == visible


def test_groups_stay_small() -> None:
    """Cada grupo cabe en ~1.000 tokens: cambiar de grupo cuesta poco (6.20)."""
    registry = default_registry()
    assert size(registry, FIXED) <= MAX_FIXED_CHARS
    for group in GROUPS:
        assert group.keywords and group.about, group.name
        assert size(registry, group.tools) <= MAX_GROUP_CHARS, group.name


# --- el selector ---

# Presupuesto pequeño: no caben todas y se rotan los grupos (12.450 desde que «archivos»
# lleva save_note, 6.28: con 12.000 ya no cabía el clima junto a los dos de archivos).
TIGHT = 12450


def test_today_everything_fits_and_the_list_never_changes() -> None:
    """Con 12.288 de contexto caben las 39: la lista de siempre, sin cambios de caché."""
    registry = default_registry()
    sel = ToolSelector(registry, budget_chars=tools_budget(12288))
    assert sel.all_fit
    lazy = {n for g in GROUPS if g.lazy for n in g.tools}  # a demanda (0.8)
    every = [n for n in names(registry.schemas()) if n not in lazy]
    for text in ("¿cuánta batería me queda?", "mueve las fotos a Imágenes", "hola"):
        assert names(sel.select(text)) == every


def test_on_demand_groups_go_at_the_end_only_when_asked() -> None:
    """0.8: las de un grupo a demanda solo salen si la frase habla de su tema, y al final (lo
    de siempre sigue igual en la caché); en otra vuelta de la misma petición, también."""
    registry = default_registry()
    sel = ToolSelector(registry, budget_chars=tools_budget(12288))
    every = names(sel.select("hola"))
    asked = names(sel.select("añade leche a la lista de la compra"))
    assert asked[: len(every)] == every and asked[len(every) :] == ["list_items", "task"]
    assert names(sel.select("", keep=True)) == asked
    assert names(sel.select("¿tengo que coger paraguas mañana?")) == every


def test_smaller_context_does_not_fit_everything() -> None:
    assert not ToolSelector(default_registry(), budget_chars=tools_budget(8192)).all_fit


def test_fixed_tools_always_first_and_in_the_same_order() -> None:
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    for text in ("¿cuánta batería me queda?", "mueve las fotos a Imágenes", "hola"):
        assert names(sel.select(text))[: len(FIXED)] == list(FIXED)


def test_picks_the_groups_of_the_topic() -> None:
    sel = ToolSelector(default_registry())
    assert sel.groups_for("¿tengo que coger paraguas mañana?") == ("clima",)
    assert sel.groups_for("pon una alarma a las 7") == ("alarmas",)
    assert "equipo" in sel.groups_for("¿por qué va tan lento el PC?")
    both = sel.groups_for("baja el brillo y pon una alarma a las 8")
    assert "equipo" in both and "alarmas" in both
    assert sel.groups_for("¿quién pintó las Meninas?") == ()
    assert "equipo" not in sel.groups_for("abre Discord")  # «disco» no es «discord»


def test_new_groups_go_at_the_end_so_the_cache_still_serves() -> None:
    """Un grupo nuevo se añade al final: lo de antes es el mismo principio (caché de Ollama)."""
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    first = names(sel.select("¿tengo que coger paraguas mañana?"))
    second = names(sel.select("pon una alarma a las 7"))
    assert second[: len(first)] == first and "set_alarm" in second
    # Pedir otra vez lo que ya está no cambia nada.
    assert names(sel.select("¿va a llover?")) == second


def test_when_full_the_least_recently_used_group_leaves() -> None:
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    sel.select("¿tengo que coger paraguas mañana?")  # clima
    sel.select("pon una alarma a las 7")  # alarmas
    sel.select("¿va a llover?")  # clima otra vez: alarmas es ahora el más antiguo
    sel.select("mueve las fotos de Descargas a Imágenes")  # archivos y archivos_cambiar
    assert "archivos_cambiar" in sel.current and "clima" in sel.current
    assert "alarmas" not in sel.current
    assert len(json.dumps(sel.tools_for(sel.current), ensure_ascii=False)) <= TIGHT + 200


def test_no_clue_keeps_the_previous_list() -> None:
    """Sin pistas («ábrela», una pregunta de cultura) la lista no cambia: ni se pierde la
    caché de Ollama ni el seguimiento se queda sin las herramientas de antes."""
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    first = names(sel.select("busca la factura de la luz"))
    assert "find_files" in first
    assert names(sel.select("ábrela")) == first
    assert names(sel.select("¿quién pintó las Meninas?")) == first


def test_another_turn_of_the_same_request_keeps_the_list() -> None:
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    first = names(sel.select("busca la factura de la luz"))
    assert names(sel.select("pon una alarma a las 7", keep=True)) == first


def test_at_most_max_groups() -> None:
    sel = ToolSelector(default_registry())
    text = "mueve las fotos, pon una alarma, baja el brillo, ¿qué tiempo hace? y ¿qué suena?"
    assert len(sel.groups_for(text)) == MAX_GROUPS


def test_written_call_to_a_hidden_tool_is_recognised() -> None:
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    assert "get_weather" not in names(sel.select("pon una alarma a las 7"))
    assert "get_weather" in sel.names


def test_every_battery_phrase_finds_its_tool() -> None:
    """La vara de medir de la 6.17: cada frase con herramienta la tiene a la vista."""
    registry = default_registry()
    missing: list[str] = []
    for line in PHRASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if "tipo" in case or case["frase"] in KNOWN_GAPS:
            continue
        sel = ToolSelector(registry)
        visible = set(names(sel.tools_for(sel.groups_for(case["frase"]))))
        steps = case["plan"] if "plan" in case else [case["tool"]]
        for step in steps:
            if step != "wait_for_window" and not set(step.split("|")) & visible:
                missing.append(f"{case['frase']} → {step}")
    assert missing == []


# --- muchas extensiones (objetivo de la 6.20) ---


class _FakeParams(Params):
    text: str = ""


def _fake_tool(name: str) -> Tool[_FakeParams]:
    class Fake(Tool[_FakeParams]):
        description: ClassVar[str] = f"Herramienta de prueba {name}. Ej.: «haz {name}»."
        risk = Risk.GREEN
        game_policy = GamePolicy.ALLOWED
        category = Category.SYSTEM
        params_model = _FakeParams

        async def run(self, params: _FakeParams, ctx: ToolContext) -> ToolResult:
            return ToolResult(ok=True)

    Fake.name = name
    return Fake()


def test_two_hundred_extension_tools_do_not_grow_the_prompt() -> None:
    """200 herramientas de extensiones en 40 grupos: ya no caben todas, pero lo que ve el
    modelo sigue dentro del presupuesto, tiene lo que pide cada frase y elegir cuesta < 5 ms."""
    base = default_registry()
    extra = [_fake_tool(f"ext{i:03d}") for i in range(200)]
    registry = ToolRegistry([*base.all(), *extra])
    groups = [
        *GROUPS,
        *(
            Group(
                f"extension{g:02d}",
                f"extensión de prueba {g}",
                tuple(f"ext{g * 5 + i:03d}" for i in range(5)),
                (f"palabraext{g:02d}",),
            )
            for g in range(40)
        ),
    ]
    budget = tools_budget(12288)
    big = ToolSelector(registry, groups, budget_chars=budget)
    assert not big.all_fit
    texts = [
        "¿tengo que coger paraguas mañana?",
        "mueve las fotos de Descargas a Imágenes",
        "¿por qué va tan lento el PC?",
        "pon una alarma a las 7 todos los días",
        *(f"usa palabraext{g:02d} ahora" for g in range(40)),
    ]
    for text in texts:
        visible = big.select(text)
        assert len(json.dumps(visible, ensure_ascii=False)) <= budget + 200
        wanted = {n for g in big.groups_for(text) for n in big._by_name[g].tools}
        assert wanted <= set(names(visible)), text
    t0 = time.perf_counter()
    for _ in range(20):
        for text in texts:
            big.groups_for(text)
    per_call_ms = (time.perf_counter() - t0) * 1000 / (20 * len(texts))
    assert per_call_ms < 5


# --- índice de último recurso (7.15) ---


def test_the_index_is_only_asked_when_nothing_fits_and_there_is_no_clue() -> None:
    every = ToolSelector(default_registry())
    assert every.all_fit and not every.needs_index("necesito organizar mi trabajo de hoy")
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    assert sel.needs_index("necesito organizar mi trabajo de hoy")
    assert not sel.needs_index("ponme una alarma a las ocho")  # hay pistas: grupo por palabras
    assert not sel.needs_index("hola Nyx")  # charla corta: sin gastar una llamada
    lines = sel.index_lines()
    assert len(lines) == len(sel.groups) and all(": " in line for line in lines)


def test_picked_groups_are_used_when_there_is_no_clue() -> None:
    sel = ToolSelector(default_registry(), budget_chars=TIGHT)
    tools = names(
        sel.select("necesito organizar mi trabajo de hoy", picked=["alarmas", "inventado"])
    )
    assert "set_alarm" in tools and sel.current == ("alarmas",)
    # Con pistas mandan las palabras, no lo elegido.
    sel.select("sube el volumen", picked=["alarmas"])
    assert "musica" in sel.current or "set_volume" in names(sel.tools_for(sel.current))


async def test_brain_asks_the_index_in_a_short_call() -> None:
    from nyx.brain.service import Brain

    class IndexLLM:
        def __init__(self) -> None:
            self.asked: list[str] = []

        async def stream(self, messages: Any, *, schema: Any = None) -> Any:
            self.asked.append(messages[-1].content)
            yield '{"grupos": ["alarmas", "clima"]}'

    llm = IndexLLM()
    brain = Brain(llm, selector=ToolSelector(default_registry(), budget_chars=TIGHT))  # type: ignore[arg-type]
    assert await brain.pick_groups("necesito organizar mi trabajo de hoy") == ["alarmas", "clima"]
    assert "Petición: «necesito organizar mi trabajo de hoy»" in llm.asked[0]
    brain.use_index = False
    assert await brain.pick_groups("necesito organizar mi trabajo de hoy") == []
