"""Guion para grabar la voz propia de Nyx (decisión del usuario, 2026-11-15).

    uv run python training/voz/guion.py            # → tools/grabadora/src/guion.json

Une cuatro fuentes y las reparte en sesiones de unas 150 frases (unos 40 minutos con
repeticiones), mezcladas: desde la primera sesión hay de todo, así que con la primera hora ya
se pueden probar modelos de voz.

1. **Lo que Nyx dice de verdad**: frases fijas con variantes (`brain/phrases.py`), respuestas
   con datos de ejemplo (`brain/answers.py`), agradecimientos y el primer arranque guiado.
2. **Frases de asistente** escritas para esto (`frases_nyx.txt`): saludos, confirmaciones,
   disculpas, nombres de apps y juegos.
3. **Números, horas y fechas**, ya en letra (lo que se lee tiene que coincidir con el texto).
4. **Frases variadas de Common Voice** (CC0, `fuentes/commonvoice-es.txt`, se baja con
   `curl` desde el repositorio de Mozilla; no va en git): se escogen las que más sonidos
   nuevos del español aportan, para cubrirlos todos.

Cada frase lleva un tono para leerla: natural, cercana, alegre, pregunta o tranquila.
"""

from __future__ import annotations

import itertools
import json
import random
import re
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CORE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CORE))

HERE = Path(__file__).resolve().parent
OUT = CORE.parent / "tools" / "grabadora" / "src" / "guion.json"
CV = HERE / "fuentes" / "commonvoice-es.txt"
OWN = HERE / "frases_nyx.txt"
#: Palabras en otros idiomas (2026-11-18): sesiones aparte, al final, sin tocar las demás.
LANGS = HERE / "frases_idiomas.txt"

PER_SESSION = 150
#: Cuántas frases de Common Voice: con las demás, unas 2.900 (3–4 horas grabadas).
CV_TARGET = 2200
SEED = 7


@dataclass(frozen=True)
class Line:
    id: str
    sesion: int
    texto: str
    tono: str
    fuente: str
    #: Idioma de lo que va entre comillas (es: todo en español) y cómo se pronuncia (no se lee).
    idioma: str = "es"
    pista: str = ""


# --- Números en letra ---------------------------------------------------------------------

_UNITS = [
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]
_TENS = [
    "_",
    "_",
    "_",
    "treinta",
    "cuarenta",
    "cincuenta",
    "sesenta",
    "setenta",
    "ochenta",
    "noventa",
]
_HUNDREDS = [
    "_",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
]


def words(n: int) -> str:
    """Número entero en letra (0 – 999.999), como se dice: «veintidós», «ciento cinco»."""
    if n < 0:
        return "menos " + words(-n)
    if n < 30:
        return _UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return _TENS[tens] + (f" y {_UNITS[unit]}" if unit else "")
    if n == 100:
        return "cien"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return _HUNDREDS[hundreds] + (f" {words(rest)}" if rest else "")
    thousands, rest = divmod(n, 1000)
    head = "mil" if thousands == 1 else f"{words(thousands)} mil"
    return head + (f" {words(rest)}" if rest else "")


def spell_numbers(text: str) -> str:
    """Pasa a letra lo que se lee: «45 %» → «cuarenta y cinco por ciento», «3,5» → «tres coma
    cinco»."""
    text = re.sub(r"(\d+),(\d+)", lambda m: f"{words(int(m[1]))} coma {words(int(m[2]))}", text)
    text = re.sub(r"(\d+)\s*%", lambda m: f"{words(int(m[1]))} por ciento", text)
    text = re.sub(r"(\d+)\s*º", lambda m: f"{words(int(m[1]))} grados", text)
    text = re.sub(r"\d+", lambda m: words(int(m[0])), text)
    return text.replace("uno por ciento", "un uno por ciento").replace("  ", " ")


# --- Tono ----------------------------------------------------------------------------------


