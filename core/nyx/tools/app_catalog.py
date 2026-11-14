"""Acciones dentro de las apps: qué atajo pulsar para cada cosa (fase 3c).

Desde la 0.7 (tarea 7.03) los atajos están en JSON, como una extensión más: los de Nyx en
`nyx/ext/builtin/tepnyx.apps/actions.json` y los de las extensiones instaladas se añaden con
`set_extension_profiles`.

Los atajos cambian con el idioma de la app: en el Bloc de notas y en Office en español,
«nuevo» es Ctrl+U y «guardar» Ctrl+G (en inglés, Ctrl+N y Ctrl+S). Por eso cada acción puede
tener variantes por idioma («es», «en»); se elige según el idioma de Windows.

`background=True`: al terminar, el foco vuelve a la ventana en la que estaba el usuario (subir
el volumen de Spotify no debe ponerte Spotify delante).

Nunca se usa dentro de juegos (ver winapi/games.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AppAction:
    label: str  # «Nueva pestaña»
    keys: dict[str, str]  # idioma → atajo; «*» vale para todos
    background: bool = False

    def keys_for(self, language: str) -> str:
        return self.keys.get(language) or self.keys.get("*") or self.keys["en"]


@dataclass(frozen=True, slots=True)
class AppProfile:
    name: str
    processes: frozenset[str]
    actions: dict[str, AppAction] = field(default_factory=dict)
    names: tuple[str, ...] = ()  # cómo se le llama (normalizado): «chrome», «edge»…


def _builtin_profiles() -> tuple[AppProfile, ...]:
    """El catálogo de Nyx, que es una extensión integrada en JSON (7.03:
    `nyx/ext/builtin/tepnyx.apps/actions.json`). Si no valida, es un error de Nyx: que falle."""
    from nyx.ext.content import builtin_dir, load_content
    from nyx.ext.manifest import load_manifest

    folder = builtin_dir() / "tepnyx.apps"
    content = load_content(load_manifest((folder / "manifest.json").read_bytes()), folder)
    if content.problems:
        raise RuntimeError(f"Catálogo de apps no válido: {content.problems}")
    return tuple(content.profiles)


PROFILES: tuple[AppProfile, ...] = _builtin_profiles()
# Las de las extensiones instaladas (7.03/7.04): se añaden y se quitan en caliente.
_EXTRA: list[AppProfile] = []


def set_extension_profiles(profiles: list[AppProfile]) -> None:
    """Sustituye las acciones que vienen de extensiones (las de Nyx van siempre primero)."""
    _EXTRA[:] = profiles


def profiles() -> tuple[AppProfile, ...]:
    return (*PROFILES, *_EXTRA)


def all_actions() -> list[str]:
    return sorted({a for p in profiles() for a in p.actions})


ALL_ACTIONS = all_actions()


def profile_for(process: str | None, name: str | None = None) -> AppProfile | None:
    """El perfil por ejecutable o, si no se sabe (apps de la Store), por nombre."""
    every = profiles()
    if process:
        found = next((p for p in every if process.lower() in p.processes), None)
        if found is not None:
            return found
    if name:
        from nyx.index.aliases import normalize

        wanted = normalize(name)
        return next((p for p in every if wanted in p.names), None)
    return None


def windows_language() -> str:
    """«es», «en»… según el idioma de la interfaz de Windows (los atajos de las apps siguen
    ese idioma)."""
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return "es"
    return {0x0A: "es", 0x09: "en"}.get(langid & 0x3FF, "en")
