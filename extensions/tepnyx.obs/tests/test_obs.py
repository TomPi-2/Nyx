"""La extensión de OBS contra un OBS falso que habla obs-websocket 5 (sin OBS ni Nyx)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from nyx_sdk.testing import ExtensionError, FakeNyx, PermissionDeniedError

FOLDER = Path(__file__).resolve().parents[1]


class FakeObs:
    """Lo justo de obs-websocket 5: hola, identificarse (con contraseña) y peticiones."""

    def __init__(self, password: str | None = None) -> None:
        self.password = password
        self.running = True
        self.recording = self.paused = self.streaming = self.replay = False
        self.scene = "Juego"
        self.scenes = ["Juego", "Charla", "Pausa"]
        self.inputs = {"Mic/Aux": False, "Audio del escritorio": False, "Música": False}
        self.items = {
            "Juego": [{"sceneItemId": 3, "sourceName": "Cámara", "sceneItemEnabled": True}]
        }
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._queue: list[str] = []
        self._salt, self._challenge = "sal", "reto"
        self._closed: str | None = None

    def install(self, nyx: FakeNyx) -> None:
        nyx.answer("ws.open", self.open)
        nyx.answer("ws.send", self.send)
        nyx.answer("ws.recv", self.recv)
        nyx.answer("ws.close", None)

    def open(self, params: dict[str, Any]) -> int:
        assert params["url"] == "ws://localhost:4455"
        if not self.running:
            raise OSError("no se ha podido conectar")
        hello: dict[str, Any] = {"obsWebSocketVersion": "5.5.0", "rpcVersion": 1}
        if self.password:
            hello["authentication"] = {"salt": self._salt, "challenge": self._challenge}
        self._push(0, hello)
        return 1

    def recv(self, params: dict[str, Any]) -> str | None:
        if self._closed:
            raise ConnectionError(f"la conexión se ha cerrado: {self._closed}")
        return self._queue.pop(0) if self._queue else None

    def _push(self, op: int, d: dict[str, Any]) -> None:
        self._queue.append(json.dumps({"op": op, "d": d}))

    def send(self, params: dict[str, Any]) -> None:
        msg = json.loads(params["text"])
        if msg["op"] == 1:
            if self.password:
                secret = base64.b64encode(
                    hashlib.sha256((self.password + self._salt).encode()).digest()
                ).decode()
                good = base64.b64encode(
                    hashlib.sha256((secret + self._challenge).encode()).digest()
                ).decode()
                if msg["d"].get("authentication") != good:
                    self._closed = "received 4009 (Authentication failed)"  # OBS cuelga
                    return
            self._push(2, {"negotiatedRpcVersion": 1})
            return
        d = msg["d"]
        kind, data = d["requestType"], d.get("requestData", {})
        self.requests.append((kind, data))
        code, out = self.handle(kind, data)
        status = {"result": code == 100, "code": code}
        self._push(7, {"requestId": d["requestId"], "requestStatus": status, "responseData": out})

    def handle(self, kind: str, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        toggles = {
            "StartRecord": ("recording", True),
            "StopRecord": ("recording", False),
            "StartStream": ("streaming", True),
            "StopStream": ("streaming", False),
            "StartReplayBuffer": ("replay", True),
            "StopReplayBuffer": ("replay", False),
        }
        if kind in toggles:
            attr, on = toggles[kind]
            if getattr(self, attr) == on:
                return (500 if on else 501), {}
            setattr(self, attr, on)
            return 100, (
                {"outputPath": "C:/Videos/2026-11-15 20-00-00.mkv"} if kind == "StopRecord" else {}
            )
        if kind == "PauseRecord":
            if not self.recording:
                return 501, {}
            self.paused = True
            return 100, {}
        if kind == "SaveReplayBuffer":
            return (100 if self.replay else 501), {}
        if kind == "GetSceneList":
            scenes = [{"sceneName": s} for s in reversed(self.scenes)]
            return 100, {"currentProgramSceneName": self.scene, "scenes": scenes}
        if kind == "GetCurrentProgramScene":
            return 100, {"currentProgramSceneName": self.scene}
        if kind == "SetCurrentProgramScene":
            self.scene = data["sceneName"]
            return 100, {}
        if kind == "GetSpecialInputs":
            return 100, {"desktop1": "Audio del escritorio", "mic1": "Mic/Aux"}
        if kind == "GetInputList":
            return 100, {"inputs": [{"inputName": n} for n in self.inputs]}
        if kind == "SetInputMute":
            self.inputs[data["inputName"]] = data["inputMuted"]
            return 100, {}
        if kind == "ToggleInputMute":
            self.inputs[data["inputName"]] = not self.inputs[data["inputName"]]
            return 100, {"inputMuted": self.inputs[data["inputName"]]}
        if kind == "SetInputVolume":
            return 100, {}
        if kind == "GetSceneItemList":
            return 100, {"sceneItems": self.items.get(data["sceneName"], [])}
        if kind == "SetSceneItemEnabled":
            for item in self.items[data["sceneName"]]:
                if item["sceneItemId"] == data["sceneItemId"]:
                    item["sceneItemEnabled"] = data["sceneItemEnabled"]
            return 100, {}
        if kind == "GetRecordDirectory":
            return 100, {"recordDirectory": "C:/Videos"}
        if kind == "SaveSourceScreenshot":
            return 100, {}
        if kind == "GetRecordStatus":
            return 100, {
                "outputActive": self.recording,
                "outputPaused": self.paused,
                "outputTimecode": "00:01:02.345",
            }
        if kind == "GetStreamStatus":
            return 100, {"outputActive": self.streaming, "outputTimecode": "00:00:00.000"}
        if kind == "GetReplayBufferStatus":
            return 100, {"outputActive": self.replay}
        return 204, {}  # UnknownRequestType


def setup(password: str | None = None, saved: str | None = None) -> tuple[FakeNyx, FakeObs]:
    nyx = FakeNyx(FOLDER, settings={"password": saved} if saved else {})
    obs = FakeObs(password)
    obs.install(nyx)
    return nyx, obs


def test_record_start_stop_and_twice() -> None:
    nyx, obs = setup()
    assert nyx.run("obs_record", accion="empezar") == "Grabando en OBS."
    assert obs.recording
    assert nyx.run("obs_record", accion="empezar") == "Ya estaba grabando."
    assert nyx.run("obs_record", accion="parar") == "Grabación guardada: 2026-11-15 20-00-00.mkv."
    assert nyx.run("obs_record", accion="pausar") == "No estás grabando."


def test_password_from_settings() -> None:
    nyx, obs = setup(password="secreta", saved="secreta")
    assert nyx.run("obs_stream", accion="empezar") == "Directo empezado en OBS."
    assert obs.streaming


def test_without_or_with_a_wrong_password() -> None:
    nyx, _ = setup(password="secreta")
    with pytest.raises(ExtensionError, match="pide contraseña"):
        nyx.run("obs_status")
    nyx, _ = setup(password="secreta", saved="otra")
    with pytest.raises(ExtensionError, match="no es correcta"):
        nyx.run("obs_status")


def test_obs_closed() -> None:
    nyx, obs = setup()
    obs.running = False
    with pytest.raises(ExtensionError, match="no está abierto"):
        nyx.run("obs_record", accion="empezar")


def test_scenes_as_people_say_them() -> None:
    nyx, obs = setup()
    assert nyx.run("obs_scene", nombre="la escena de charla") == "Escena «Charla»."
    assert obs.scene == "Charla"
    assert nyx.run("obs_scene", nombre="pausa") == "Escena «Pausa»."
    assert nyx.run("obs_scene", nombre="Pausa") == "Ya estás en «Pausa»."
    with pytest.raises(ExtensionError, match="No encuentro"):
        nyx.run("obs_scene", nombre="cocina")


def test_mute_the_mic_and_the_music() -> None:
    nyx, obs = setup()
    assert (
        nyx.run("obs_mute", fuente="el micro", estado="silenciar") == "«Mic/Aux» silenciado en OBS."
    )
    assert obs.inputs["Mic/Aux"] is True
    assert nyx.run("obs_mute", fuente="musica", estado="alternar") == "«Música» silenciado en OBS."
    assert nyx.run("obs_mute", fuente="sonido del pc", estado="activar").startswith("«Audio del")
    assert nyx.run("obs_volume", fuente="micro", porcentaje=150) == "«Mic/Aux» al 100 % en OBS."
    assert ("SetInputVolume", {"inputName": "Mic/Aux", "inputVolumeMul": 1.0}) in obs.requests


def test_hide_the_camera() -> None:
    nyx, obs = setup()
    assert (
        nyx.run("obs_show", fuente="la cámara", estado="ocultar") == "«Cámara» oculta en «Juego»."
    )
    assert obs.items["Juego"][0]["sceneItemEnabled"] is False


def test_replay_needs_the_buffer() -> None:
    nyx, _ = setup()
    assert "pídeme que lo active" in nyx.run("obs_replay", accion="guardar")
    nyx.run("obs_replay", accion="activar")
    assert nyx.run("obs_replay", accion="guardar") == "Repetición guardada."


def test_screenshot_and_status() -> None:
    nyx, obs = setup()
    shot = nyx.run("obs_screenshot")
    assert shot["secondary"].startswith("Captura de OBS ")
    kind, data = obs.requests[-1]
    assert kind == "SaveSourceScreenshot" and data["sourceName"] == "Juego"
    obs.recording = True
    status = nyx.run("obs_status")
    assert status["display"] == "Grabando (00:01:02), sin directo. Escena «Juego»."
    assert "Escenas: Juego, Charla, Pausa." in status["secondary"]


def test_only_local_obs() -> None:
    """Sin el permiso de su manifiesto, Nyx no la deja conectarse."""
    nyx = FakeNyx(FOLDER, permissions=[])
    with pytest.raises(ExtensionError, match="no está abierto"):
        nyx.run("obs_status")  # ws.open denegado → para el usuario, OBS no responde
    assert nyx.asks[0][0] == "ws.open"
    assert issubclass(PermissionDeniedError, RuntimeError)
