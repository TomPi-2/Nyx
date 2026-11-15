"""La extensión de Spotify contra un Spotify falso (Web API y cuentas), sin Nyx ni red."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from nyx_sdk.testing import ExtensionError, FakeNyx

FOLDER = Path(__file__).resolve().parents[1]

TRACK = {
    "uri": "spotify:track:1",
    "name": "Bohemian Rhapsody",
    "artists": [{"name": "Queen"}],
    "album": {"uri": "spotify:album:9", "name": "A Night at the Opera"},
}


class FakeSpotify:
    def __init__(self, *, premium: bool = True, devices: int = 1) -> None:
        self.premium = premium
        self.devices = [{"id": f"pc{i}", "type": "Computer"} for i in range(devices)]
        self.calls: list[tuple[str, str, dict[str, str], Any]] = []
        self.secrets: dict[str, str] = {}
        self.playing: dict[str, Any] | None = {"is_playing": True, "item": TRACK}
        self.refresh_ok = True
        self.opened: list[str] = []
        self.notes: list[dict[str, str]] = []

    def install(self, nyx: FakeNyx) -> None:
        nyx.answer("net.fetch", self.fetch)
        nyx.answer("secrets.get", lambda p: self.secrets.get(p["key"]))
        nyx.answer("secrets.set", lambda p: self.secrets.__setitem__(p["key"], p["value"]))
        nyx.answer("secrets.delete", lambda p: self.secrets.pop(p["key"], None))
        nyx.answer("open.uri", lambda p: self.opened.append(p["uri"]))
        nyx.answer("notify", self.notes.append)
        nyx.answer(
            "oauth.authorize",
            lambda p: {"access_token": "nuevo", "refresh_token": "r1", "expires_in": 3600},
        )

    def fetch(self, p: dict[str, Any]) -> dict[str, Any]:
        url = urlsplit(p["url"])
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        is_json = (p.get("headers") or {}).get("Content-Type") == "application/json"
        body = json.loads(p["body"]) if is_json else None
        self.calls.append((p["method"], url.path, query, body))
        if url.netloc == "accounts.spotify.com":
            if not self.refresh_ok:
                return {"status": 400, "body": '{"error": "invalid_grant"}'}
            return {"status": 200, "body": '{"access_token": "t", "expires_in": 3600}'}
        status, data = self.route(p["method"], url.path.removeprefix("/v1"), query, body)
        return {"status": status, "body": json.dumps(data) if data is not None else ""}

    def route(self, method: str, path: str, query: dict[str, str], body: Any) -> tuple[int, Any]:
        if path == "/search":
            kind = query["type"]
            items = {
                "track": [TRACK],
                "artist": [{"uri": "spotify:artist:5", "name": "Queen"}],
                "album": [
                    {
                        "uri": "spotify:album:9",
                        "name": "A Night at the Opera",
                        "artists": [{"name": "Queen"}],
                    }
                ],
                "playlist": [None, {"uri": "spotify:playlist:7", "name": "Rock clásico"}],
            }[kind]
            return 200, {f"{kind}s": {"items": items}}
        if path == "/me/playlists":
            return 200, {"items": [{"uri": "spotify:playlist:1", "name": "Para correr"}]}
        if path == "/me/player/devices":
            return 200, {"devices": self.devices}
        if path == "/me/player/play":
            if not self.premium:
                return 403, {"error": {"status": 403, "reason": "PREMIUM_REQUIRED"}}
            return (204, None) if self.devices else (404, {"error": {"reason": "NO_ACTIVE_DEVICE"}})
        if path == "/me/player/currently-playing":
            return (200, self.playing) if self.playing else (204, None)
        if path in ("/me/library", "/me/player/queue", "/me/player/shuffle", "/me/player/repeat"):
            return 204, None
        return 404, None


def setup(*, client: bool = True, logged: bool = True, **kw: Any) -> tuple[FakeNyx, FakeSpotify]:
    nyx = FakeNyx(FOLDER, settings={"client_id": "mi-app"} if client else {})
    spotify = FakeSpotify(**kw)
    if logged:
        spotify.secrets["refresh_token"] = "r0"
    spotify.install(nyx)
    return nyx, spotify


def test_play_a_song_inside_its_album() -> None:
    nyx, spotify = setup()
    assert nyx.run("spotify_play", que="bohemian rhapsody") == (
        "Pongo «Bohemian Rhapsody, de Queen»."
    )
    method, path, _, body = spotify.calls[-1]
    assert (method, path) == ("PUT", "/v1/me/player/play")
    assert body == {"context_uri": "spotify:album:9", "offset": {"uri": "spotify:track:1"}}
    search = next(c for c in spotify.calls if c[1] == "/v1/search")
    assert search[2]["limit"] == "5"  # nunca más de 10 (apps nuevas de Spotify)


def test_artist_and_my_playlist() -> None:
    nyx, spotify = setup()
    assert nyx.run("spotify_play", que="queen", tipo="artista") == "Pongo «Queen»."
    assert nyx.run("spotify_play", que="mi lista para correr", tipo="lista") == (
        "Pongo tu lista «Para correr»."
    )
    assert spotify.calls[-1][3] == {"context_uri": "spotify:playlist:1"}


def test_without_connecting_opens_the_search() -> None:
    nyx, spotify = setup(client=False, logged=False)
    answer = nyx.run("spotify_play", que="la macarena")
    assert spotify.opened == ["spotify:search:la%20macarena"]
    assert "¿cómo conecto Spotify?" in answer and spotify.calls == []
    nyx, spotify = setup(logged=False)
    assert "conecta Spotify" in nyx.run("spotify_play", que="queen")


def test_no_device_opens_spotify_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    nyx, spotify = setup(devices=0)
    nyx.load()
    assert nyx.module is not None

    async def no_wait(_s: float) -> None:
        spotify.devices = [{"id": "pc", "type": "Computer"}]  # Spotify ya ha arrancado

    monkeypatch.setattr(nyx.module.asyncio, "sleep", no_wait)
    assert nyx.run("spotify_play", que="queen").startswith("Pongo")
    assert spotify.opened == ["spotify:"]
    assert spotify.calls[-1][2] == {"device_id": "pc"}


def test_premium_is_needed_to_play() -> None:
    nyx, _ = setup(premium=False)
    with pytest.raises(ExtensionError, match="Premium"):
        nyx.run("spotify_play", que="queen")


def test_expired_session() -> None:
    nyx, spotify = setup()
    spotify.refresh_ok = False
    with pytest.raises(ExtensionError, match="seis meses"):
        nyx.run("spotify_now")
    assert "refresh_token" not in spotify.secrets  # el viejo ya no vale


def test_like_now_queue_and_modes() -> None:
    nyx, spotify = setup()
    assert nyx.run("spotify_like") == "Guardada en tus favoritas: «Bohemian Rhapsody, de Queen»."
    assert ("PUT", "/v1/me/library", {"uris": "spotify:track:1"}, None) in spotify.calls
    assert nyx.run("spotify_now")["display"] == "Suena: Bohemian Rhapsody, de Queen"
    assert nyx.run("spotify_queue", que="bohemian") == "En la cola: «Bohemian Rhapsody, de Queen»."
    assert nyx.run("spotify_mode", modo="repetir cancion") == "Repito esta canción."
    assert spotify.calls[-1][2] == {"state": "track"}
    spotify.playing = None
    assert nyx.run("spotify_now") == {"message": "No suena nada en Spotify."}


@pytest.mark.asyncio
async def test_connect_in_the_background() -> None:
    nyx, spotify = setup(logged=False)
    answer = await nyx.call("spotify_connect")
    assert "navegador" in answer
    assert nyx.module is not None
    await nyx.module._login  # termina sola, sin que Nyx espere
    assert spotify.secrets["refresh_token"] == "r1"
    assert spotify.notes == [
        {"title": "Spotify conectado", "text": "Ya puedo poner lo que me pidas."}
    ]
    oauth = nyx.asked("oauth.authorize")[0]
    assert oauth["token_url"] == "https://accounts.spotify.com/api/token"
    assert await nyx.call("spotify_connect", accion="desconectar") == "Spotify desconectado."
    assert "refresh_token" not in spotify.secrets


def test_connect_needs_the_app() -> None:
    nyx, _ = setup(client=False, logged=False)
    with pytest.raises(ExtensionError, match="cómo conecto"):
        nyx.run("spotify_connect")


def test_api_is_never_called_without_its_permission() -> None:
    nyx = FakeNyx(FOLDER, permissions=[], settings={"client_id": "x"})
    with pytest.raises(RuntimeError, match="sin permiso"):
        nyx.run("spotify_now")
