"""Ejemplos para el LoRA del cerebro (6.27, paso 2). Todo en local: las reglas de Nyx y el 7B.

Etapas (con el entorno de Nyx, desde core/):

    uv run python training/llm/make_dataset.py semillas     # frases con su llamada (reglas)
    uv run python training/llm/make_dataset.py parafrasis   # el 7B las dice de otras formas
    uv run python training/llm/make_dataset.py charla       # preguntas y respuestas con cabecera
    uv run python training/llm/make_dataset.py inventadas   # herramientas que Nyx no tiene
    uv run python training/llm/make_dataset.py juntar       # train.jsonl y valid.jsonl

Ideas clave:

- Las reglas resuelven antes que el modelo lo que entienden, así que lo que vale es lo que NO
  entienden pero tiene una intención clara: paráfrasis más libres de frases cuya llamada sí
  saben las reglas (la paráfrasis hereda la llamada si conserva los datos: app, número, hora).
- La batería (`tests/battery/frases.jsonl`) y la reserva (`reserva.jsonl`) no entran nunca.
- Los mensajes se arman con el mismo `Brain.build_messages` y las mismas herramientas que Nyx,
  para que el modelo aprenda exactamente con lo que verá.
- Herramientas inventadas, para que aprenda a usar herramientas en general y no empeore con
  las de las extensiones (0.7).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from nyx.brain.base import ChatMessage
from nyx.brain.guard import looks_like_code, mentions_tool, tool_keys
from nyx.brain.ollama import OllamaEngine
from nyx.brain.panel import BARE
from nyx.brain.router import Route, refusal, route
from nyx.brain.service import Brain, ReplyDone, ToolPlan
from nyx.index.aliases import normalize
from nyx.index.service import SystemIndex
from nyx.settings.model import load_settings
from nyx.stt.normalize import NUMBER_WORDS
from nyx.tools.registry import default_registry

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CORE = HERE.parents[1]
BATTERY = CORE / "tests" / "battery"
RNG = random.Random(627)
MAX_CHAT = 350  # ejemplos de charla como mucho (ver stage_build)

Calls = list[dict[str, Any]]


def jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def excluded() -> set[str]:
    """Frases de la batería y de la reserva: nunca para entrenar."""
    out: set[str] = set()
    for name in ("frases.jsonl", "reserva.jsonl"):
        for row in jsonl_read(BATTERY / name):
            out.add(normalize(row["frase"]))
    return out


# --- semillas ---

APPS = [
    "Spotify", "Discord", "Chrome", "Steam", "Word", "Excel", "PowerPoint", "OBS",
    "el bloc de notas", "la calculadora", "Paint", "Fortnite", "Visual Studio Code",
]  # fmt: skip
CITIES = ["Madrid", "Sevilla", "Valencia", "Bilbao", "Zaragoza", "Málaga", "Granada", "Vigo"]
TEMPLATES = [
    "abre {app}", "cierra {app}", "cambia a {app}", "maximiza {app}", "minimiza {app}",
    "pon {app} a la izquierda", "pon {app} a la derecha", "sube el volumen de {app}",
    "baja el volumen de {app}", "silencia {app}", "pon el volumen al {n}", "pon el brillo al {n}",
    "sube el brillo", "baja el brillo", "pon una alarma a las {h}", "despiértame mañana a las {h}",
    "pon un temporizador de {m} minutos", "avísame en {m} minutos", "¿qué tiempo hace en {city}?",
    "¿va a llover mañana en {city}?", "¿cuánta batería me queda?", "¿cuánta RAM estoy usando?",
    "¿cuánto espacio libre me queda?", "¿qué programa consume más CPU?", "¿qué suena?",
    "pausa la música", "siguiente canción", "canción anterior", "reanuda la música",
    "haz una captura de pantalla", "¿qué alarmas tengo?", "cancela el temporizador",
    "empieza el cronómetro", "para el cronómetro", "¿cuánto lleva el cronómetro?",
    "apaga el wifi", "enciende el wifi", "apaga el bluetooth", "enciende el bluetooth",
    "bloquea el ordenador", "¿qué hay en Descargas?", "abre la carpeta de Documentos",
    "crea una carpeta llamada {word} en el escritorio", "busca el archivo {word}",
    "abre los ajustes de sonido", "abre los ajustes de pantalla", "¿qué tengo copiado?",
    "deshaz eso", "abre youtube.com", "ponte de color azul", "habla más despacio",
    "¿qué cosas sabes hacer?", "abre tus ajustes", "pon los auriculares",
]  # fmt: skip
WORDS = ["Facturas", "Viajes", "Trabajo", "Fotos2025", "Recetas", "Clase", "Proyecto"]
HOURS = [
    "7",
    "7 y media",
    "8",
    "9 y cuarto",
    "6 de la tarde",
    "10",
    "las 23:30".replace("las ", ""),
]


def _expand() -> list[str]:
    out: list[str] = []
    for tpl in TEMPLATES:
        for _ in range(3 if "{" in tpl else 1):
            out.append(
                tpl.format(
                    app=RNG.choice(APPS),
                    n=RNG.choice([10, 20, 30, 40, 50, 60, 70, 80, 100]),
                    h=RNG.choice(HOURS),
                    m=RNG.choice([2, 3, 5, 10, 12, 15, 20, 25, 30, 45]),
                    city=RNG.choice(CITIES),
                    word=RNG.choice(WORDS),
                )
            )
    return out


def _test_strings() -> list[str]:
    out: list[str] = []
    for path in (CORE / "tests").glob("test_router*.py"):
        out += re.findall(r'"([^"\n{}()^$\\]{6,90})"', path.read_text(encoding="utf-8"))
    return out


# Carpetas por su nombre, como las dice el usuario (y como pide el prompt): nunca la ruta del
# equipo, que el modelo podría aprenderse (privacidad: el LoRA puede distribuirse con Nyx).
_FOLDER_NAMES = {
    "downloads": "Descargas", "documents": "Documentos", "desktop": "Escritorio",
    "pictures": "Imágenes", "videos": "Vídeos", "music": "Música",
}  # fmt: skip


def _no_paths(calls: Calls) -> Calls | None:
    out: Calls = []
    for call in calls:
        args = dict(call["arguments"])
        for key, value in args.items():
            if isinstance(value, str) and re.search(r"[A-Za-z]:\\|\\Users\\", value):
                name = _FOLDER_NAMES.get(Path(value).name.casefold())
                if name is None:
                    return None  # una ruta que no es una carpeta conocida: fuera
                args[key] = name
        out.append({"name": call["name"], "arguments": args})
    return out


def stage_seeds() -> None:
    skip = excluded()
    index = SystemIndex.open()
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for text in [*_test_strings(), *_expand()]:
        key = normalize(text)
        if key in seen or key in skip or len(text.split()) < 2:
            continue
        seen.add(key)
        if refusal(text, index) is not None:
            continue
        routed = route(text, index)
        if isinstance(routed, Route):
            calls = _no_paths([{"name": c.name, "arguments": c.arguments} for c in routed.calls])
            if calls is not None:
                rows.append({"text": text, "calls": calls})
    index.close()
    jsonl_write(DATA / "seeds.jsonl", rows)
    print(f"{len(rows)} semillas")


# --- paráfrasis ---

PARAPHRASE = """Eres un generador de frases para entrenar a un asistente de voz de PC en español \
de España. Te doy una petición. Escribe {k} formas DISTINTAS de pedir EXACTAMENTE lo mismo, como \
la diría una persona real hablando: coloquial, con rodeos, explicando el motivo, preguntando, \
con muletillas («oye», «porfa», «venga»), en otro orden…{keep} No añadas peticiones nuevas. \
Una frase por línea, sin numerar ni comillas.

