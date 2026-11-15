"""Datos de uso anónimos (SPEC §8; 2026-11-16): cuentas, informe y envío."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from nyx.usage.report import Report, build, spread, tool_use
from nyx.usage.sender import UsageSender, install_id
from nyx.usage.stats import UsageStats

DAY = date(2026, 11, 15)
HW = {"gpu_vendor": "amd", "vram_gb": "8-12", "ram_gb": "32+"}


def stats_for(tmp: Path, day: date = DAY) -> UsageStats:
    return UsageStats(tmp / "uso", today=lambda: day)


def test_counts_only_numbers(tmp_path: Path) -> None:
    stats = stats_for(tmp_path)
    stats.request("router", 12)
    stats.request("llm", 950, 380)
    stats.request("inventado", 1)  # caminos desconocidos no se apuntan
    stats.activation(True)
    stats.activation(False)
    stats.error("D-201")
    stats.error("llm_timeout ¡raro!")
    data = stats.day(DAY)
    assert data is not None
    assert data["requests"] == {"router": 1, "llm": 1}
    assert data["latency_ms"] == {"router": [12], "llm": [950]}
    assert data["first_token_ms"] == [380]
    assert data["activations"] == {"ok": 1, "false": 1}
    assert data["errors"] == {"D-201": 1, "llm_timeoutraro": 1}  # solo letras, cifras, - y _


def test_tool_use_keeps_names_and_results_only(tmp_path: Path) -> None:
    actions = tmp_path / "2026-11-15.jsonl"
    rows = [
        {"tool": "open_app", "ok": True, "phrase": "abre Spotify", "params": {"name": "Spotify"}},
        {"tool": "open_app", "ok": False},
        {"tool": "system_power", "decision": "cancelled", "ok": False},
        {"tool": "../raro", "ok": True},
    ]
    actions.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    used = tool_use(actions)
    assert set(used) == {"open_app", "system_power"}
    assert used["open_app"].ok == 1 and used["open_app"].fail == 1
    assert used["system_power"].cancelled == 1
    assert "Spotify" not in json.dumps({k: v.model_dump() for k, v in used.items()})


def test_report_never_carries_anything_else(tmp_path: Path) -> None:
    stats = stats_for(tmp_path)
    for ms in range(10, 110, 10):
        stats.request("router", ms)
    counts = stats.day(DAY)
    assert counts is not None
    counts["frase"] = "abre mis fotos privadas"  # aunque se colara en las cuentas…
    report = build("abcdefgh123", DAY, counts, tmp_path / "nada.jsonl", "nyx-r2:7b", HW)
    sent = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert "privadas" not in sent  # …no sale
    assert report.latency_ms["router"].p50 == 55 and report.latency_ms["router"].n == 10
    with pytest.raises(ValidationError):
        Report.model_validate({**report.model_dump(), "ciudad": "Valencia"})


def test_spread() -> None:
    assert spread([]) is None
    s = spread([100, 200, 300, 400, 1000])
    assert s is not None and s.p50 == 300 and s.p90 == 1000


def test_install_id_changes_every_month(tmp_path: Path) -> None:
    a = install_id(tmp_path, today=date(2026, 11, 1))
    assert a == install_id(tmp_path, today=date(2026, 11, 30))
    assert a != install_id(tmp_path, today=date(2026, 12, 1))


def sender(
    tmp: Path, server: Any, *, enabled: bool = True, today: date = date(2026, 11, 16)
) -> UsageSender:
    return UsageSender(
        stats_for(tmp),
        enabled=lambda: enabled,
        llm_model=lambda: "nyx-r2:7b",
        transport=httpx.MockTransport(server),
        target=("https://ejemplo.supabase.co", "clave-anon"),
        actions=tmp / "actions",
        hw=HW,
        today=lambda: today,
    )


async def test_sends_finished_days_once_to_the_nyx_schema(tmp_path: Path) -> None:
    got: list[httpx.Request] = []

    def server(request: httpx.Request) -> httpx.Response:
        got.append(request)
        return httpx.Response(204)

    stats_for(tmp_path).request("router", 10)  # el 15: ya ha terminado
    stats_for(tmp_path, date(2026, 11, 16)).request("router", 10)  # hoy: aún no
    s = sender(tmp_path, server)
    assert await s.send_pending() == 1
    (req,) = got
    assert req.url.path == "/rest/v1/rpc/report"
    assert req.headers["Content-Profile"] == "nyx"
    body = json.loads(req.content)
    assert body["p_report"]["day"] == "2026-11-15"
    assert await s.send_pending() == 0  # no se repite


async def test_nothing_without_permission(tmp_path: Path) -> None:
    def server(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería enviar nada")

    stats_for(tmp_path).request("router", 10)
    assert await sender(tmp_path, server, enabled=False).send_pending() == 0


async def test_a_failed_send_is_retried_later(tmp_path: Path) -> None:
    answers = [httpx.Response(500), httpx.Response(204)]

    def server(request: httpx.Request) -> httpx.Response:
        return answers.pop(0)

    stats_for(tmp_path).request("llm", 900)
    s = sender(tmp_path, server)
    assert await s.send_pending() == 0
    assert await s.send_pending() == 1