def tone_of(text: str, default: str) -> str:
    if text.rstrip().endswith("?"):
        return "pregunta"
    if "¡" in text or text.rstrip().endswith("!"):
        return "alegre"
    return default


def tidy(text: str) -> str:
    """Espacios y mayúscula inicial («¿ vale?» → «¿vale?»)."""
    text = " ".join(text.split())
    text = re.sub(r"([¿¡])\s+", r"\1", text)
    text = re.sub(r"\s+([?!.,;:])", r"\1", text)
    first = next((i for i, c in enumerate(text) if c.isalpha()), None)
    if first is not None:
        text = text[:first] + text[first].upper() + text[first + 1 :]
    if text and text[-1].isalnum():
        text += "."
    return text


# --- 1. Lo que Nyx dice de verdad ------------------------------------------------------------

#: Datos de ejemplo para las respuestas con datos (se prueban varias combinaciones).
_SAMPLES: tuple[dict[str, Any], ...] = (
    {"percent": 45, "plugged": False, "minutes_left": 125, "secs_left": 7500},
    {"percent": 82, "plugged": True, "power_plugged": True},
    {"percent": 12, "usage": 12, "cores": 8, "used": "11,2 GB", "total": "32 GB"},
    {"percent": 67, "usage": 67, "used": "21 GB", "total": "32 GB", "free": "11 GB",
     "drive": "C:", "free_formatted": "312 GB", "total_formatted": "1 TB"},
    {"title": "Bohemian Rhapsody", "artist": "Queen", "app": "Spotify", "playing": True},
    {"title": "Clair de lune", "artist": "", "app": "Spotify", "playing": False},
    {"elapsed_s": 754, "elapsed": "12 minutos y 34 segundos", "running": True},
    {"cpu_name": "Chrome", "cpu_pct": 23, "ram_name": "Chrome", "ram": "2,1 GB"},
    {"cpu_name": "Steam", "cpu_pct": 41, "ram_name": "Discord", "ram": "900 MB"},
)  # fmt: skip


def nyx_lines() -> list[tuple[str, str]]:
    from nyx.brain.answers import ANSWERS, THANKS_REPLIES
    from nyx.brain.phrases import PHRASES
    from nyx.setup import flow

    out: list[tuple[str, str]] = []
    for group in PHRASES.values():
        for p in group:
            out.append((p.spoken or p.display, "cercana"))
    for variants in ANSWERS.values():
        for tone_variants in variants.values():
            for make in tone_variants:
                for data in _SAMPLES:
                    try:
                        out.append((make(data), "cercana"))
                    except KeyError, TypeError, ValueError, IndexError:
                        continue
    for replies in THANKS_REPLIES.values():
        out.extend((r, "alegre") for r in replies)
    for said in flow.SAY.values():
        out.extend((s, "cercana") for s in said)
    out.extend((s, "alegre") for s in flow.COLOR_SAYS.values())
    out.extend((s, "cercana") for s in flow.TINT_SAYS.values())
    out.extend((s, "tranquila") for s in flow.NOT_UNDERSTOOD)
    out.extend((flow.size_says(size), "cercana") for size in (60, 90, 100, 120, 160))
    return out


# --- 3. Números, horas y fechas --------------------------------------------------------------

_MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def number_lines(rng: random.Random) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def hour(h: int, m: int) -> str:
        la = "la" if h in (1, 13) else "las"
        hh = words(h if h <= 12 else h - 12)
        if hh == "uno":
            hh = "una"
        if m == 0:
            return f"{la} {hh} en punto"
        if m == 15:
            return f"{la} {hh} y cuarto"
        if m == 30:
            return f"{la} {hh} y media"
        return f"{la} {hh} y {words(m)}"

    for _ in range(35):
        h, m = rng.randrange(1, 24), rng.choice((0, 5, 10, 15, 20, 25, 30, 40, 45, 50, 55, 7, 13))
        out.append((rng.choice((
            f"Son {hour(h, m)}.",
            f"Te aviso a {hour(h, m)}.",
            f"Alarma puesta para {hour(h, m)}.",
            f"Tu alarma de {hour(h, m)} ya está sonando.",
        )), "natural"))  # fmt: skip
    for _ in range(25):
        d, mo, wd = rng.randrange(1, 29), rng.choice(_MONTHS), rng.choice(_DAYS)
        out.append((rng.choice((
            f"Hoy es {wd}, {words(d)} de {mo}.",
            f"Mañana es {wd}, {words(d)} de {mo}.",
            f"Lo tienes apuntado para el {words(d)} de {mo}.",
        )), "natural"))  # fmt: skip
    for _ in range(30):
        t, lo = rng.randrange(-3, 39), rng.randrange(-6, 25)
        out.append((rng.choice((
            f"Ahora mismo hace {words(t)} grados y está despejado.",
            f"Mañana, máxima de {words(max(t, lo))} grados y mínima de {words(min(t, lo))}.",
            f"Hay un {words(rng.randrange(5, 95))} por ciento de probabilidad de lluvia.",
            f"Ahora mismo, {words(t)} grados con algunas nubes.",
        )), "natural"))  # fmt: skip
    for _ in range(25):
        n = rng.choice(
            (rng.randrange(1, 100), rng.randrange(100, 1000), rng.randrange(1000, 99999))
        )
        out.append((rng.choice((
            f"Hay {words(n)} archivos en Descargas.",
            f"Te queda un {words(rng.randrange(1, 100))} por ciento de batería.",
            f"El resultado es {words(n)}.",
            f"Llevas {words(rng.randrange(1, 60))} minutos con el cronómetro.",
            f"Tienes {words(rng.randrange(2, 500))} gigas libres en el disco.",
        )), "natural"))  # fmt: skip
    return out


# --- 4. Common Voice: las que más sonidos aportan ---------------------------------------------

#: Grafemas que suenan como un solo sonido (aproximación a los fonemas del español).
_DIGRAPHS = ("ch", "ll", "rr", "qu", "gu", "gü")


def sounds(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text.lower())
    t = re.sub(r"[^a-záéíóúüñ ]", " ", t)
    out: list[str] = []
    for word in t.split():
        i = 0
        while i < len(word):
            pair = word[i : i + 2]
            if pair in _DIGRAPHS:
                out.append(pair)
                i += 2
            else:
                out.append(word[i])
                i += 1
        out.append(" ")
    return out


def units(text: str) -> set[str]:
    """Pares de sonidos seguidos (dífonos aproximados): lo que hay que cubrir."""
    s = sounds(text)
    return {a + b for a, b in itertools.pairwise(s)}


#: Español de libro antiguo, que Nyx nunca dirá: «hubieron comido», «volvióse», «ó» con tilde.
_ARCHAIC = re.compile(
    r"\bhub(?:e|iste|o|imos|isteis|ieron)\b\s+\w+(?:ado|ido)\b"
    r"|\b\w+(?:óse|ióse|ábase|íase|áronse|iéronse|óle|iósele)\b|\bó\b|\bá\b",
    re.I,
)


def good_cv(line: str) -> str | None:
    line = tidy(line)
    n = len(line.split())
    if not 5 <= n <= 18 or any(c.isdigit() for c in line):
        return None
    if re.search(r"[\"()\[\]{}<>/\\|_*#@&]|\.\.|[A-Z]{2,}", line):
        return None
    if line[-1] in ":;,—-" or _ARCHAIC.search(line):
        return None
    capitals = sum(1 for w in line.split()[1:] if w[:1].isupper())
    return None if capitals > 1 else line


