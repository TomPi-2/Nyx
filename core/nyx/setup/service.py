"""Asistente de primer arranque y Ajustes → Cerebro, Caché, Ayuda y Privacidad (fase 5d‑2).

Lo que la interfaz puede pedir (SetupRequested) y lo que contesta:
- «status»: estado completo (SetupStatusChanged): modelos que faltan, Ollama, whisper-server,
  la caché del sistema, los atajos aprendidos y las grabaciones guardadas.
- «download»: descarga lo que falte del catálogo (con su huella SHA-256) y el modelo de Ollama
  configurado, con progreso real (SetupProgress).
- «scan»: vuelve a escanear aplicaciones y carpetas.
- «forget_shortcut»: olvida un atajo aprendido (arg = la frase).
- «mic_test_start» / «mic_test_stop»: nivel del micrófono en directo (MicLevelChanged).
- «clear_samples» / «clear_activations»: manda a la papelera las grabaciones de calibración o
  el registro de activaciones. Nunca borrado permanente (SPEC sección 8).

Nada de esto sale del equipo salvo las descargas de modelos, que el usuario pide.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import (
    MicLevelChanged,
    SetupProgress,
    SetupRequested,
    SetupResult,
    SetupStatusChanged,
)
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.models import CATALOG, DownloadError, ModelFile, download, is_present
from nyx.paths import local_dir
from nyx.settings.model import Settings

log = logging.getLogger(__name__)

MB = 1024 * 1024
#: El nivel del micrófono se manda unas 15 veces por segundo.
MIC_EVERY_S = 1 / 15
#: La prueba del micrófono se para sola si nadie la para.
MIC_MAX_S = 120.0
#: Grabaciones de calibración (scripts/record_samples.py).
SAMPLES_DIR = ("training", "grabaciones")


class SetupService:
    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        *,
        index: Callable[[], SystemIndex | None] = lambda: None,
        shortcuts: Callable[[], ShortcutStore | None] = lambda: None,
        whisper_server: Callable[[], Path] | None = None,
        root: Path | None = None,
    ) -> None:
        self.bus = bus
        self.settings = settings
        self.index = index
        self.shortcuts = shortcuts
        self.whisper_server = whisper_server
        self.root = root or local_dir()
        self._downloading = False
        self._scanning = False
        self._mic: asyncio.Task[None] | None = None
        self._unsubscribe = bus.subscribe(SetupRequested, self._on_request)

    async def close(self) -> None:
        self._unsubscribe()
        await self._stop_mic()

    # --- estado ---

    async def status(self) -> dict[str, Any]:
        models = [
            {
                "key": m.key,
                "name": m.filename,
                "size_mb": m.size_mb,
                "license": m.license,
                "present": is_present(m),
            }
            for m in CATALOG
        ]
        index = self.index()
        shortcuts = self.shortcuts()
        last_scan = None
        if index is not None:
            with contextlib.suppress(Exception):
                last_scan = index.last_scan()
        return {
            "models": models,
            "ollama": await self._ollama_status(),
            "whisper": self.whisper_server is not None and self.whisper_server().exists(),
            "downloading": self._downloading,
            "index": None
            if index is None
            else {
                "total": len(index),
                "apps": len(index.entries({Kind.APP})),
                "games": len(index.entries({Kind.GAME})),
                "folders": len(index.entries({Kind.FOLDER})),
                "last_scan": last_scan,
                "scanning": self._scanning,
                "everything": _everything_installed(),
            },
            "shortcuts": []
            if shortcuts is None
            else [
                {"phrase": s.phrase, "tool": s.call.name, "uses": s.uses} for s in shortcuts.all()
            ],
            "samples": _count(self.root.joinpath(*SAMPLES_DIR), "*.wav"),
            "activations": _count(self.root / "activaciones", "*.jsonl"),
        }

    async def _ollama_status(self) -> dict[str, Any]:
        wanted = self.settings.llm.model
        try:
            async with httpx.AsyncClient(timeout=1.5) as http:
                resp = await http.get(f"{self.settings.llm.host}/api/tags")
                resp.raise_for_status()
                names = sorted(str(m["name"]) for m in resp.json().get("models", []))
        except (httpx.HTTPError, ValueError, KeyError):
            return {"running": False, "models": [], "wanted": wanted, "has_wanted": False}
        has = wanted in names or f"{wanted}:latest" in names
        return {"running": True, "models": names, "wanted": wanted, "has_wanted": has}

    async def _publish_status(self) -> None:
        await self.bus.publish(SetupStatusChanged(await self.status()))

    # --- peticiones ---

    async def _on_request(self, event: SetupRequested) -> None:
        handlers: dict[str, Callable[[], Awaitable[None]]] = {
            "status": self._publish_status,
            "download": self._download,
            "scan": self._scan,
            "forget_shortcut": lambda: self._forget(event.arg),
            "mic_test_start": self._start_mic,
            "mic_test_stop": self._stop_mic,
            "clear_samples": lambda: self._clear("clear_samples", self.root.joinpath(*SAMPLES_DIR)),
            "clear_activations": lambda: self._clear(
                "clear_activations", self.root / "activaciones"
            ),
        }
        handler = handlers.get(event.action)
        if handler is not None:
            await handler()

    async def _download(self) -> None:
        if self._downloading:
            return
        self._downloading = True
        await self._publish_status()
        loop = asyncio.get_running_loop()
        failed: list[str] = []
        try:
            for model in [m for m in CATALOG if not is_present(m)]:
                try:
                    await asyncio.to_thread(self._download_one, model, loop)
                except (DownloadError, OSError) as err:
                    log.warning("No se pudo descargar %s: %s", model.filename, err)
                    failed.append(model.filename)
                    await self.bus.publish(
                        SetupProgress(model.key, model.filename, 0, model.size_mb, True, str(err))
                    )
            if not await self._pull_ollama():
                failed.append(self.settings.llm.model)
        finally:
            self._downloading = False
        message = "No se pudo descargar: " + ", ".join(failed) if failed else None
        await self.bus.publish(SetupResult("download", not failed, message))
        await self._publish_status()

    def _download_one(self, model: ModelFile, loop: asyncio.AbstractEventLoop) -> None:
        last = [0.0]

        def progress(_: ModelFile, done: int, total: int) -> None:
            now = time.monotonic()
            if now - last[0] < 0.2:
                return
            last[0] = now
            event = SetupProgress(model.key, model.filename, done / MB, (total or 1) / MB)
            asyncio.run_coroutine_threadsafe(self.bus.publish(event), loop)

        download(model, progress=progress)
        done = SetupProgress(model.key, model.filename, model.size_mb, model.size_mb, True)
        asyncio.run_coroutine_threadsafe(self.bus.publish(done), loop).result()

    async def _pull_ollama(self) -> bool:
        """Descarga el modelo de Ollama configurado si Ollama está y no lo tiene."""
        status = await self._ollama_status()
        if not status["running"] or status["has_wanted"]:
            return True
        name = self.settings.llm.model
        key = f"ollama:{name}"
        last = 0.0
        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=600.0)) as http,
                http.stream(
                    "POST", f"{self.settings.llm.host}/api/pull", json={"model": name}
                ) as resp,
            ):
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise DownloadError(str(data["error"]))
                    total, done = data.get("total"), data.get("completed")
                    now = time.monotonic()
                    if total and done is not None and now - last >= 0.2:
                        last = now
                        await self.bus.publish(SetupProgress(key, name, done / MB, total / MB))
        except (httpx.HTTPError, DownloadError, ValueError) as err:
            log.warning("No se pudo descargar %s en Ollama: %s", name, err)
            await self.bus.publish(SetupProgress(key, name, 0, 0, True, str(err)))
            return False
        await self.bus.publish(SetupProgress(key, name, 1, 1, True))
        return True

    async def _scan(self) -> None:
        index = self.index()
        if index is None or self._scanning:
            return
        self._scanning = True
        await self._publish_status()
        try:
            await index.refresh()
        finally:
            self._scanning = False
        await self._publish_status()

    async def _forget(self, phrase: str) -> None:
        shortcuts = self.shortcuts()
        ok = shortcuts is not None and await asyncio.to_thread(shortcuts.forget, phrase)
        await self.bus.publish(SetupResult("forget_shortcut", ok))
        await self._publish_status()

    async def _clear(self, action: str, folder: Path) -> None:
        """A la papelera, nunca borrado permanente (SPEC sección 8)."""
        ok = await asyncio.to_thread(_to_recycle_bin, folder)
        await self.bus.publish(SetupResult(action, ok))
        await self._publish_status()

    # --- prueba del micrófono ---

    async def _start_mic(self) -> None:
        await self._stop_mic()
        self._mic = asyncio.create_task(self._mic_loop(), name="mic-test")

    async def _stop_mic(self) -> None:
        if self._mic is not None:
            self._mic.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mic
            self._mic = None
            await self.bus.publish(MicLevelChanged(0.0))

    async def _mic_loop(self) -> None:
        import numpy as np
        import sounddevice as sd

        from nyx.audio.devices import resolve

        level = [0.0]

        def callback(indata: Any, _frames: int, _time: Any, _status: Any) -> None:
            rms = float(np.sqrt(np.mean(np.square(indata, dtype=np.float64))))
            level[0] = max(rms, level[0] * 0.85)  # sube al momento y baja despacio

        device, extra = await asyncio.to_thread(resolve, "input", self.settings.audio.input_device)
        try:
            stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=16000,
                dtype="float32",
                callback=callback,
                extra_settings=extra,
            )
        except Exception as err:
            log.warning("No se pudo abrir el micrófono para la prueba: %s", err)
            await self.bus.publish(
                SetupResult("mic_test_start", False, "No se puede abrir el micrófono")
            )
            return
        with stream:
            end = time.monotonic() + MIC_MAX_S
            while time.monotonic() < end:
                await self.bus.publish(MicLevelChanged(min(1.0, level[0] * 4)))
                await asyncio.sleep(MIC_EVERY_S)
        await self.bus.publish(MicLevelChanged(0.0))


def _to_recycle_bin(folder: Path) -> bool:
    """La carpeta entera a la papelera (si tiene algo). False si no se pudo."""
    if not folder.exists() or not any(folder.iterdir()):
        return True
    try:
        from send2trash import send2trash

        send2trash(str(folder))
    except Exception as err:
        log.warning("No se pudo mandar %s a la papelera: %s", folder, err)
        return False
    return True


def _count(folder: Path, pattern: str) -> int:
    try:
        return sum(1 for _ in folder.rglob(pattern)) if folder.exists() else 0
    except OSError:
        return 0


def _everything_installed() -> bool:
    try:
        from nyx.winapi.search import everything_exe

        return everything_exe() is not None
    except Exception:
        return False
