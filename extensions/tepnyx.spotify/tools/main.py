# SPDX-License-Identifier: MIT
"""Spotify con la voz (extensión oficial de Tepnyx; tarea 7.14).

Desde febrero de 2026 Spotify no deja una app común para todos los usuarios (5 por app y su
dueño con Premium), así que cada uno conecta **su propia app** de Spotify (gratis, en
developer.spotify.com; la guía está en knowledge/spotify.md y en Ajustes). Con ella, Nyx busca
y pone lo que se pida con la Web API (poner música exige Premium).

Sin conectar, «pon X en Spotify» abre la búsqueda en la app de Spotify y Nyx explica cómo
conectarla. Pausar, seguir y pasar de canción ya los hace Nyx sin esta extensión (con los
controles multimedia de Windows).

Inicio de sesión: OAuth 2 con PKCE que hace Nyx (`oauth.authorize`): la extensión no ve la
contraseña. El token de refresco se guarda en el Administrador de credenciales (`secrets`).
"""

from __future__ import annotations

import asyncio
import json
import time
import unicodedata
from typing import Any
from urllib.parse import quote, urlencode

import nyx

API = "https://api.spotify.com/v1"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = (
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "user-library-modify playlist-read-private"
)

NO_CLIENT = (
    "Para que ponga yo la música, Spotify pide que conectes una app tuya (es gratis, pero "
    "hace falta Premium): dime «¿cómo conecto Spotify?» y te guío."
)
NOT_CONNECTED = "Aún no has conectado tu cuenta de Spotify: dime «conecta Spotify»."
EXPIRED = "Spotify ha cerrado la sesión (lo hace cada seis meses): dime «conecta Spotify»."
PREMIUM = "Spotify solo deja que otra app ponga la música si tienes Premium."
NO_DEVICE = "No encuentro Spotify abierto en ningún sitio: ábrelo y vuelve a pedírmelo."

KINDS = {"cancion": "track", "artista": "artist", "disco": "album", "lista": "playlist"}

_access: dict[str, Any] = {"token": None, "until": 0.0}
_login: asyncio.Task[None] | None = None


# --- Sesión -------------------------------------------------------------------------------------


async def client_id() -> str | None:
    value = await nyx.ask("settings.get", {"key": "client_id"})
    return str(value).strip() if value else None


async def _store(tokens: dict[str, Any]) -> None:
    _access["token"] = tokens["access_token"]
    _access["until"] = time.monotonic() + float(tokens.get("expires_in", 3600))
    if tokens.get("refresh_token"):  # Spotify puede darlo nuevo: siempre el último
        await nyx.ask("secrets.set", {"key": "refresh_token", "value": tokens["refresh_token"]})


async def token() -> str:
    if _access["token"] and time.monotonic() < _access["until"] - 60:
        return str(_access["token"])
    app = await client_id()
    if not app:
        raise nyx.Error(NO_CLIENT)
    refresh = await nyx.ask("secrets.get", {"key": "refresh_token"})
    if not refresh:
        raise nyx.Error(NOT_CONNECTED)
    form = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": app}
    resp = await nyx.ask(
        "net.fetch",
        {
            "url": TOKEN_URL,
            "method": "POST",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": urlencode(form),
        },
    )
    if resp["status"] == 400 and "invalid_grant" in resp["body"]:
        await nyx.ask("secrets.delete", {"key": "refresh_token"})
        raise nyx.Error(EXPIRED)
    if resp["status"] != 200:
        raise nyx.Error("Spotify no contesta bien ahora mismo: prueba en un momento.")
    await _store(json.loads(resp["body"]))
    return str(_access["token"])


async def connected() -> bool:
    if not await client_id():
        return False
    return bool(_access["token"] or await nyx.ask("secrets.get", {"key": "refresh_token"}))


