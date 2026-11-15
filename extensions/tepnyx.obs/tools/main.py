# SPDX-License-Identifier: MIT
"""OBS Studio con la voz (extensión oficial de Tepnyx; tarea 7.14).

Habla con OBS por obs-websocket 5 (viene dentro de OBS desde la 28) en ws://localhost:4455, a
través de Nyx (`ws.*`): la extensión no tiene red propia ni pulsa teclas. Si OBS pide
contraseña, la pone el usuario en Ajustes → Extensiones y se lee con `settings.get`.

Cada orden abre su conexión, se identifica, pide lo suyo y la cierra: OBS puede cerrarse o
reiniciarse entre una orden y otra sin que la extensión se entere.
"""

from __future__ import annotations

import base64
import contextlib
import difflib
import hashlib
import itertools
import json
import os
import time
import unicodedata
from typing import Any

import nyx

URL = "ws://localhost:4455"
RPC_VERSION = 1
SETTINGS = "Ajustes → Extensiones → OBS Studio"
NOT_RUNNING = (
    "OBS no está abierto o no tiene el servidor WebSocket activado (en OBS: Herramientas → "
    "Configuración del servidor WebSocket → Habilitar)."
)

# Códigos de obs-websocket 5 (RequestStatus).
OUTPUT_RUNNING = 500
OUTPUT_NOT_RUNNING = 501
OUTPUT_PAUSED = 502
OUTPUT_NOT_PAUSED = 503
OUTPUT_DISABLED = 504

MIC = {"micro", "microfono", "mic", "mi micro", "mi microfono", "mi voz", "voz"}
DESKTOP = {
    "escritorio",
    "audio del escritorio",
    "sonido del escritorio",
    "pc",
    "audio del pc",
    "sonido del pc",
    "ordenador",
    "sonido del ordenador",
    "audio del ordenador",
}
FILLER = {"el", "la", "los", "las", "de", "del", "mi", "escena", "fuente", "en", "obs"}

_ids = itertools.count(1)


class ObsError(nyx.Error):
    """Lo que OBS ha contestado que no; el texto es para el usuario."""

    def __init__(self, code: int, comment: str) -> None:
        super().__init__(f"OBS dice que no: {comment}" if comment else "OBS no ha podido hacerlo.")
        self.code = code


def auth_answer(password: str, salt: str, challenge: str) -> str:
    """La respuesta al reto de obs-websocket 5."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class Obs:
    """Una conexión con OBS para una orden."""

    def __init__(self) -> None:
        self.sock: int | None = None

    async def __aenter__(self) -> Obs:
        try:
            self.sock = await nyx.ask("ws.open", {"url": URL})
        except RuntimeError as e:
            raise nyx.Error(NOT_RUNNING) from e
        hello = await self._recv()
        if hello.get("op") != 0:
            raise nyx.Error("OBS ha contestado algo raro al conectar.")
        identify: dict[str, Any] = {"rpcVersion": RPC_VERSION, "eventSubscriptions": 0}
        auth = (hello.get("d") or {}).get("authentication")
        if auth:
            password = await nyx.ask("settings.get", {"key": "password"})
            if not password:
                raise nyx.Error(f"OBS pide contraseña: ponla en {SETTINGS}.")
            identify["authentication"] = auth_answer(password, auth["salt"], auth["challenge"])
        await self._send(1, identify)
        try:
            identified = await self._recv()
        except RuntimeError as e:  # OBS cierra la conexión (4009) si la contraseña no vale
            raise nyx.Error(f"La contraseña de OBS no es correcta: cámbiala en {SETTINGS}.") from e
        if identified.get("op") != 2:
            raise nyx.Error("OBS no me ha dejado conectarme.")
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.sock is not None:
            with contextlib.suppress(RuntimeError):
                await nyx.ask("ws.close", {"id": self.sock})

    async def _send(self, op: int, data: dict[str, Any]) -> None:
        text = json.dumps({"op": op, "d": data})
        await nyx.ask("ws.send", {"id": self.sock, "text": text})

    async def _recv(self) -> dict[str, Any]:
        text = await nyx.ask("ws.recv", {"id": self.sock, "timeout_s": 5})
        if text is None:
            raise nyx.Error("OBS no contesta.")
        try:
            message = json.loads(text)
        except ValueError as e:
            raise nyx.Error("OBS ha contestado algo que no entiendo.") from e
        return message if isinstance(message, dict) else {}

    async def call(self, request: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Hace una petición y devuelve `responseData`. Lanza ObsError si OBS dice que no."""
        request_id = f"nyx-{next(_ids)}"
        body: dict[str, Any] = {"requestType": request, "requestId": request_id}
        if data:
            body["requestData"] = data
        await self._send(6, body)
        for _ in range(50):  # sin suscripciones no llegan eventos, pero por si acaso
            message = await self._recv()
            d = message.get("d") or {}
            if message.get("op") == 7 and d.get("requestId") == request_id:
                status = d.get("requestStatus") or {}
                if not status.get("result"):
                    raise ObsError(int(status.get("code") or 0), str(status.get("comment") or ""))
                return d.get("responseData") or {}
        raise nyx.Error("OBS no contesta.")


