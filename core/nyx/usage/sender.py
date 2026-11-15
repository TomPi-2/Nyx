r"""Envío de los datos de uso anónimos a Tepnyx (Supabase, esquema `nyx`; 2026-11-16).

Solo si el usuario lo ha permitido (`privacy.usage_data`, apagado por defecto) y si esta
versión de Nyx trae a dónde enviarlo. Una vez al día, los días ya terminados que falten
(como mucho los 7 últimos), con `nyx.report` en la base de datos de Tepnyx: la función valida
cada campo y guarda un informe por instalación y día (reenviar el mismo día lo sustituye).

- El identificador es aleatorio y cambia cada mes: deja contar «equipos al día» sin poder
  seguir a nadie.
- A dónde se envía: `NYX_USAGE_URL` y `NYX_USAGE_KEY` (desarrollo) o `uso.json` junto al
  núcleo, que pone `scripts/build-release.ps1` desde un archivo local fuera de git. La clave
  es la pública de Supabase («anon»): solo deja llamar a `nyx.report`.
- Sin conexión no pasa nada: se intenta en la siguiente vuelta.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from nyx.paths import local_dir
from nyx.usage.report import build
from nyx.usage.stats import UsageStats, folder

log = logging.getLogger(__name__)

#: Cada cuánto se mira si hay algo que enviar.
EVERY_S = 6 * 3600
#: Días hacia atrás que se intentan enviar.
MAX_DAYS = 7
TIMEOUT_S = 15.0


def endpoint() -> tuple[str, str] | None:
    """(dirección de Supabase, clave pública) o None si esta versión no envía nada."""
    url, key = os.environ.get("NYX_USAGE_URL", ""), os.environ.get("NYX_USAGE_KEY", "")
    if not (url and key):
        packaged = Path(__file__).resolve().parents[2] / "uso.json"
        try:
            data = json.loads(packaged.read_text(encoding="utf-8"))
            url, key = str(data.get("url", "")), str(data.get("key", ""))
        except OSError, ValueError:
            return None
    if not url.startswith("https://") or not key:
        return None
    return url.rstrip("/"), key


def install_id(root: Path | None = None, *, today: date | None = None) -> str:
    """Aleatorio y nuevo cada mes (`uso/id.json`): nunca deriva de nada del equipo."""
    root = root or folder()
    month = f"{today or date.today():%Y-%m}"
    path = root / "id.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("month") == month and isinstance(data.get("id"), str):
            return str(data["id"])
    except OSError, ValueError, AttributeError:
        pass
    new = secrets.token_urlsafe(18)
    try:
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"month": month, "id": new}), encoding="utf-8")
    except OSError:
        pass
    return new


class UsageSender:
    def __init__(
        self,
        stats: UsageStats,
        *,
        enabled: Callable[[], bool],
        llm_model: Callable[[], str],
        transport: httpx.AsyncBaseTransport | None = None,
        target: tuple[str, str] | None = None,
        actions: Path | None = None,
        hw: dict[str, str] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.stats = stats
        self._enabled = enabled
        self._llm_model = llm_model
        self._transport = transport
        self._target = target if target is not None else endpoint()
        self._actions = actions or local_dir() / "actions"
        self._hw = hw
        self._today = today
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._target is None:
            log.info("Datos de uso: esta versión no los envía a ningún sitio")
            return
        self._task = asyncio.create_task(self._loop(), name="usage-sender")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(60)  # que arranque Nyx primero
        while True:
            try:
                await self.send_pending()
            except Exception:
                log.warning("Datos de uso: fallo al enviar", exc_info=True)
            await asyncio.sleep(EVERY_S)

    async def send_pending(self) -> int:
        """Envía los días terminados que falten. Devuelve cuántos ha enviado."""
        if self._target is None or not self._enabled():
            return 0
        sent_path = self.stats.root / "enviados.json"
        try:
            sent = set(json.loads(sent_path.read_text(encoding="utf-8")))
        except OSError, ValueError, TypeError:
            sent = set()
        today = self._today()
        done = 0
        for back in range(MAX_DAYS, 0, -1):
            day = today - timedelta(days=back)
            key = f"{day:%Y-%m-%d}"
            counts = self.stats.day(day)
            if key in sent or counts is None:
                continue
            report = await asyncio.to_thread(
                build,
                install_id(self.stats.root, today=day),
                day,
                counts,
                self._actions / f"{key}.jsonl",
                self._llm_model(),
                self._hw,
            )
            if await self._post(report.model_dump(mode="json")):
                sent.add(key)
                done += 1
        keep = sorted(k for k in sent if k >= f"{today - timedelta(days=MAX_DAYS + 1):%Y-%m-%d}")
        with contextlib.suppress(OSError):
            sent_path.write_text(json.dumps(keep), encoding="utf-8")
        if done:
            log.info("Datos de uso: %d días enviados", done)
        return done

    async def _post(self, report: dict[str, Any]) -> bool:
        assert self._target is not None
        url, key = self._target
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Todo lo de Nyx está en su propio esquema de la base de datos de Tepnyx.
            "Content-Profile": "nyx",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self._transport) as http:
                resp = await http.post(
                    f"{url}/rest/v1/rpc/report", headers=headers, json={"p_report": report}
                )
        except httpx.HTTPError as e:
            log.info("Datos de uso: sin conexión (%s)", e)
            return False
        if resp.status_code >= 300:
            log.warning("Datos de uso: el servidor dice %d", resp.status_code)
            return False
        return True