async def api(
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    body: Any = None,
    *,
    retry: bool = True,
) -> tuple[int, Any]:
    """Una llamada a la Web API. Devuelve (estado, JSON o None)."""
    url = API + path + (f"?{urlencode(query)}" if query else "")
    headers = {"Authorization": f"Bearer {await token()}"}
    payload: str | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body)
    elif method in ("PUT", "POST"):
        payload = ""  # Spotify quiere Content-Length aunque no haya nada
    resp = await nyx.ask(
        "net.fetch", {"url": url, "method": method, "headers": headers, "body": payload}
    )
    status = int(resp["status"])
    if status == 401 and retry:  # el token ha caducado antes de tiempo
        _access["token"] = None
        return await api(method, path, query, body, retry=False)
    try:
        data = json.loads(resp["body"]) if resp["body"] else None
    except ValueError:
        data = None
    if status == 429:
        raise nyx.Error("Spotify pide que vayamos más despacio: prueba en un momento.")
    if status == 403:
        reason = ((data or {}).get("error") or {}).get("reason", "")
        raise nyx.Error(
            PREMIUM
            if reason == "PREMIUM_REQUIRED" or "premium" in str(data).lower()
            else "Spotify no me deja hacerlo."
        )
    return status, data


# --- Buscar -------------------------------------------------------------------------------------


def norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in plain).split())


def label(item: dict[str, Any]) -> str:
    artists = ", ".join(a["name"] for a in item.get("artists", [])[:2])
    return f"{item['name']}, de {artists}" if artists else str(item["name"])


async def search(what: str, kind: str) -> dict[str, Any]:
    _, data = await api("GET", "/search", {"q": what, "type": kind, "limit": 5})
    items: list[dict[str, Any]] = [
        i for i in ((data or {}).get(f"{kind}s") or {}).get("items", []) if i
    ]
    if not items:
        raise nyx.Error(f"No encuentro «{what}» en Spotify.")
    return items[0]


async def playlist(what: str) -> dict[str, Any]:
    """Las listas del usuario primero («pon mi lista de correr»); si no, las de Spotify."""
    wanted = norm(what).removeprefix("mi lista ").removeprefix("lista ")
    _, data = await api("GET", "/me/playlists", {"limit": 50})
    mine: list[dict[str, Any]] = [p for p in (data or {}).get("items", []) if p]
    for p in mine:
        if norm(p["name"]) == wanted:
            return p
    for p in mine:
        if wanted and wanted in norm(p["name"]):
            return p
    return await search(what, "playlist")


# --- Reproducir ---------------------------------------------------------------------------------


async def device() -> str:
    """El dispositivo donde poner la música: el activo, el PC o cualquiera. Si no hay
    ninguno, abre la app de Spotify y espera un poco a que aparezca."""
    for attempt in range(9):
        _, data = await api("GET", "/me/player/devices")
        devices = [d for d in (data or {}).get("devices", []) if not d.get("is_restricted")]
        if devices:
            best = next((d for d in devices if d.get("is_active")), None)
            best = best or next((d for d in devices if d.get("type") == "Computer"), devices[0])
            return str(best["id"])
        if attempt == 0:
            await nyx.ask("open.uri", {"uri": "spotify:"})
        await asyncio.sleep(1)
    raise nyx.Error(NO_DEVICE)


async def play(body: dict[str, Any]) -> None:
    status, _ = await api("PUT", "/me/player/play", body=body)
    if status == 404:  # sin dispositivo activo
        status, _ = await api("PUT", "/me/player/play", {"device_id": await device()}, body)
    if status not in (200, 202, 204):
        raise nyx.Error("Spotify no ha podido ponerlo.")


# --- Herramientas -------------------------------------------------------------------------------


@nyx.tool
async def spotify_play(que: str, tipo: str | None = None) -> str:
    if not await connected():
        await nyx.ask("open.uri", {"uri": f"spotify:search:{quote(que)}"})
        missing = NOT_CONNECTED if await client_id() else NO_CLIENT
        return f"Te he abierto la búsqueda en Spotify. {missing}"
    kind = KINDS.get(tipo or "cancion", "track")
    if kind == "playlist":
        found = await playlist(que)
        await play({"context_uri": found["uri"]})
        return f"Pongo tu lista «{found['name']}»."
    found = await search(que, kind)
    if kind == "track":
        # Dentro de su disco: al acabar sigue sonando música en vez de pararse.
        album = (found.get("album") or {}).get("uri")
        body = (
            {"context_uri": album, "offset": {"uri": found["uri"]}}
            if album
            else {"uris": [found["uri"]]}
        )
        await play(body)
    else:
        await play({"context_uri": found["uri"]})
    return f"Pongo «{label(found)}»."


