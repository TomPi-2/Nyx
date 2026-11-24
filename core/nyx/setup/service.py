"""Asistente de primer arranque y Ajustes → Cerebro, Caché, Ayuda y Privacidad (fase 5d‑2).

Lo que la interfaz puede pedir (SetupRequested) y lo que contesta:
- «status»: estado completo (SetupStatusChanged): modelos que faltan, Ollama, whisper-server,
  la caché del sistema, los atajos aprendidos y las grabaciones guardadas.
- «download»: descarga lo que falte del catálogo (con su huella SHA-256) y el modelo de Ollama
  configurado, con progreso real (SetupProgress).
- «scan»: vuelve a escanear aplicaciones y carpetas.
- «forget_shortcut»: olvida un atajo aprendido (arg = la frase).
- «forget_all_shortcuts»: olvida todos los atajos aprendidos.
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

from nyx import errors
from nyx.brain.shortcuts import ShortcutStore
from nyx.bus import EventBus
from nyx.events import (
    MicLevelChanged,
    SettingsRequested,
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
from nyx.setup import brain, everything, hardware, ollama

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
        self._failed_code = errors.DOWNLOAD_FAILED  # el de la última descarga que falló
        self._scanning = False
        self._mic: asyncio.Task[None] | None = None
        self._installing = False
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
            # v13: tarjeta gráfica, modelos posibles y el recomendado; estado de Everything.
            "llm": await asyncio.to_thread(hardware.llm_status),
            "everything": await asyncio.to_thread(everything.status),
            "installing_everything": self._installing,
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
            ]
            + [
                # Planes de varios pasos (7.16): se olvidan igual que un atajo.
                {"phrase": phrase, "tool": "plan", "steps": steps, "uses": uses}
                for phrase, steps, uses in shortcuts.all_plans()
            ],
            "samples": _count(self.root.joinpath(*SAMPLES_DIR), "*.wav"),
            "activations": _count(self.root / "activaciones", "*.jsonl"),
        }

    async def _ollama_status(self) -> dict[str, Any]:
        wanted = self.settings.llm.model
        if self.settings.llm.engine == "llamacpp":
            # Sin Ollama (C5.1): «en marcha» siempre (lo lanza el núcleo) y el modelo es el
            # archivo del cerebro. Mismas claves para que la interfaz no cambie.
            path = self.settings.llm.model_path or brain.gguf_path()
            has = await asyncio.to_thread(path.is_file)
            return {
                "running": True,
                "models": [wanted] if has else [],
                "wanted": wanted,
                "has_wanted": has,
            }
        try:
            async with httpx.AsyncClient(timeout=1.5) as http:
                resp = await http.get(f"{self.settings.llm.host}/api/tags")
                resp.raise_for_status()
                names = sorted(str(m["name"]) for m in resp.json().get("models", []))
        except httpx.HTTPError, ValueError, KeyError:
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
            "forget_all_shortcuts": self._forget_all,
            "mic_test_start": self._start_mic,
            "mic_test_stop": self._stop_mic,
            "clear_samples": lambda: self._clear("clear_samples", self.root.joinpath(*SAMPLES_DIR)),
            "clear_activations": lambda: self._clear(
                "clear_activations", self.root / "activaciones"
            ),
            "install_everything": self._install_everything,
            "start_everything": self._start_everything,
        }
        handler = handlers.get(event.action)
        if handler is not None:
            await handler()

    async def _download(self) -> None:
        if self._downloading:
            return
        self._downloading = True
        self._failed_code = errors.DOWNLOAD_FAILED
        await self._publish_status()
        loop = asyncio.get_running_loop()
        failed: list[str] = []
        try:
            for model in [m for m in CATALOG if not is_present(m)]:
                try:
                    await asyncio.to_thread(self._download_one, model, loop)
                except (DownloadError, OSError) as err:
                    code = err.code if isinstance(err, DownloadError) else errors.DOWNLOAD_FAILED
                    log.warning("%s: no se pudo descargar %s: %s", code, model.filename, err)
                    failed.append(model.filename)
                    self._failed_code = code
                    text = errors.coded(code, f"No he podido descargar {model.filename}")
                    await self.bus.publish(
                        SetupProgress(model.key, model.filename, 0, model.size_mb, True, text)
                    )
            pull = self._brain_file if self.settings.llm.engine == "llamacpp" else self._pull_ollama
            if not await pull():
                failed.append(self.settings.llm.model)
        finally:
            self._downloading = False
        message = (
            errors.coded(self._failed_code, "No se pudo descargar: " + ", ".join(failed))
            if failed
            else None
        )
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

    async def _ensure_ollama(self) -> bool:
        """Ollama oficial si falta (9.08): se instala con winget y se abre. El panel de
        descargas lo enseña como «Ollama» mientras tanto."""
        if (await self._ollama_status())["running"]:
            return True
        key, label = "ollama-app", "Ollama"
        await self.bus.publish(SetupProgress(key, label, 0, 1))
        error = None
        if not ollama.installed() and not await ollama.install():
            error = errors.coded(errors.OLLAMA_INSTALL, "No he podido instalar Ollama")
        elif not await ollama.start(self.settings.llm.host):
            error = errors.coded(errors.OLLAMA_START, "Ollama no responde")
        if error is not None:
            self._failed_code = errors.code_of(error) or errors.OLLAMA_INSTALL
            log.warning("%s", error)
        await self.bus.publish(SetupProgress(key, label, 0 if error else 1, 1, True, error))
        return error is None

    async def _nyx_brain(self) -> bool:
        """El cerebro entrenado de Nyx (9.08b) en vez del Qwen de serie: si sale, pasa a ser el
        que usa Nyx. Si no (sin publicar, sin red…), False y se baja el de siempre."""
        data = brain.manifest()
        if data is None:
            return False
        name = str(data["name"])
        key = f"ollama:{name}"

        async def progress(done: float, total: float) -> None:
            await self.bus.publish(SetupProgress(key, name, done, total))

        try:
            await brain.ensure(self.settings.llm.host, progress)
        except brain.BrainError as err:
            log.info("Cerebro de Nyx no disponible (%s): bajo %s", err, self.settings.llm.model)
            # La barra del cerebro de Nyx se quita: la sustituye la del modelo de siempre.
            await self.bus.publish(SetupProgress(key, name, 0, 0, True))
            return False
        # Por el mismo camino que Ajustes (lo guarda y avisa a las ventanas).
        await self.bus.publish(SettingsRequested({"llm": {"model": name}}))
        await self.bus.publish(SetupProgress(key, name, 1, 1, True))
        return True

    async def _brain_file(self) -> bool:
        """Con llama-server (C5.1): el cerebro de Nyx en un `.gguf`, sin Ollama."""
        if self.settings.llm.model_path is not None:
            return self.settings.llm.model_path.is_file()  # uno propio: no se baja nada
        data = brain.manifest()
        name = str(data["name"]) if data else self.settings.llm.model
        key = f"cerebro:{name}"

        async def progress(done: float, total: float) -> None:
            await self.bus.publish(SetupProgress(key, name, done, total))

        try:
            await brain.ensure_file(progress)
        except brain.BrainError as err:
            text = (
                str(err) if errors.code_of(str(err)) else errors.coded(errors.BRAIN_PULL, str(err))
            )
            self._failed_code = errors.code_of(text) or errors.BRAIN_PULL
            log.warning("%s", text)
            await self.bus.publish(SetupProgress(key, name, 0, 1, True, text))
            return False
        await self.bus.publish(SetupProgress(key, name, 1, 1, True))
        return True

    async def _pull_ollama(self) -> bool:
        """Descarga el modelo de Ollama configurado si no lo tiene (instala Ollama si falta)."""
        if not await self._ensure_ollama():
            return False
        status = await self._ollama_status()
        if not status["running"] or status["has_wanted"]:
            return True
        if self.settings.llm.model == hardware.LLM_CHOICES[0].id and await self._nyx_brain():
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
            log.warning("%s: no se pudo descargar %s en Ollama: %s", errors.BRAIN_PULL, name, err)
            self._failed_code = errors.BRAIN_PULL
            text = errors.coded(errors.BRAIN_PULL, "No he podido bajar mi cerebro")
            await self.bus.publish(SetupProgress(key, name, 0, 0, True, text))
            return False
        await self.bus.publish(SetupProgress(key, name, 1, 1, True))
        return True

    async def _install_everything(self) -> None:
        """Opcional: solo si el usuario lo marca en el asistente (o lo pide en Caché)."""
        if self._installing:
            return
        self._installing = True
        await self._publish_status()
        try:
            ok = await everything.install()
        finally:
            self._installing = False
        message = None if ok else "No se pudo instalar Everything (¿se canceló el permiso?)"
        await self.bus.publish(SetupResult("install_everything", ok, message))
        await self._publish_status()

    async def _start_everything(self) -> None:
        ok = await asyncio.to_thread(everything.start)
        await self.bus.publish(SetupResult("start_everything", ok))
        await asyncio.sleep(1.0)  # que le dé tiempo a arrancar antes de mirar
        await self._publish_status()

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

    async def _forget_all(self) -> None:
        shortcuts = self.shortcuts()
        forgotten = 0 if shortcuts is None else await asyncio.to_thread(shortcuts.forget_all)
        log.info("Atajos olvidados: %d", forgotten)
        await self.bus.publish(SetupResult("forget_all_shortcuts", shortcuts is not None))
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