# --- Nombres como los dice la gente -------------------------------------------------------------


def norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = "".join(c if c.isalnum() else " " for c in plain)
    return " ".join(plain.split())


def bare(text: str) -> str:
    """Sin artículos ni «escena»/«fuente»: «la escena de juego» → «juego»."""
    words = [w for w in norm(text).split() if w not in FILLER]
    return " ".join(words) or norm(text)


def pick(query: str, names: list[str], what: str) -> str:
    """El nombre de OBS que quiere decir `query`: igual, contenido o parecido. Si hay varios
    que valen, pregunta; si ninguno, dice cuáles hay."""
    if not names:
        raise nyx.Error(f"No hay {what} en OBS.")
    q = bare(query)
    keyed = {name: bare(name) for name in names}
    exact = [n for n, k in keyed.items() if k == q or norm(n) == norm(query)]
    if exact:
        return exact[0]
    inside = [n for n, k in keyed.items() if q in k or (len(k) >= 3 and k in q)]
    if len(inside) == 1:
        return inside[0]
    if len(inside) > 1:
        raise nyx.Error(f"Hay varias parecidas: {', '.join(inside[:6])}. ¿Cuál?")
    close = difflib.get_close_matches(q, list(keyed.values()), n=1, cutoff=0.6)
    if close:
        return next(n for n, k in keyed.items() if k == close[0])
    raise nyx.Error(f"No encuentro «{query}» entre {what} de OBS: {', '.join(names[:10])}.")


async def audio_input(obs: Obs, query: str) -> str:
    q = bare(query)
    mic, desktop = q in {bare(w) for w in MIC}, q in {bare(w) for w in DESKTOP}
    if mic or desktop:
        special = await obs.call("GetSpecialInputs")
        found = special.get("mic1" if mic else "desktop1")
        if found:
            return str(found)
        if mic:  # el micro como fuente de una escena
            inputs = (await obs.call("GetInputList", {"inputKind": "wasapi_input_capture"}))[
                "inputs"
            ]
            if len(inputs) == 1:
                return str(inputs[0]["inputName"])
    inputs = (await obs.call("GetInputList")).get("inputs", [])
    return pick(query, [str(i["inputName"]) for i in inputs], "los audios")


def clock(timecode: object) -> str:
    """«00:12:31.416» → «00:12:31»."""
    return str(timecode or "").split(".")[0]


# --- Herramientas -------------------------------------------------------------------------------


