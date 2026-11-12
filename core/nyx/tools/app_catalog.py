"""Acciones dentro de las apps: qué atajo pulsar para cada cosa (fase 3c).

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


def _a(label: str, keys: str | dict[str, str], *, background: bool = False) -> AppAction:
    return AppAction(label, {"*": keys} if isinstance(keys, str) else keys, background)


@dataclass(frozen=True, slots=True)
class AppProfile:
    name: str
    processes: frozenset[str]
    actions: dict[str, AppAction] = field(default_factory=dict)
    names: tuple[str, ...] = ()  # cómo se le llama (normalizado): «chrome», «edge»…


_BROWSER = {
    "new_tab": _a("Nueva pestaña", "ctrl+t"),
    "close_tab": _a("Cerrar pestaña", "ctrl+w"),
    "reopen_tab": _a("Reabrir pestaña cerrada", "ctrl+shift+t"),
    "next_tab": _a("Pestaña siguiente", "ctrl+tab"),
    "previous_tab": _a("Pestaña anterior", "ctrl+shift+tab"),
    "new_window": _a("Nueva ventana", "ctrl+n"),
    "incognito": _a("Ventana de incógnito", "ctrl+shift+n"),
    "back": _a("Atrás", "alt+left"),
    "forward": _a("Adelante", "alt+right"),
    "reload": _a("Recargar", "f5"),
    "history": _a("Historial", "ctrl+h"),
    "downloads": _a("Descargas", "ctrl+j"),
    "bookmark": _a("Guardar en marcadores", "ctrl+d"),
    "find": _a("Buscar en la página", "ctrl+f"),
    "zoom_in": _a("Ampliar", "ctrl+plus"),
    "zoom_out": _a("Reducir", "ctrl+minus"),
    "zoom_reset": _a("Zoom normal", "ctrl+0"),
    "fullscreen": _a("Pantalla completa", "f11"),
}

PROFILES: tuple[AppProfile, ...] = (
    AppProfile(
        "Bloc de notas",
        frozenset({"notepad.exe"}),
        {
            "new_tab": _a("Nueva nota", {"es": "ctrl+u", "en": "ctrl+n"}),
            "close_tab": _a("Cerrar nota", "ctrl+w"),
            "save": _a("Guardar", {"es": "ctrl+g", "en": "ctrl+s"}),
            "save_as": _a("Guardar como", {"es": "ctrl+shift+g", "en": "ctrl+shift+s"}),
            "find": _a("Buscar", {"es": "ctrl+b", "en": "ctrl+f"}),
            "print": _a("Imprimir", "ctrl+p"),
            "zoom_in": _a("Ampliar", "ctrl+plus"),
            "zoom_out": _a("Reducir", "ctrl+minus"),
        },
        names=("bloc de notas", "notepad"),
    ),
    AppProfile(
        "Navegador",
        frozenset(
            {"chrome.exe", "msedge.exe", "opera.exe", "brave.exe", "vivaldi.exe", "opera_gx.exe"}
        ),
        _BROWSER,
        names=(
            "google chrome",
            "chrome",
            "microsoft edge",
            "edge",
            "opera",
            "opera gx",
            "operaje x",
            "opera g x",
            "operagx",
            "brave",
            "vivaldi",
            "navegador",
        ),
    ),
    AppProfile(
        "Firefox",
        frozenset({"firefox.exe"}),
        {**_BROWSER, "incognito": _a("Ventana privada", "ctrl+shift+p")},
        names=("firefox", "mozilla firefox"),
    ),
    AppProfile(
        "Spotify",
        frozenset({"spotify.exe"}),
        {
            "volume_up": _a("Subir volumen", "ctrl+up", background=True),
            "volume_down": _a("Bajar volumen", "ctrl+down", background=True),
            "shuffle": _a("Aleatorio", "ctrl+s", background=True),
            "repeat": _a("Repetir", "ctrl+r", background=True),
            "like": _a("Me gusta", "alt+shift+b", background=True),
            "search": _a("Buscar", "ctrl+k"),
        },
        names=("spotify",),
    ),
    AppProfile(
        "Discord",
        frozenset({"discord.exe", "discordptb.exe", "discordcanary.exe"}),
        {
            "toggle_mute": _a("Micrófono", "ctrl+shift+m", background=True),
            "toggle_deafen": _a("Ensordecer", "ctrl+shift+d", background=True),
            "quick_switcher": _a("Buscar canal o persona", "ctrl+k"),
            "search": _a("Buscar mensajes", "ctrl+f"),
            "answer_call": _a("Contestar llamada", "ctrl+enter"),
            "mark_read": _a("Marcar como leído", "esc", background=True),
        },
        names=("discord", "discord ptb", "discord canary"),
    ),
    AppProfile(
        "Explorador de archivos",
        frozenset({"explorer.exe"}),
        {
            "new_tab": _a("Nueva pestaña", "ctrl+t"),
            "close_tab": _a("Cerrar pestaña", "ctrl+w"),
            "new_window": _a("Nueva ventana", "ctrl+n"),
            "back": _a("Atrás", "alt+left"),
            "forward": _a("Adelante", "alt+right"),
            "up": _a("Carpeta superior", "alt+up"),
            "reload": _a("Actualizar", "f5"),
            "search": _a("Buscar", "ctrl+e"),
        },
        names=("explorador de archivos", "explorador"),
    ),
    AppProfile(
        "Visual Studio Code",
        frozenset({"code.exe"}),
        {
            "command_palette": _a("Paleta de comandos", "ctrl+shift+p"),
            "quick_open": _a("Abrir archivo", "ctrl+p"),
            "new_tab": _a("Archivo nuevo", "ctrl+n"),
            "close_tab": _a("Cerrar pestaña", "ctrl+w"),
            "save": _a("Guardar", "ctrl+s"),
            "toggle_sidebar": _a("Barra lateral", "ctrl+b"),
            "find": _a("Buscar", "ctrl+f"),
        },
        names=("visual studio code", "vscode", "vs code"),
    ),
    AppProfile(
        "Word",
        frozenset({"winword.exe"}),
        {
            "new_tab": _a("Documento nuevo", {"es": "ctrl+u", "en": "ctrl+n"}),
            "save": _a("Guardar", {"es": "ctrl+g", "en": "ctrl+s"}),
            "print": _a("Imprimir", "ctrl+p"),
            "find": _a("Buscar", {"es": "ctrl+b", "en": "ctrl+f"}),
        },
        names=("word", "microsoft word"),
    ),
    AppProfile(
        "Excel",
        frozenset({"excel.exe"}),
        {
            "new_tab": _a("Libro nuevo", {"es": "ctrl+u", "en": "ctrl+n"}),
            "save": _a("Guardar", {"es": "ctrl+g", "en": "ctrl+s"}),
            "print": _a("Imprimir", "ctrl+p"),
            "find": _a("Buscar", {"es": "ctrl+b", "en": "ctrl+f"}),
        },
        names=("excel", "microsoft excel"),
    ),
)

ALL_ACTIONS = sorted({a for p in PROFILES for a in p.actions})


def profile_for(process: str | None, name: str | None = None) -> AppProfile | None:
    """El perfil por ejecutable o, si no se sabe (apps de la Store), por nombre."""
    if process:
        found = next((p for p in PROFILES if process.lower() in p.processes), None)
        if found is not None:
            return found
    if name:
        from nyx.index.aliases import normalize

        wanted = normalize(name)
        return next((p for p in PROFILES if wanted in p.names), None)
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
