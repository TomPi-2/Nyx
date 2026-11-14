"""Tipos de extensión sin código (tarea 7.03): acciones por app, preajustes, conocimiento y
personalidad (HOJA-DE-RUTA §4.3).

Se leen y se validan contra un esquema; no ejecutan nada. Lo que no valida no se carga (y se
dice por qué). El catálogo de `app_action` es la primera extensión de este tipo
(`builtin/tepnyx.apps`), la prueba de que el formato sirve.

- `actions.json`: atajos de teclado por app. Las teclas pasan por el mismo analizador que usa
  Nyx (`winapi/keys.parse`) y por su lista de bloqueo. Nunca en juegos ni en Nyx: eso lo
  garantiza `app_action` al ejecutar, y aquí no se aceptan ejecutables de Nyx.
- `presets/*.json`: solo los ajustes editables de `PRESET_KEYS` (apariencia, voz y tono):
  nunca niveles de seguridad, políticas del modo partida, privacidad, red ni el cerebro.
- `knowledge/*.md`: textos que Nyx consulta; llegan al modelo marcados como externos.
- `personality.json`: tono base y frases propias para las respuestas fijas.
- `shape/`: una forma de Nyx (GLSL ES 1.00 con los uniforms fijos de
  `docs/extensiones/formas.md`; tarea 7.09). Aquí se valida el texto; compilarla y medirla lo
  hace la interfaz, que vuelve a la forma de siempre si falla.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nyx.ext.manifest import Manifest

if TYPE_CHECKING:
    from nyx.tools.app_catalog import AppProfile

MAX_JSON_BYTES = 256 * 1024
MAX_KNOWLEDGE_FILES = 40
MAX_KNOWLEDGE_BYTES = 64 * 1024
MAX_PRESETS = 20
MAX_SHADER_BYTES = 32 * 1024
# Lo que un shader de forma no puede usar: otra versión de GLSL, extensiones, uniforms o
# texturas propias (solo los de Nyx) y bucles sin límite fijo.
_SHADER_FORBIDDEN = re.compile(
    r"#\s*(?:version|extension|include|pragma)\b|\b(?:uniform|sampler2D|samplerCube|texture2D"
    r"|textureCube|texture|while|do)\b"
)

_ACTION_ID = r"^[a-z][a-z0-9_]{1,40}$"
_PROCESS = re.compile(r"^[a-z0-9][a-z0-9_. -]{0,60}\.exe$")
_NYX_PROCESSES = frozenset({"nyx.exe", "nyx-ui.exe", "nyxsetup.exe"})

#: Lo que un preajuste puede cambiar (ruta dentro de `Settings`). Nada de seguridad.
PRESET_KEYS = frozenset(
    {
        "appearance.indicator_size",
        "appearance.font",
        "appearance.nyx_color",
        "appearance.panel_tint",
        "appearance.glass.quality",
        "appearance.glass.motion",
        "appearance.glass.edge",
        "tts.enabled",
        "tts.voice",
        "tts.speed",
        "responses.speak_typed",
        "responses.tone",
        "listen.followup_s",
        "wake.sensitivity",
        "game.mode",
    }
)


class ContentError(ValueError):
    """Un archivo de una extensión no vale. El mensaje es para personas."""


def _keys_ok(combo: str) -> str:
    from nyx.winapi import keys

    hotkey = keys.parse(combo)  # ValueError si no se entiende
    if (why := keys.blocked_reason(hotkey)) is not None:
        raise ValueError(f"«{combo}»: {why}")
    return combo


Combo = Annotated[str, Field(min_length=1, max_length=40)]
Label = Annotated[str, Field(min_length=1, max_length=60)]


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: Label
    keys: Combo | dict[Literal["*", "es", "en"], Combo]
    background: bool = False

    @field_validator("keys")
    @classmethod
    def _valid_keys(cls, keys: str | dict[str, str]) -> str | dict[str, str]:
        if isinstance(keys, str):
            return _keys_ok(keys)
        if not keys:
            raise ValueError("sin teclas")
        if "*" not in keys and "en" not in keys:
            raise ValueError("hace falta «*» o «en» (para cuando Windows no está en español)")
        return {lang: _keys_ok(combo) for lang, combo in keys.items()}


class AppSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Label
    processes: tuple[str, ...] = Field(min_length=1, max_length=10)
    names: tuple[Annotated[str, Field(min_length=2, max_length=60)], ...] = ()
    actions: dict[Annotated[str, Field(pattern=_ACTION_ID)], ActionSpec] = Field(
        min_length=1, max_length=80
    )

    @field_validator("processes")
    @classmethod
    def _valid_processes(cls, processes: tuple[str, ...]) -> tuple[str, ...]:
        out = tuple(p.lower() for p in processes)
        for p in out:
            if not _PROCESS.match(p):
                raise ValueError(f"«{p}» no es un ejecutable")
            if p in _NYX_PROCESSES:
                raise ValueError("no se pueden poner acciones en Nyx")
        return out


class ActionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    apps: tuple[AppSpec, ...] = Field(min_length=1, max_length=50)

    def profiles(self) -> list[AppProfile]:
        from nyx.index.aliases import normalize
        from nyx.tools.app_catalog import AppAction, AppProfile

        out = []
        for app in self.apps:
            actions = {
                key: AppAction(
                    spec.label,
                    {"*": spec.keys}
                    if isinstance(spec.keys, str)
                    else {str(k): v for k, v in spec.keys.items()},
                    spec.background,
                )
                for key, spec in app.actions.items()
            }
            names = tuple(dict.fromkeys(normalize(n) for n in (app.name, *app.names)))
            out.append(AppProfile(app.name, frozenset(app.processes), actions, names))
        return out


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Label
    description: str = Field(default="", max_length=200)
    settings: dict[str, Any] = Field(min_length=1)

    @field_validator("settings")
    @classmethod
    def _only_editable(cls, settings: dict[str, Any]) -> dict[str, Any]:
        flat = _flatten(settings)
        if bad := sorted(set(flat) - PRESET_KEYS):
            raise ValueError(f"un preajuste no puede cambiar {', '.join(bad)}")
        # Los valores, con las mismas reglas que Ajustes: se valida aplicándolos a unos
        # ajustes por defecto.
        from nyx.settings.model import Settings

        try:
            Settings.model_validate(_merge(Settings().model_dump(mode="json"), settings))
        except ValidationError as e:
            raise ValueError(f"valores no válidos: {e.errors()[0]['msg']}") from e
        return settings


Tone = Literal["cercano", "neutro", "divertido"]


class Personality(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Label
    tone: Tone = "cercano"
    #: Frases propias por clave de respuesta fija (`brain/answers.py`): varias variantes.
    phrases: dict[
        Annotated[str, Field(pattern=_ACTION_ID)],
        tuple[Annotated[str, Field(min_length=1, max_length=200)], ...],
    ] = Field(default_factory=dict, max_length=200)

    @field_validator("phrases")
    @classmethod
    def _plain_text(cls, phrases: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        for key, variants in phrases.items():
            if not variants or len(variants) > 12:
                raise ValueError(f"«{key}»: entre 1 y 12 variantes")
            for text in variants:
                # Texto llano: nada que parezca código, enlaces ni marcas.
                if re.search(r"[<>{}`]|https?://|\[\[", text):
                    raise ValueError(f"«{key}»: solo texto, sin código ni enlaces")
        return phrases


class ShapeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Label
    box: float = Field(default=1.0, ge=0.5, le=1.25)  # caja máxima, en veces el tamaño


@dataclass(frozen=True, slots=True)
class Shape:
    name: str
    box: float
    source: str  # el GLSL, sin el preámbulo que pone Nyx


def check_shader(source: str) -> str:
    """El shader si cumple el contrato; si no, `ContentError` con el motivo."""
    if len(source.encode("utf-8")) > MAX_SHADER_BYTES:
        raise ContentError("shape.glsl: demasiado grande")
    code = re.sub(r"//[^\n]*|/\*.*?\*/", " ", source, flags=re.DOTALL)  # sin comentarios
    if m := _SHADER_FORBIDDEN.search(code):
        raise ContentError(f"shape.glsl: no se puede usar «{m.group(0).strip()}»")
    if not re.search(r"\bvoid\s+main\s*\(", code):
        raise ContentError("shape.glsl: falta main()")
    return source


@dataclass(slots=True)
class ExtContent:
    """Lo que trae una extensión sin código, ya validado."""

    profiles: list[AppProfile] = field(default_factory=list)
    presets: dict[str, Preset] = field(default_factory=dict)
    knowledge: dict[str, str] = field(default_factory=dict)  # título → texto
    personality: Personality | None = None
    shape: Shape | None = None
    problems: list[str] = field(default_factory=list)


def _read_json(path: Path) -> object:
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ContentError(f"{path.name}: demasiado grande")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ContentError(f"{path.name}: no es JSON válido ({e})") from e


def _validate(model: type[BaseModel], data: object, where: str) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise ContentError(f"{where}: {loc + ': ' if loc else ''}{first['msg']}") from e


def knowledge_sections(text: str, prefix: str = "") -> dict[str, str]:
    """{título: texto} de cada apartado `##` (como `nyx.md`)."""
    from nyx.index.aliases import normalize

    out: dict[str, str] = {}
    title, lines = "", list[str]()
    for line in text.splitlines():
        if line.startswith("## "):
            if title:
                out[title] = "\n".join(lines).strip()
            title, lines = normalize(f"{prefix} {line[3:]}".strip()), []
        elif title:
            lines.append(line)
    if title:
        out[title] = "\n".join(lines).strip()
    return {k: v for k, v in out.items() if v}


def load_content(manifest: Manifest, folder: Path) -> ExtContent:
    """Lee lo que el manifiesto dice que trae. Un archivo malo no tumba el resto: se anota en
    `problems` y se sigue (Ajustes lo enseña)."""
    out = ExtContent()

    def attempt(what: str, fn: Any) -> None:
        try:
            fn()
        except (ContentError, OSError) as e:
            out.problems.append(f"{what}: {e}")

    if "actions" in manifest.kinds:

        def actions() -> None:
            spec = _validate(ActionsFile, _read_json(folder / "actions.json"), "actions.json")
            out.profiles = spec.profiles()

        attempt("acciones", actions)
    if "preset" in manifest.kinds:

        def presets() -> None:
            files = sorted((folder / "presets").glob("*.json"))[:MAX_PRESETS]
            for path in files:
                preset = _validate(Preset, _read_json(path), f"presets/{path.name}")
                out.presets[path.stem] = preset

        attempt("preajustes", presets)
    if "knowledge" in manifest.kinds:

        def knowledge() -> None:
            files = sorted((folder / "knowledge").glob("*.md"))
            if len(files) > MAX_KNOWLEDGE_FILES:
                raise ContentError(f"más de {MAX_KNOWLEDGE_FILES} archivos")
            for path in files:
                raw = path.read_bytes()
                if len(raw) > MAX_KNOWLEDGE_BYTES:
                    raise ContentError(f"knowledge/{path.name}: demasiado grande")
                text = raw.decode("utf-8", errors="replace")
                out.knowledge.update(knowledge_sections(text, manifest.name))

        attempt("conocimiento", knowledge)
    if "personality" in manifest.kinds:

        def personality() -> None:
            data = _read_json(folder / "personality.json")
            out.personality = _validate(Personality, data, "personality.json")

        attempt("personalidad", personality)
    if "shape" in manifest.kinds:

        def shape() -> None:
            spec = _validate(ShapeSpec, _read_json(folder / "shape" / "shape.json"), "shape.json")
            raw = (folder / "shape" / "shape.glsl").read_bytes()
            if len(raw) > MAX_SHADER_BYTES:
                raise ContentError("shape.glsl: demasiado grande")
            source = check_shader(raw.decode("utf-8", errors="strict"))
            out.shape = Shape(spec.name, spec.box, source)

        attempt("forma", shape)
    return out


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def _merge(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def builtin_dir() -> Path:
    return Path(__file__).resolve().parent / "builtin"