@nyx.tool
async def spotify_queue(que: str) -> str:
    found = await search(que, "track")
    status, _ = await api("POST", "/me/player/queue", {"uri": found["uri"]})
    if status == 404:
        raise nyx.Error("Pon algo en Spotify primero y luego te lo añado a la cola.")
    return f"En la cola: «{label(found)}»."


async def now_playing() -> dict[str, Any] | None:
    status, data = await api("GET", "/me/player/currently-playing")
    if status == 204 or not data or not data.get("item"):
        return None
    return dict(data)


@nyx.tool
async def spotify_like() -> str:
    playing = await now_playing()
    if playing is None:
        raise nyx.Error("No suena nada en Spotify.")
    item = playing["item"]
    status, _ = await api("PUT", "/me/library", {"uris": item["uri"]})
    if status == 400:  # por si la API lo quiere en el cuerpo
        status, _ = await api("PUT", "/me/library", body={"uris": [item["uri"]]})
    if status not in (200, 201, 204):
        raise nyx.Error("Spotify no ha podido guardarla.")
    return f"Guardada en tus favoritas: «{label(item)}»."


@nyx.tool
async def spotify_now() -> dict[str, str]:
    playing = await now_playing()
    if playing is None:
        return {"message": "No suena nada en Spotify."}
    item = playing["item"]
    album = (item.get("album") or {}).get("name")
    text = f"«{label(item)}»" + (f", del disco «{album}»" if album else "")
    state = "Suena" if playing.get("is_playing") else "En pausa"
    return {"message": f"{state}: {text}.", "display": f"{state}: {label(item)}"}


@nyx.tool
async def spotify_mode(modo: str) -> str:
    if modo in ("aleatorio", "sin aleatorio"):
        on = modo == "aleatorio"
        status, _ = await api("PUT", "/me/player/shuffle", {"state": "true" if on else "false"})
        answer = "Aleatorio activado." if on else "Aleatorio quitado."
    else:
        state = {"repetir": "context", "repetir cancion": "track", "sin repetir": "off"}[modo]
        status, _ = await api("PUT", "/me/player/repeat", {"state": state})
        answer = {
            "context": "Repito lo que suena.",
            "track": "Repito esta canción.",
            "off": "Sin repetir.",
        }[state]
    if status == 404:
        raise nyx.Error("Pon algo en Spotify primero.")
    return answer


@nyx.tool
async def spotify_connect(accion: str = "conectar") -> str:
    global _login
    if accion == "desconectar":
        await nyx.ask("secrets.delete", {"key": "refresh_token"})
        _access["token"] = None
        return "Spotify desconectado."
    app = await client_id()
    if not app:
        raise nyx.Error(NO_CLIENT)
    if _login is not None and not _login.done():
        return "Ya te he abierto Spotify en el navegador: entra y acepta."
    # En segundo plano: iniciar sesión puede llevar un rato y Nyx no se queda esperando.
    _login = asyncio.create_task(_connect(app))
    return "Te abro Spotify en el navegador: entra y acepta. Te aviso cuando esté."


async def _connect(app: str) -> None:
    try:
        tokens = await nyx.ask(
            "oauth.authorize",
            {
                "authorize_url": AUTHORIZE_URL,
                "token_url": TOKEN_URL,
                "client_id": app,
                "scopes": SCOPES,
                "timeout_s": 240,
            },
            timeout_s=260,
        )
        await _store(tokens)
        note = {"title": "Spotify conectado", "text": "Ya puedo poner lo que me pidas."}
    except (RuntimeError, TimeoutError) as e:
        note = {"title": "Spotify no se ha conectado", "text": str(e)[:150]}
    await nyx.ask("notify", note)
