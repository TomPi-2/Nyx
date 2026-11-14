"""Juegos de Steam, Riot y Epic (SPEC sección 10). EA, Ubisoft, Battle.net, GOG y Xbox: fase 6.

Cada juego se abre por su lanzador (no con el .exe del juego), que es lo que esperan los
anticheats y lo que mantiene las actualizaciones.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from nyx.index.aliases import generate
from nyx.index.model import Entry, Kind, Launch, LaunchKind

log = logging.getLogger(__name__)

# --- Steam ---

_STEAM_SKIP = re.compile(r"redistributable|steamworks|proton|steam linux runtime|soundtrack", re.I)
_VDF_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict[str, Any]:
    """KeyValues de Valve («clave» «valor» y bloques con llaves)."""
    root: dict[str, Any] = {}
    stack = [root]
    key: str | None = None
    for m in _VDF_TOKEN.finditer(text):
        string, brace = m.group(1), m.group(2)
        if brace == "{":
            child: dict[str, Any] = {}
            stack[-1][key or ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = string.replace("\\\\", "\\")
        else:
            stack[-1][key] = string.replace("\\\\", "\\")
            key = None
    return root


def steam_root() -> Path | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            path = Path(str(winreg.QueryValueEx(k, "SteamPath")[0]))
    except OSError:
        return None
    return path if path.exists() else None


def steam_libraries(root: Path) -> list[Path]:
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        data = parse_vdf(vdf.read_text(encoding="utf-8", errors="replace"))
        for lib in data.get("libraryfolders", {}).values():
            if isinstance(lib, dict) and (p := lib.get("path")):
                libs.append(Path(p))
    unique: dict[str, Path] = {str(p).casefold(): p for p in libs}
    return list(unique.values())


def scan_steam(root: Path | None = None) -> Iterator[Entry]:
    root = root or steam_root()
    if root is None:
        return
    for lib in steam_libraries(root):
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            state = parse_vdf(acf.read_text(encoding="utf-8", errors="replace")).get("AppState", {})
            appid, name = state.get("appid"), state.get("name")
            if not appid or not name or _STEAM_SKIP.search(name):
                continue
            yield Entry(
                key=f"game:steam:{appid}",
                kind=Kind.GAME,
                name=name,
                launch=Launch(LaunchKind.URI, f"steam://rungameid/{appid}"),
                source="steam",
                aliases=generate(name),
            )


# --- Riot ---

# producto → (nombre, ejecutable del juego)
RIOT_PRODUCTS: dict[str, tuple[str, str]] = {
    "valorant": ("VALORANT", "valorant-win64-shipping.exe"),
    "league_of_legends": ("League of Legends", "league of legends.exe"),
    "bacon": ("Legends of Runeterra", "lor.exe"),
    "lion": ("2XKO", "2xko.exe"),
}


def scan_riot(program_data: Path | None = None) -> Iterator[Entry]:
    base = (program_data or Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))) / "Riot Games"
    installs = base / "RiotClientInstalls.json"
    if not installs.exists():
        return
    try:
        client = json.loads(installs.read_text(encoding="utf-8")).get("rc_default")
    except OSError, ValueError:
        return
    if not client:
        return
    metadata = base / "Metadata"
    installed = {p.name for p in metadata.iterdir()} if metadata.exists() else set()
    for product, (name, exe) in RIOT_PRODUCTS.items():
        if f"{product}.live" not in installed:
            continue
        args = (f"--launch-product={product}", "--launch-patchline=live")
        yield Entry(
            key=f"game:riot:{product}",
            kind=Kind.GAME,
            name=name,
            launch=Launch(LaunchKind.EXE, client, args),
            source="riot",
            process=exe,
            aliases=generate(name),
        )
    if "league_of_legends.live" in installed:
        # TFT se abre desde el cliente de League.
        yield Entry(
            key="game:riot:tft",
            kind=Kind.GAME,
            name="Teamfight Tactics",
            launch=Launch(
                LaunchKind.EXE,
                client,
                ("--launch-product=league_of_legends", "--launch-patchline=live"),
            ),
            source="riot",
            process="league of legends.exe",
            aliases=generate("Teamfight Tactics"),
        )


# --- Epic ---


def scan_epic(program_data: Path | None = None) -> Iterator[Entry]:
    base = program_data or Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    manifests = base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifests.exists():
        return
    for item in manifests.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8-sig"))
        except OSError, ValueError:
            continue
        name, app = data.get("DisplayName"), data.get("AppName")
        categories = data.get("AppCategories") or []
        if not name or not app or data.get("bIsIncompleteInstall") or "addons" in categories:
            continue
        main = data.get("MainGameAppName")
        if main and main != app:
            continue  # contenido adicional de otro juego (p. ej. modos de Fortnite)
        ids = f"{data.get('CatalogNamespace')}:{data.get('CatalogItemId')}:{app}"
        exe = Path(str(data.get("LaunchExecutable") or "")).name.lower() or None
        yield Entry(
            key=f"game:epic:{app}",
            kind=Kind.GAME,
            name=name,
            launch=Launch(
                LaunchKind.URI, f"com.epicgames.launcher://apps/{ids}?action=launch&silent=true"
            ),
            source="epic",
            process=exe,
            aliases=generate(name),
        )


def scan() -> list[Entry]:
    entries: list[Entry] = []
    for scanner in (scan_steam, scan_riot, scan_epic):
        try:
            entries += list(scanner())
        except Exception:
            log.warning("Fallo al escanear juegos (%s)", scanner.__name__, exc_info=True)
    return entries