def pick_cv(lines: Iterable[str], target: int) -> list[str]:
    pool = list(dict.fromkeys(filter(None, (good_cv(x) for x in lines))))
    covered: dict[str, int] = {}
    chosen: list[str] = []
    candidates = [(line, units(line)) for line in pool]
    while candidates and len(chosen) < target:
        # Lo nuevo que aporta cada frase, por palabra (no premiar las largas sin más).
        def gain(item: tuple[str, set[str]]) -> float:
            line, u = item
            return sum(1 / (1 + covered.get(x, 0)) for x in u) / (len(line.split()) ** 0.5)

        best = max(candidates, key=gain)
        candidates.remove(best)
        chosen.append(best[0])
        for x in best[1]:
            covered[x] = covered.get(x, 0) + 1
    return chosen


# --- Montaje -----------------------------------------------------------------------------------


def build() -> list[Line]:
    rng = random.Random(SEED)
    sources: dict[str, list[tuple[str, str]]] = {
        "nyx": [],
        "asistente": [],
        "numeros": [],
        "cv": [],
    }

    def add(source: str, items: Iterable[tuple[str, str]]) -> None:
        for text, tone in items:
            clean = tidy(spell_numbers(text))
            if clean:
                sources[source].append((clean, tone_of(clean, tone)))

    add("nyx", nyx_lines())
    own = [x.strip() for x in OWN.read_text(encoding="utf-8").splitlines()]
    add("asistente", ((x, "cercana") for x in own if x and not x.startswith("#")))
    add("numeros", number_lines(rng))
    if CV.exists():
        add(
            "cv",
            (
                (x, "natural")
                for x in pick_cv(CV.read_text(encoding="utf-8").splitlines(), CV_TARGET)
            ),
        )
    else:
        print(f"Aviso: falta {CV} (curl desde Common Voice): el guion va sin frases variadas")

    # Sin repetir la misma frase de dos fuentes.
    seen: set[str] = set()
    for key in sources:
        unique = []
        for text, tone in sources[key]:
            k = text.lower()
            if k not in seen:
                seen.add(k)
                unique.append((text, tone))
        rng.shuffle(unique)
        sources[key] = unique

    # Reparto: cada sesión con su parte de cada fuente.
    total = sum(len(v) for v in sources.values())
    sessions = max(1, round(total / PER_SESSION))
    buckets: list[list[tuple[str, str, str]]] = [[] for _ in range(sessions)]
    for key, items in sources.items():
        for i, (text, tone) in enumerate(items):
            buckets[i % sessions].append((text, tone, key))
    lines: list[Line] = []
    for s, bucket in enumerate(buckets, start=1):
        rng.shuffle(bucket)
        for i, (text, tone, key) in enumerate(bucket, start=1):
            lines.append(Line(f"s{s:02d}-{i:03d}", s, text, tone, key))
    return lines + language_lines(len(buckets))


def language_lines(after: int) -> list[Line]:
    """Las frases de otros idiomas, en sesiones nuevas tras la `after` (los ids de las demás no
    cambian). Con su idioma y una pista de pronunciación para quien graba."""
    if not LANGS.exists():
        return []
    items: list[tuple[str, str, str]] = []
    for raw in LANGS.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        lang, text, hint = (part.strip() for part in raw.split("|", 2))
        items.append((lang, text, hint))
    random.Random(SEED + 1).shuffle(items)
    out: list[Line] = []
    for n, (lang, text, hint) in enumerate(items):
        session = after + 1 + n // PER_SESSION
        index = n % PER_SESSION + 1
        tone = "pregunta" if text.endswith("?»") or text.endswith("?") else "cercana"
        out.append(Line(f"s{session:02d}-{index:03d}", session, text, tone, "idiomas", lang, hint))
    return out


def main() -> None:
    lines = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps([asdict(x) for x in lines], ensure_ascii=False, indent=0) + "\n",
        encoding="utf-8",
    )
    by: dict[str, int] = {}
    for x in lines:
        by[x.fuente] = by.get(x.fuente, 0) + 1
    sessions = max(x.sesion for x in lines)
    print(f"{len(lines)} frases en {sessions} sesiones: {OUT}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in by.items()))


if __name__ == "__main__":
    main()
