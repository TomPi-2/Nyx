"""Alias automáticos: cómo puede llamar el usuario (o transcribir whisper) a cada cosa."""

from __future__ import annotations

import re
import unicodedata

# Palabras que sobran en el nombre de un programa.
_NOISE = re.compile(
    r"\b(?:microsoft|google|inc|corporation|launcher|x64|x86|64-bit|32-bit|\(64-bit\)|"
    r"desktop|app|beta|ptb|preview)\b",
    re.IGNORECASE,
)
_VERSION = re.compile(r"\b(?:v?\d+(?:\.\d+)+|\d{4})\b")
_TRADEMARKS = re.compile(r"[®™©]")
_ARTICLES = re.compile(r"^(?:el|la|los|las|un|una|mi|mis|tu|tus)\s+")

# Nombres que la gente (o whisper) dice de otra forma. Clave: nombre normalizado.
KNOWN: dict[str, tuple[str, ...]] = {
    "visual studio code": ("vscode", "vs code", "code", "visual code", "visual estudio code"),
    "google chrome": ("chrome", "crom", "navegador chrome"),
    "microsoft edge": ("edge", "ech"),
    "bloc de notas": (
        "notepad",
        "notas",
        "block de notas",
        "blog de notas",
        "el blog de notas",
        "el bloc de notas",
    ),
    "opera gx": ("operaje x", "opera g x", "operagx"),
    "explorador de archivos": ("explorador", "archivos", "explorer"),
    "calculadora": ("calculator", "la calculadora"),
    "administrador de tareas": ("task manager", "tareas"),
    "simbolo del sistema": ("cmd", "consola", "terminal antigua"),
    "terminal": ("windows terminal", "powershell", "la terminal"),
    "valorant": ("valo", "balorant", "valoran"),
    "league of legends": ("lol", "league", "el lol", "liga de leyendas"),
    "teamfight tactics": ("tft",),
    "counter-strike 2": ("cs2", "counter", "counter strike", "cs"),
    "rocket league": ("rocket",),
    "discord": ("discor", "discort"),
    "spotify": ("spoti", "espotify", "spotifai"),
    "steam": ("estim", "stim"),
    "configuracion": ("ajustes", "settings"),
    "microsoft store": ("tienda", "store", "la tienda"),
    "obs studio": ("obs",),
    "whatsapp": ("guasap", "wasap", "whats"),
}


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin símbolos y con los espacios justos."""
    text = _TRADEMARKS.sub("", text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s+-]", " ", text.lower())
    text = text.replace("_", " ")
    return " ".join(text.split())


def strip_articles(text: str) -> str:
    return _ARTICLES.sub("", text)


def acronym(words: list[str]) -> str | None:
    initials = "".join(w[0] for w in words if w and w[0].isalpha())
    return initials if len(initials) >= 2 else None


def generate(name: str, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Alias normalizados de `name` (el propio nombre siempre es el primero)."""
    base = normalize(name)
    out: list[str] = [base]
    clean = " ".join(_VERSION.sub(" ", _NOISE.sub(" ", base)).split())
    if clean and clean != base:
        out.append(clean)
    for candidate in (base, clean):
        words = candidate.split()
        if len(words) >= 3 and (acr := acronym(words)):
            out.append(acr)
        out += KNOWN.get(candidate, ())
    out += (normalize(e) for e in extra)
    seen: set[str] = set()
    unique = []
    for alias in out:
        if alias and alias not in seen:
            seen.add(alias)
            unique.append(alias)
    return tuple(unique)
