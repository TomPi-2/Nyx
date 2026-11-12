"""Batería de frases (SPEC secciones 6 y 14): acierto y latencia del router y del LLM.

No ejecuta nada: cada frase pasa por el router y, si no encaja, por el LLM real (Ollama), y se
compara lo que se haría con lo esperado en tests/battery/frases.jsonl.

    uv run python scripts/battery.py                  # todas
    uv run python scripts/battery.py --solo spotify   # las que contienen «spotify»
    uv run python scripts/battery.py --informe ../docs/benchmarks/bateria.md
    uv run python scripts/battery.py --sin-grupos     # todas las herramientas (antes de 6.20b)
    uv run python scripts/battery.py --mezclar        # orden al azar: más cambios de grupo
    uv run python scripts/battery.py --contexto 8192  # como si no cupieran todas (grupos)

Formato de cada línea: {"frase": …, y una de:
    "tool": "open_app" (o "a|b"), "args": {…parciales…}   una acción
    "plan": ["open_app", "set_volume"]                    varios pasos en orden
    "tipo": "respuesta"                                   una respuesta en texto
    "tipo": "no_sabe"                                     no debe hacer nada (texto)}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nyx.brain.ollama import OllamaEngine
from nyx.brain.router import Miss, Route, refusal, route, written_command
from nyx.brain.select import ToolSelector, tools_budget
from nyx.brain.service import Brain, ReplyDone, ToolPlan
from nyx.executor import ToolCall, with_waits
from nyx.index.aliases import normalize
from nyx.index.service import SystemIndex
from nyx.pipeline import MISS_LLM_MIN
from nyx.settings.model import load_settings
from nyx.tools.registry import default_registry

PHRASES = Path(__file__).resolve().parents[1] / "tests" / "battery" / "frases.jsonl"
REGISTRY = default_registry()


@dataclass
class Outcome:
    frase: str
    path: str  # router | llm | no_encontrado
    ok: bool
    got: str
    why: str = ""
    ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def describe(calls: list[ToolCall]) -> str:
    return "; ".join(f"{c.name}({json.dumps(c.arguments, ensure_ascii=False)})" for c in calls)


def same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        e, a = normalize(expected), normalize(actual)
        return bool(e) and (e in a or a in e)
    return bool(expected == actual)


def invalid(calls: list[ToolCall]) -> str:
    for call in calls:
        tool = REGISTRY.get(call.name)
        if tool is None:
            return f"{call.name} no existe"
        try:
            tool.params_model.model_validate(call.arguments)
        except ValidationError as e:
            return f"{call.name}: {e.errors()[0]['msg']}"
    return ""


def judge(case: dict[str, Any], calls: list[ToolCall] | None, text: str | None) -> tuple[bool, str]:
    if "tipo" in case:
        if calls:
            return False, "ha actuado"
        if case["tipo"] == "respuesta" and (not text or "aun no se" in normalize(text)):
            return False, "sin respuesta útil"
        return True, ""
    if not calls:
        return False, "no ha actuado"
    if problem := invalid(calls):
        return False, f"llamada no válida ({problem}; en Nyx se reintentaría)"
    if "plan" in case:
        names = [c.name for c in calls]
        wanted = [set(step.split("|")) for step in case["plan"]]
        if len(names) != len(wanted) or any(
            n not in w for n, w in zip(names, wanted, strict=False)
        ):
            return False, f"plan distinto: {names}"
        return True, ""
    steps = [c for c in calls if c.name != "wait_for_window"]
    options = set(case["tool"].split("|"))
    if len(steps) != 1 or steps[0].name not in options:
        return False, f"esperaba {case['tool']}"
    for key, value in case.get("args", {}).items():
        if not same(value, steps[0].arguments.get(key)):
            return False, f"{key}={steps[0].arguments.get(key)!r} (esperaba {value!r})"
    return True, ""


async def run_case(case: dict[str, Any], index: SystemIndex, brain: Brain) -> Outcome:
    text = case["frase"]
    t0 = time.perf_counter()
    if (no := refusal(text, index)) is not None:
        ms = (time.perf_counter() - t0) * 1000
        ok, why = judge(case, None, no[0])
        return Outcome(text, "negativa", ok, f"«{no[0]}»", why, ms)
    routed = route(text, index)
    if isinstance(routed, Route):
        ms = (time.perf_counter() - t0) * 1000
        ok, why = judge(case, routed.calls, None)
        return Outcome(text, "router", ok, describe(routed.calls), why, ms)
    hint = ""
    if isinstance(routed, Miss):
        if not routed.candidates or routed.candidates[0].score < MISS_LLM_MIN:
            ms = (time.perf_counter() - t0) * 1000
            got = f"No encuentro «{routed.target}»"
            ok, why = judge(case, None, got)
            return Outcome(text, "no_encontrado", ok, got, why, ms)
        names = ", ".join(m.entry.name for m in routed.candidates[:3])
        hint = f"«{routed.target}» no coincide con nada instalado. Lo más parecido: {names}."
    brain.memory.clear()
    calls: list[ToolCall] | None = None
    reply = ""
    first: float | None = None
    async for event in brain.respond(text, hint):
        first = first or (time.perf_counter() - t0) * 1000
        if isinstance(event, ToolPlan):
            calls = with_waits([ToolCall(c.name, c.arguments) for c in event.calls])
        elif isinstance(event, ReplyDone):
            reply = event.reply.spoken
    ms = (time.perf_counter() - t0) * 1000
    ok, why = judge(case, calls, reply if calls is None else None)
    got = describe(calls) if calls else f"«{reply}»"
    return Outcome(text, "llm", ok, got, why, ms, {"first_ms": first or ms})


def report(outcomes: list[Outcome], model: str, how: str = "") -> str:
    total = len(outcomes)
    good = sum(o.ok for o in outcomes)
    lines = [
        f"# Batería de frases · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Modelo: `{model}`. Frases: {total}. "
        f"**Acierto: {good}/{total} ({100 * good / total:.0f} %)**.",
        "",
    ]
    if how:
        lines += [how, ""]
    # Primer token en la primera pasada de cada frase del LLM: las repeticiones (--veces)
    # encuentran la caché ya caliente y engañarían.
    firsts = [o.extra["first_try_ms"] for o in outcomes if "first_try_ms" in o.extra]
    if firsts:
        lines += [
            f"Primer token en lo que pasa por el LLM (primera pasada): mediana "
            f"**{statistics.median(firsts):.0f} ms**, media **{statistics.mean(firsts):.0f} ms**, "
            f"peor {max(firsts):.0f} ms.",
            "",
        ]
    lines += [
        "| Camino | Frases | Acierto | Latencia mediana | Peor |",
        "| --- | --- | --- | --- | --- |",
    ]
    for path in ("negativa", "router", "llm", "no_encontrado"):
        group = [o for o in outcomes if o.path == path]
        if not group:
            continue
        times = [o.ms for o in group]
        hits = sum(o.ok for o in group)
        lines.append(
            f"| {path} | {len(group)} | {hits}/{len(group)} | {statistics.median(times):.0f} ms "
            f"| {max(times):.0f} ms |"
        )
    failures = [o for o in outcomes if not o.ok]
    if failures:
        lines += [
            "",
            "## Fallos",
            "",
            "| Frase | Camino | Qué hizo | Por qué |",
            "| --- | --- | --- | --- |",
        ]

        def cell(text: str, limit: int = 0) -> str:
            # Ni saltos de línea ni «|»: romperían la tabla.
            flat = " ".join(text.split()).replace("|", "/")
            return flat[:limit] if limit else flat

        for o in failures:
            lines.append(f"| {cell(o.frase)} | {o.path} | {cell(o.got, 120)} | {cell(o.why)} |")
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo", help="solo las frases que contienen este texto")
    parser.add_argument("--informe", type=Path, help="guardar el informe en Markdown")
    parser.add_argument(
        "--veces",
        type=int,
        default=3,
        help="cuántas veces se pasa cada frase del LLM; cuenta la mayoría (tarea 6.18: con "
        "una sola pasada, la suerte engaña)",
    )
    parser.add_argument(
        "--sin-grupos",
        action="store_true",
        help="el modelo ve todas las herramientas siempre (como antes de la 6.20b)",
    )
    parser.add_argument(
        "--mezclar",
        type=int,
        nargs="?",
        const=1,
        default=None,
        metavar="SEMILLA",
        help="frases en orden al azar (más cambios de grupo y de caché, como en el uso real)",
    )
    parser.add_argument("--modelo", default=None, help="otro modelo de Ollama (6.21)")
    parser.add_argument(
        "--con-aviso",
        action="store_true",
        help="con el aviso de «esto se resuelve con herramientas» (6.21; desactivado en Nyx)",
    )
    parser.add_argument(
        "--sin-reencaminar",
        action="store_true",
        help="las órdenes que el LLM escribe como texto no pasan por el router (antes de 6.21)",
    )
    parser.add_argument(
        "--contexto",
        type=int,
        default=None,
        metavar="TOKENS",
        help="presupuesto de herramientas como si `llm.num_ctx` fuera este (p. ej. 8192: no "
        "caben todas y se rotan por grupos); Ollama sigue con el contexto de los ajustes",
    )
    args = parser.parse_args()

    cases = [
        json.loads(line)
        for line in PHRASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.solo:
        cases = [c for c in cases if args.solo.lower() in c["frase"].lower()]
    if args.mezclar is not None:
        random.Random(args.mezclar).shuffle(cases)
    settings = load_settings()
    model = args.modelo or settings.llm.model
    llm = OllamaEngine(settings.llm.host, model, num_ctx=settings.llm.num_ctx, timeout_s=60)
    if args.sin_grupos:
        brain = Brain(llm, tools=REGISTRY.schemas())
        how = "Herramientas: todas en cada petición (sin grupos)."
    else:
        ctx = args.contexto or settings.llm.num_ctx
        selector = ToolSelector(REGISTRY, budget_chars=tools_budget(ctx))
        brain = Brain(llm, selector=selector)
        how = (
            "Herramientas: todas (caben en su parte del contexto)."
            if selector.all_fit
            else f"Herramientas: fijas + grupos usados hace poco (no caben con {ctx} de contexto)."
        )
    if args.mezclar is not None:
        how += f" Orden al azar (semilla {args.mezclar})."
    index = SystemIndex.open()
    brain.tools_hint = args.con_aviso
    if not args.sin_reencaminar:
        brain.reroute = lambda text: written_command(text, index)  # como en Nyx (6.21)
    await brain.warmup()
    outcomes: list[Outcome] = []
    for case in cases:
        outcome = await run_case(case, index, brain)
        first_try = outcome.extra.get("first_ms")
        if outcome.path == "llm" and args.veces > 1:
            # El modelo no responde siempre igual: se repite y cuenta la mayoría.
            tries = [outcome] + [await run_case(case, index, brain) for _ in range(args.veces - 1)]
            good = sum(t.ok for t in tries)
            outcome = next(t for t in tries if t.ok == (good * 2 > len(tries)))
            if 0 < good < len(tries):
                outcome.why = (outcome.why + " " if outcome.why else "") + f"({good}/{len(tries)})"
        if first_try is not None:
            outcome.extra["first_try_ms"] = first_try
        outcomes.append(outcome)
        mark = "✓" if outcome.ok else "✗"
        print(
            f"{mark} {outcome.ms:6.0f} ms  {outcome.path:13} {outcome.frase}  →  {outcome.got[:90]}"
            + (f"  [{outcome.why}]" if outcome.why else "")
        )
    await llm.aclose()
    index.close()
    text = report(outcomes, model, how)
    print()
    print(text.split("## Fallos")[0])
    if args.informe:
        args.informe.parent.mkdir(parents=True, exist_ok=True)
        args.informe.write_text(text, encoding="utf-8")
        print(f"Informe: {args.informe}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
