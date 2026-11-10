"""Búsqueda de archivos (SPEC sección 10): Everything si está instalado; si no, el índice de
búsqueda de Windows (viene con el sistema); y, como último recurso, recorrer las carpetas
del usuario con un tiempo máximo.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote

log = logging.getLogger(__name__)

LIMIT = 20
WALK_BUDGET_S = 2.0
_STOP = "el la los las un una de del en y o con para por mi mis que al"
_STOPWORDS = frozenset(_STOP.split(" "))
_SKIP_DIRS = frozenset({"appdata", "node_modules", ".git", "__pycache__", ".venv", "venv"})


def terms(query: str) -> list[str]:
    """Palabras que deben aparecer en el nombre («la factura de la luz» → factura, luz)."""
    words = re.findall(r"[\w.-]+", query.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2] or words


def _like(term: str) -> str:
    escaped = term.replace("'", "''").replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    return f"System.FileName LIKE '%{escaped}%'"


def _scope(path: Path) -> str:
    return "file:" + str(path).replace("\\", "/").replace("'", "''")


def windows_search(query: str, roots: Iterable[Path], limit: int = LIMIT) -> list[Path]:
    """Índice de Windows por OLE DB (Search.CollatorDSO). Lanza OSError si no responde."""
    import pythoncom
    import win32com.client

    words = terms(query)
    scopes = " OR ".join(f"SCOPE='{_scope(r)}'" for r in roots)
    where = " AND ".join(_like(w) for w in words)
    sql = (
        f"SELECT TOP {limit} System.ItemUrl FROM SYSTEMINDEX "
        f"WHERE ({scopes}) AND {where} ORDER BY System.DateModified DESC"
    )
    pythoncom.CoInitialize()
    try:
        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open(sql, conn)
        found: list[Path] = []
        while not rs.EOF:
            url = str(rs.Fields.Item("System.ItemUrl").Value)
            if url.lower().startswith("file:"):
                found.append(Path(unquote(url[5:].lstrip("/"))))
            rs.MoveNext()
        return found
    except Exception as e:
        raise OSError(f"el índice de Windows no responde: {e}") from e
    finally:
        pythoncom.CoUninitialize()


def everything_exe() -> str | None:
    """es.exe (línea de órdenes de Everything): en el PATH, donde lo deja winget o junto a
    Everything. (Instalado con winget mientras Nyx funciona, el PATH de Nyx aún no lo tiene.)"""
    if exe := shutil.which("es.exe"):
        return exe
    local = os.environ.get("LOCALAPPDATA")
    if local and (winget := Path(local) / "Microsoft" / "WinGet" / "Links" / "es.exe").exists():
        return str(winget)
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
        if base and (candidate := Path(base) / "Everything" / "es.exe").exists():
            return str(candidate)
    return None


def everything_search(query: str, limit: int = LIMIT) -> list[Path]:
    exe = everything_exe()
    if exe is None:
        raise OSError("Everything no está instalado")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    done = subprocess.run(
        [exe, "-n", str(limit), "-sort", "date-modified-descending", *terms(query)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        creationflags=flags,
    )
    if done.returncode != 0:
        raise OSError(f"Everything: código {done.returncode}")
    return [Path(line) for line in done.stdout.splitlines() if line.strip()]


def walk_search(query: str, roots: Iterable[Path], limit: int = LIMIT) -> list[Path]:
    """Último recurso: recorrer las carpetas con un tiempo máximo."""
    words = terms(query)
    deadline = time.monotonic() + WALK_BUDGET_S
    found: list[Path] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".")
            ]
            for name in filenames:
                low = name.lower()
                if all(w in low for w in words):
                    found.append(Path(dirpath) / name)
                    if len(found) >= limit:
                        return found
            if time.monotonic() > deadline:
                return found
    return found


def useful(path: Path) -> bool:
    """Fuera lo que no busca una persona: dependencias, cachés, carpetas ocultas."""
    return not any(part.lower() in _SKIP_DIRS or part.startswith(".") for part in path.parts[1:])


def search(query: str, roots: list[Path], limit: int = LIMIT) -> tuple[list[Path], str]:
    """(resultados, motor usado). Everything → índice de Windows → recorrido."""
    found: list[Path]
    try:
        found, how = everything_search(query, limit * 3), "everything"
    except (OSError, subprocess.SubprocessError):
        try:
            found, how = windows_search(query, roots, limit * 3), "windows"
        except OSError:
            log.info("Índice de Windows no disponible: busco recorriendo carpetas", exc_info=True)
            found, how = walk_search(query, roots, limit * 3), "walk"
    return [p for p in found if useful(p)][:limit], how