Petición: {text}"""


# Restos de la instrucción que a veces se cuelan en la paráfrasis.
_LEAK = re.compile(r"\(ningun|petici[oó]n:|\bmant[eé]n\b|datos? (?:clave|iguales)", re.I)


def _keep_values(calls: Calls) -> list[str]:
    values: list[str] = []
    for call in calls:
        for key, value in call["arguments"].items():
            if isinstance(value, str) and len(value) >= 3 and key not in ("action", "what"):
                values.append(value)
            elif isinstance(value, int) and not isinstance(value, bool):
                values.append(str(value))
    return values


_WORD_FOR = {v: k for k, v in NUMBER_WORDS.items()}


def _has_value(text: str, value: str) -> bool:
    norm = normalize(text)
    if value.isdigit():
        word = _WORD_FOR.get(int(value))
        return bool(re.search(rf"\b{value}\b", norm)) or (word is not None and word in norm)
    if re.fullmatch(r"\d{2}:\d{2}", value):  # hora: basta la hora
        hour = int(value[:2]) % 12 or 12
        word = _WORD_FOR.get(hour)
        return bool(re.search(rf"\b{hour}\b|\b{int(value[:2])}\b", norm)) or (
            word is not None and word in norm
        )
    words = [w for w in normalize(value).split() if len(w) >= 3]
    return any(w in norm for w in words) if words else True


async def _chat(client: httpx.AsyncClient, model: str, prompt: str, temperature: float) -> str:
    reply = await client.post(
        "/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 12288},
        },
        timeout=120,
    )
    reply.raise_for_status()
    return str(reply.json()["message"]["content"])


async def stage_paraphrase(per_seed: int) -> None:
    settings = load_settings()
    skip = excluded()
    index = SystemIndex.open()
    seeds = jsonl_read(DATA / "seeds.jsonl")
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=settings.llm.host) as client:
        for i, seed in enumerate(seeds):
            keep = _keep_values(seed["calls"])
            prompt = PARAPHRASE.format(
                k=per_seed,
                text=seed["text"],
                keep=f" Mantén igual estos datos: {', '.join(keep)}." if keep else "",
            )
            try:
                raw = await _chat(client, settings.llm.model, prompt, 0.9)
            except httpx.HTTPError as exc:
                print(f"  fallo con {seed['text']!r}: {exc}", file=sys.stderr)
                continue
            for line in raw.splitlines():
                text = line.strip().strip("-•*0123456789.) ").strip("«»\"'")
                if (
                    not text
                    or len(text.split()) > 25
                    or normalize(text) in skip
                    or _LEAK.search(text)
                ):
                    continue
                if normalize(text) == normalize(seed["text"]):
                    continue
                if not all(_has_value(text, v) for v in keep):
                    continue
                routed = route(text, index)
                router_ok = (
                    isinstance(routed, Route)
                    and [{"name": c.name, "arguments": c.arguments} for c in routed.calls]
                    == seed["calls"]
                )
                rows.append(
                    {
                        "text": text,
                        "calls": seed["calls"],
                        "seed": seed["text"],
                        "router": router_ok,
                    }
                )
            if i % 25 == 0:
                print(f"{i}/{len(seeds)} semillas · {len(rows)} paráfrasis", flush=True)
    index.close()
    jsonl_write(DATA / "paraphrases.jsonl", rows)
    print(f"{len(rows)} paráfrasis ({sum(not r['router'] for r in rows)} que las reglas no cogen)")


# --- charla ---

TOPICS = [
    "cultura general", "historia", "ciencia", "geografía", "idiomas y traducciones de una palabra",
    "cálculos sencillos", "definiciones de palabras", "cocina y recetas rápidas", "deportes",
    "cine y series", "música", "consejos rápidos del día a día", "tecnología", "animales",
    "chistes y adivinanzas", "saludos y charla corta con un asistente", "salud y bienestar básico",
]  # fmt: skip
QUESTIONS = """Escribe {k} preguntas o frases cortas y variadas que una persona le diría en voz \
alta a su asistente de PC sobre «{topic}», en español de España. Nada sobre el estado del PC, \
archivos ni apps. Una por línea, sin numerar."""


async def stage_chat(per_topic: int) -> None:
    settings = load_settings()
    skip = excluded()
    registry = default_registry()
    keys = tool_keys(t.name for t in registry.all())
    questions: list[str] = []
    async with httpx.AsyncClient(base_url=settings.llm.host) as client:
        for topic in TOPICS:
            raw = await _chat(
                client, settings.llm.model, QUESTIONS.format(k=per_topic, topic=topic), 1.0
            )
            for line in raw.splitlines():
                q = line.strip().strip("-•*0123456789.) ").strip("«»\"'")
                if 2 <= len(q.split()) <= 20 and normalize(q) not in skip:
                    questions.append(q)
    questions = list(dict.fromkeys(questions))
    print(f"{len(questions)} preguntas")
    llm = OllamaEngine(
        settings.llm.host, settings.llm.model, num_ctx=settings.llm.num_ctx, timeout_s=60
    )
    brain = Brain(llm, tools=registry.schemas())
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        brain.memory.clear()
        reply = None
        acted = False
        async for event in brain.respond(q):
            if isinstance(event, ToolPlan):
                acted = True
            elif isinstance(event, ReplyDone):
                reply = event.reply
        if acted or reply is None or not reply.display or not reply.spoken:
            continue
        text = f"{reply.display} {reply.secondary} {reply.spoken}"
        if looks_like_code(text) or mentions_tool(text, keys):
            continue
        if " ".join(normalize(reply.display).split()) in BARE:
            continue  # cabecera vacía: no se enseña
        if reply.spoken.count(".") > 3 or "aun no se" in normalize(reply.spoken):
            continue
        header = (
            f"[{reply.display} | {reply.secondary}]" if reply.secondary else f"[{reply.display}]"
        )
        rows.append({"text": q, "reply": f"{header}\n{reply.spoken}"})
        if i % 50 == 0:
            print(f"{i}/{len(questions)} · {len(rows)} buenas", flush=True)
    await llm.aclose()
    jsonl_write(DATA / "chat.jsonl", rows)
    print(f"{len(rows)} respuestas de charla")


# Lo que el 7B dice que hace o hará sin hacerlo (el «no actúa» que se quiere quitar).
_CLAIMS = re.compile(
    r"\b(?:abro|abrir[eé]|busco|buscar[eé]|pongo|pondr[eé]|voy a|te (?:abro|pongo|busco)|"
    r"he (?:abierto|puesto|buscado|creado)|puedo (?:buscar|abrir|poner)|en tu "
    r"(?:biblioteca|pc|ordenador|equipo))\b",
    re.I,
)


def clean_chat(reply: str) -> str | None:
    """Una respuesta de charla apta para entrenar, o None. La cabecera tiene que ser del
    modelo (corta, sin «…»: si no la escribe, Nyx la saca de la voz y sale recortada) y la
    línea grande va con mayúscula (6.23)."""
    header, _, spoken = reply.partition("\n")
    inner = header.strip().strip("[]")
    display, _, secondary = inner.partition("|")
    display, secondary = display.strip(), secondary.strip()
    if not display or display.endswith(("…", ".", "?", "!")) or len(display.split()) > 6:
        return None  # sin cabecera propia, o la cabecera es una frase entera
    if _CLAIMS.search(spoken) or not spoken.strip():
        return None
    display = display[:1].upper() + display[1:]
    head = f"[{display} | {secondary}]" if secondary else f"[{display}]"
    return f"{head}\n{spoken.strip()}"


# --- herramientas inventadas ---

INVENTED: list[tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]] = [
    (
        {"name": "luces_casa", "description": "Enciende o apaga las luces de una habitación.",
         "parameters": {"type": "object", "properties": {
             "habitacion": {"type": "string", "description": "Habitación (salón, cocina…)"},
             "encender": {"type": "boolean", "description": "true = encender"}},
             "required": ["habitacion", "encender"]}},
        [("enciende la luz del salón", {"habitacion": "salón", "encender": True}),
         ("apaga las luces de la cocina", {"habitacion": "cocina", "encender": False}),
         ("no veo nada en el dormitorio, da la luz", {"habitacion": "dormitorio", "encender": True}),
         ("oye, apágame la luz del baño", {"habitacion": "baño", "encender": False})],
    ),
    (
        {"name": "termostato", "description": "Pone la calefacción a una temperatura.",
         "parameters": {"type": "object", "properties": {
             "grados": {"type": "integer", "description": "Temperatura en °C"}},
             "required": ["grados"]}},
        [("pon la calefacción a 21 grados", {"grados": 21}),
         ("tengo frío, sube la calefacción a 23", {"grados": 23}),
         ("deja la casa a 19 grados", {"grados": 19})],
    ),
    (
        {"name": "lista_compra", "description": "Añade un producto a la lista de la compra.",
         "parameters": {"type": "object", "properties": {
             "producto": {"type": "string", "description": "Lo que hay que comprar"}},
             "required": ["producto"]}},
        [("apunta leche en la lista de la compra", {"producto": "leche"}),
         ("se nos han acabado los huevos, añádelos a la compra", {"producto": "huevos"}),
         ("que no se me olvide comprar pan", {"producto": "pan"})],
    ),
    (
        {"name": "regar_plantas", "description": "Activa el riego de una zona del jardín.",
         "parameters": {"type": "object", "properties": {
             "zona": {"type": "string", "description": "Zona (huerto, césped…)"},
             "minutos": {"type": "integer", "description": "Minutos de riego"}},
             "required": ["zona"]}},
        [("riega el huerto 10 minutos", {"zona": "huerto", "minutos": 10}),
         ("el césped está seco, ponle agua", {"zona": "césped"})],
    ),
    (
        {"name": "estado_servidor", "description": "Dice si un servidor de juegos está en línea.",
         "parameters": {"type": "object", "properties": {
             "juego": {"type": "string", "description": "Juego"}},
             "required": ["juego"]}},
        [("¿están caídos los servidores del Valorant?", {"juego": "Valorant"}),
         ("¿funciona el servidor de Minecraft?", {"juego": "Minecraft"}),
         ("no me deja entrar al Fortnite, ¿está caído?", {"juego": "Fortnite"})],
    ),
    (
        {"name": "traducir_pantalla", "description": "Traduce el texto seleccionado en pantalla.",
         "parameters": {"type": "object", "properties": {
             "idioma": {"type": "string", "description": "Idioma de destino"}},
             "required": ["idioma"]}},
        [("tradúceme al inglés lo que tengo seleccionado", {"idioma": "inglés"}),
         ("pásame esto al francés", {"idioma": "francés"})],
    ),
    (
        {"name": "modo_concentracion", "description": "Activa o quita el modo sin distracciones.",
         "parameters": {"type": "object", "properties": {
             "activar": {"type": "boolean", "description": "true = activar"},
             "minutos": {"type": "integer", "description": "Duración en minutos"}},
             "required": ["activar"]}},
        [("necesito concentrarme una hora, quita las distracciones", {"activar": True, "minutos": 60}),
         ("ya he terminado de estudiar, quita el modo concentración", {"activar": False})],
    ),
]  # fmt: skip


def stage_invented() -> None:
    rows: list[dict[str, Any]] = []
    for schema, examples in INVENTED:
        for text, args in examples:
            rows.append({"text": text, "calls": [{"name": schema["name"], "arguments": args}],
                         "tool": schema})  # fmt: skip
    jsonl_write(DATA / "invented.jsonl", rows)
    print(f"{len(rows)} ejemplos con herramientas inventadas")


# --- juntar ---


def _msg(m: ChatMessage) -> dict[str, Any]:
    return {"role": m.role, "content": m.content}


def stage_build(valid_share: float) -> None:
    registry = default_registry()
    schemas = registry.schemas()
    brain = Brain(llm=None, tools=schemas)  # type: ignore[arg-type]  # solo build_messages
    start = datetime(2026, 11, 13, 8, 0)
    examples: list[dict[str, Any]] = []

    def add(text: str, assistant: dict[str, Any], tools: list[dict[str, Any]]) -> None:
        brain._clock = lambda: start + timedelta(minutes=RNG.randint(0, 60 * 24 * 60))
        messages = [_msg(m) for m in brain.build_messages(text)]
        examples.append({"messages": [*messages, assistant], "tools": tools})

    def calls_msg(calls: Calls) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"type": "function", "function": c} for c in calls],
        }

    for row in jsonl_read(DATA / "seeds.jsonl"):
        add(row["text"], calls_msg(row["calls"]), schemas)
    for row in jsonl_read(DATA / "paraphrases.jsonl"):
        if not _LEAK.search(row["text"]):
            add(row["text"], calls_msg(row["calls"]), schemas)
    # Charla: para no olvidar conversar ni llamar herramientas para todo. Son respuestas del
    # propio 7B (a veces con datos mal), así que pocas: lo que se enseña es el formato.
    chat = [
        (r["text"], c) for r in jsonl_read(DATA / "chat.jsonl") if (c := clean_chat(r["reply"]))
    ]
    RNG.shuffle(chat)
    for text, reply in chat[:MAX_CHAT]:
        add(text, {"role": "assistant", "content": reply}, schemas)
    for row in jsonl_read(DATA / "invented.jsonl"):
        extra = {"type": "function", "function": row["tool"]}
        tools = [*schemas, extra]
        RNG.shuffle(tools)
        for _ in range(4):  # pocos ejemplos: se repiten con fechas distintas
            add(row["text"], calls_msg(row["calls"]), tools)
    RNG.shuffle(examples)
    n_valid = max(1, int(len(examples) * valid_share))
    jsonl_write(DATA / "valid.jsonl", examples[:n_valid])
    jsonl_write(DATA / "train.jsonl", examples[n_valid:])
    print(f"{len(examples) - n_valid} para entrenar, {n_valid} para validar")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "etapa", choices=["semillas", "parafrasis", "charla", "inventadas", "juntar"]
    )
    parser.add_argument("--por-semilla", type=int, default=8)
    parser.add_argument("--por-tema", type=int, default=40)
    parser.add_argument("--validar", type=float, default=0.05)
    args = parser.parse_args()
    if args.etapa == "semillas":
        stage_seeds()
    elif args.etapa == "parafrasis":
        asyncio.run(stage_paraphrase(args.por_semilla))
    elif args.etapa == "charla":
        asyncio.run(stage_chat(args.por_tema))
    elif args.etapa == "inventadas":
        stage_invented()
    else:
        stage_build(args.validar)


if __name__ == "__main__":
    main()