@nyx.tool
async def obs_record(accion: str) -> str:
    async with Obs() as obs:
        try:
            if accion == "empezar":
                await obs.call("StartRecord")
                return "Grabando en OBS."
            if accion == "parar":
                data = await obs.call("StopRecord")
                name = os.path.basename(str(data.get("outputPath") or ""))
                return f"Grabación guardada: {name}." if name else "Grabación guardada."
            if accion == "pausar":
                await obs.call("PauseRecord")
                return "Grabación en pausa."
            if accion == "reanudar":
                await obs.call("ResumeRecord")
                return "Sigo grabando."
        except ObsError as e:
            if e.code == OUTPUT_RUNNING:
                return "Ya estaba grabando."
            if e.code == OUTPUT_NOT_RUNNING:
                return "No estás grabando."
            if e.code == OUTPUT_PAUSED:
                return "La grabación ya estaba en pausa."
            if e.code == OUTPUT_NOT_PAUSED:
                return "La grabación no estaba en pausa."
            raise
    raise nyx.Error(f"No sé hacer «{accion}» con la grabación.")


@nyx.tool
async def obs_stream(accion: str) -> str:
    async with Obs() as obs:
        try:
            if accion == "empezar":
                await obs.call("StartStream")
                return "Directo empezado en OBS."
            if accion == "parar":
                await obs.call("StopStream")
                return "Directo terminado."
        except ObsError as e:
            if e.code == OUTPUT_RUNNING:
                return "Ya estabas en directo."
            if e.code == OUTPUT_NOT_RUNNING:
                return "No estás en directo."
            raise
    raise nyx.Error(f"No sé hacer «{accion}» con el directo.")


@nyx.tool
async def obs_replay(accion: str) -> str:
    async with Obs() as obs:
        try:
            if accion == "guardar":
                await obs.call("SaveReplayBuffer")
                return "Repetición guardada."
            if accion == "activar":
                await obs.call("StartReplayBuffer")
                return "Búfer de repetición activado: ya puedes pedirme que guarde lo último."
            if accion == "desactivar":
                await obs.call("StopReplayBuffer")
                return "Búfer de repetición desactivado."
        except ObsError as e:
            if e.code == OUTPUT_NOT_RUNNING:
                if accion == "guardar":
                    return "El búfer de repetición no está activado: pídeme que lo active primero."
                return "El búfer de repetición ya estaba desactivado."
            if e.code == OUTPUT_RUNNING:
                return "El búfer de repetición ya estaba activado."
            if e.code == OUTPUT_DISABLED:
                raise nyx.Error(
                    "La repetición está apagada en OBS: Ajustes → Salida → Búfer de repetición."
                ) from e
            raise
    raise nyx.Error(f"No sé hacer «{accion}» con la repetición.")


@nyx.tool
async def obs_virtualcam(accion: str) -> str:
    async with Obs() as obs:
        try:
            if accion == "activar":
                await obs.call("StartVirtualCam")
                return "Cámara virtual activada."
            if accion == "desactivar":
                await obs.call("StopVirtualCam")
                return "Cámara virtual desactivada."
        except ObsError as e:
            if e.code == OUTPUT_RUNNING:
                return "La cámara virtual ya estaba activada."
            if e.code == OUTPUT_NOT_RUNNING:
                return "La cámara virtual ya estaba desactivada."
            raise
    raise nyx.Error(f"No sé hacer «{accion}» con la cámara virtual.")


@nyx.tool
async def obs_scene(nombre: str) -> str:
    async with Obs() as obs:
        data = await obs.call("GetSceneList")
        names = [str(s["sceneName"]) for s in data.get("scenes", [])]
        scene = pick(nombre, names, "las escenas")
        if scene == data.get("currentProgramSceneName"):
            return f"Ya estás en «{scene}»."
        await obs.call("SetCurrentProgramScene", {"sceneName": scene})
        return f"Escena «{scene}»."


@nyx.tool
async def obs_mute(fuente: str, estado: str) -> str:
    async with Obs() as obs:
        name = await audio_input(obs, fuente)
        if estado == "alternar":
            muted = bool((await obs.call("ToggleInputMute", {"inputName": name}))["inputMuted"])
        else:
            muted = estado == "silenciar"
            await obs.call("SetInputMute", {"inputName": name, "inputMuted": muted})
        return f"«{name}» silenciado en OBS." if muted else f"«{name}» vuelve a sonar en OBS."


@nyx.tool
async def obs_volume(fuente: str, porcentaje: int) -> str:
    level = max(0, min(100, porcentaje))
    async with Obs() as obs:
        name = await audio_input(obs, fuente)
        await obs.call("SetInputVolume", {"inputName": name, "inputVolumeMul": level / 100})
        return f"«{name}» al {level} % en OBS."


@nyx.tool
async def obs_show(fuente: str, estado: str, escena: str | None = None) -> str:
    async with Obs() as obs:
        scenes = await obs.call("GetSceneList")
        if escena:
            names = [str(s["sceneName"]) for s in scenes.get("scenes", [])]
            scene = pick(escena, names, "las escenas")
        else:
            scene = str(scenes.get("currentProgramSceneName") or "")
        items = (await obs.call("GetSceneItemList", {"sceneName": scene})).get("sceneItems", [])
        by_name = {str(i["sourceName"]): i for i in items}
        source = pick(fuente, list(by_name), f"las fuentes de «{scene}»")
        item = by_name[source]
        visible = not item.get("sceneItemEnabled") if estado == "alternar" else estado == "mostrar"
        await obs.call(
            "SetSceneItemEnabled",
            {"sceneName": scene, "sceneItemId": item["sceneItemId"], "sceneItemEnabled": visible},
        )
        return f"«{source}» {'a la vista' if visible else 'oculta'} en «{scene}»."


@nyx.tool
async def obs_screenshot() -> dict[str, str]:
    async with Obs() as obs:
        scene = str((await obs.call("GetCurrentProgramScene"))["currentProgramSceneName"])
        folder = str((await obs.call("GetRecordDirectory"))["recordDirectory"])
        name = f"Captura de OBS {time.strftime('%Y-%m-%d %H-%M-%S')}.png"
        await obs.call(
            "SaveSourceScreenshot",
            {
                "sourceName": scene,
                "imageFormat": "png",
                "imageFilePath": os.path.join(folder, name),
            },
        )
        return {"message": "Captura guardada en la carpeta de grabaciones.", "secondary": name}


@nyx.tool
async def obs_status() -> dict[str, str]:
    async with Obs() as obs:
        record = await obs.call("GetRecordStatus")
        stream = await obs.call("GetStreamStatus")
        scenes = await obs.call("GetSceneList")
        inputs = (await obs.call("GetInputList")).get("inputs", [])
        try:
            replay = bool((await obs.call("GetReplayBufferStatus")).get("outputActive"))
        except ObsError:
            replay = False  # apagada en los ajustes de OBS
    parts = []
    if record.get("outputPaused"):
        parts.append(f"grabación en pausa ({clock(record.get('outputTimecode'))})")
    elif record.get("outputActive"):
        parts.append(f"grabando ({clock(record.get('outputTimecode'))})")
    else:
        parts.append("sin grabar")
    if stream.get("outputActive"):
        parts.append(f"en directo ({clock(stream.get('outputTimecode'))})")
    else:
        parts.append("sin directo")
    if replay:
        parts.append("repetición activada")
    current = str(scenes.get("currentProgramSceneName") or "")
    # OBS las da de abajo arriba: al revés, como se ven en su lista.
    names = [str(s["sceneName"]) for s in scenes.get("scenes", [])][::-1]
    audio = [str(i["inputName"]) for i in inputs][:10]
    summary = ", ".join(parts).capitalize() + f". Escena «{current}»."
    details = f"Escenas: {', '.join(names)}." + (f" Fuentes: {', '.join(audio)}." if audio else "")
    return {"message": f"{summary} {details}", "display": summary, "secondary": details}
