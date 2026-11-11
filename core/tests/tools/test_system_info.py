from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psutil

from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.system_info import SystemInfo, SystemInfoParams


@dataclass
class _Battery:
    percent: float
    secsleft: int
    power_plugged: bool


@dataclass
class _Mem:
    used: int
    total: int
    percent: float


@dataclass
class _Part:
    device: str
    mountpoint: str
    fstype: str = "NTFS"
    opts: str = "rw,fixed"


@dataclass
class _Usage:
    free: int
    total: int


@dataclass
class _MemInfo:
    rss: int


class _Proc:
    def __init__(self, pid: int, name: str, cpu: float, rss: int) -> None:
        self.info: dict[str, Any] = {
            "pid": pid,
            "name": name,
            "memory_info": _MemInfo(rss=rss),
        }
        self._cpu = cpu

    def cpu_percent(self, interval: float | None = None) -> float:
        return self._cpu

    def memory_info(self) -> _MemInfo:
        return _MemInfo(rss=self.info["memory_info"].rss)


class _FakePsutil:
    def __init__(
        self,
        *,
        battery: _Battery | None = None,
        cpu: float = 23.6,
        mem: _Mem | None = None,
        partitions: list[_Part] | None = None,
        usages: dict[str, _Usage] | None = None,
        procs: list[_Proc] | None = None,
        cpus: int = 1,
    ) -> None:
        self._battery = battery
        self._cpu = cpu
        self._mem = mem or _Mem(used=11 * 1024**3, total=32 * 1024**3, percent=34.4)
        self._partitions = (
            partitions if partitions is not None else [_Part(device="C:\\", mountpoint="C:\\")]
        )
        self._usages = (
            usages
            if usages is not None
            else {"C:\\": _Usage(free=120 * 1024**3, total=500 * 1024**3)}
        )
        self._procs = procs or []
        self._cpus = cpus

    def sensors_battery(self) -> _Battery | None:
        return self._battery

    def cpu_percent(self, interval: float | None = None) -> float:
        return self._cpu

    def virtual_memory(self) -> _Mem:
        return self._mem

    def disk_partitions(self, all: bool = False) -> list[_Part]:
        return self._partitions

    def disk_usage(self, mountpoint: str) -> _Usage:
        if mountpoint not in self._usages:
            raise OSError("unidad no disponible")
        return self._usages[mountpoint]

    def process_iter(self, attrs: list[str] | None = None) -> list[_Proc]:
        return self._procs

    def cpu_count(self, logical: bool = True) -> int:
        return self._cpus


def test_metadata() -> None:
    tool = SystemInfo()
    assert tool.name == "system_info"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.ALLOWED
    assert tool.category is Category.SYSTEM
    assert tool.observe is True


async def test_battery_unplugged_with_remaining_time(ctx: ToolContext) -> None:
    ps = _FakePsutil(battery=_Battery(percent=74.4, secsleft=5400, power_plugged=False))
    tool = SystemInfo(ps=ps, cpu_interval=0.0)
    res = await tool.run(SystemInfoParams(what="battery"), ctx)
    assert res.ok
    assert res.display == "74 %"
    assert "74 % de batería" in res.message
    assert "desenchufado" in res.message
    assert "1 h y 30 min" in res.message


async def test_battery_plugged_and_desktop_without_battery(ctx: ToolContext) -> None:
    plugged = SystemInfo(
        ps=_FakePsutil(battery=_Battery(percent=98.2, secsleft=-2, power_plugged=True)),
        cpu_interval=0.0,
    )
    res_plugged = await plugged.run(SystemInfoParams(what="battery"), ctx)
    assert res_plugged.ok
    assert res_plugged.display == "98 %"
    assert "enchufado" in res_plugged.message

    desktop = SystemInfo(ps=_FakePsutil(battery=None), cpu_interval=0.0)
    res_desktop = await desktop.run(SystemInfoParams(what="battery"), ctx)
    assert res_desktop.ok
    assert res_desktop.display == "Sin batería"
    assert "no tiene batería" in res_desktop.message


async def test_cpu_and_ram(ctx: ToolContext) -> None:
    ps = _FakePsutil(
        cpu=23.7,
        mem=_Mem(used=int(11.4 * 1024**3), total=32 * 1024**3, percent=35.6),
    )
    tool = SystemInfo(ps=ps, cpu_interval=0.0)

    cpu_res = await tool.run(SystemInfoParams(what="cpu"), ctx)
    assert cpu_res.ok
    assert cpu_res.display == "CPU al 24 %"
    assert cpu_res.message == "El uso de CPU está al 24 %."

    ram_res = await tool.run(SystemInfoParams(what="ram"), ctx)
    assert ram_res.ok
    assert ram_res.display == "11 / 32 GB"
    assert ram_res.message == "Estás usando 11 GB de 32 GB de RAM (36 %)."


async def test_disk_single_and_multiple_units(ctx: ToolContext) -> None:
    ps_single = _FakePsutil(
        partitions=[
            _Part(device="C:\\", mountpoint="C:\\"),
            _Part(device="E:\\", mountpoint="E:\\", fstype="", opts="cdrom"),
            _Part(device="F:\\", mountpoint="F:\\"),
        ],
        usages={"C:\\": _Usage(free=120 * 1024**3, total=500 * 1024**3)},
    )
    res_single = await SystemInfo(ps=ps_single, cpu_interval=0.0).run(
        SystemInfoParams(what="disk"), ctx
    )
    assert res_single.ok
    assert res_single.message == "Te quedan 120 GB libres en C: (de 500 GB)."
    assert res_single.display == "120 GB libres"

    ps_multi = _FakePsutil(
        partitions=[
            _Part(device="C:\\", mountpoint="C:\\"),
            _Part(device="D:\\", mountpoint="D:\\"),
        ],
        usages={
            "C:\\": _Usage(free=120 * 1024**3, total=500 * 1024**3),
            "D:\\": _Usage(free=340 * 1024**3, total=1000 * 1024**3),
        },
    )
    res_multi = await SystemInfo(ps=ps_multi, cpu_interval=0.0).run(
        SystemInfoParams(what="disk"), ctx
    )
    assert res_multi.ok
    assert (
        res_multi.message
        == "Te quedan 120 GB libres en C: (de 500 GB) y 340 GB libres en D: (de 1000 GB)."
    )


async def test_top_aggregates_and_ignores_system_idle(ctx: ToolContext) -> None:
    ps = _FakePsutil(
        procs=[
            _Proc(0, "System Idle Process", cpu=95.0, rss=0),
            _Proc(4, "System", cpu=2.0, rss=100 * 1024**2),
            _Proc(101, "chrome.exe", cpu=15.0, rss=500 * 1024**2),
            _Proc(102, "chrome.exe", cpu=10.0, rss=400 * 1024**2),
            _Proc(205, "Blender.exe", cpu=5.0, rss=3 * 1024**3),
        ],
        cpus=1,
    )
    res = await SystemInfo(ps=ps, cpu_interval=0.0).run(SystemInfoParams(what="top"), ctx)
    assert res.ok
    assert (
        res.message
        == "El proceso que más CPU usa es chrome (25 %) y el que más RAM usa es Blender (3 GB)."
    )

    ps_same = _FakePsutil(
        procs=[_Proc(300, "Spotify.exe", cpu=18.0, rss=450 * 1024**2)],
        cpus=1,
    )
    res_same = await SystemInfo(ps=ps_same, cpu_interval=0.0).run(SystemInfoParams(what="top"), ctx)
    assert res_same.ok
    assert (
        res_same.message
        == "El proceso que más recursos usa es Spotify: 18 % de CPU y 450 MB de RAM."
    )


async def test_errors_are_handled_cleanly(ctx: ToolContext) -> None:
    empty_disk = SystemInfo(ps=_FakePsutil(partitions=[], usages={}), cpu_interval=0.0)
    assert not (await empty_disk.run(SystemInfoParams(what="disk"), ctx)).ok

    empty_top = SystemInfo(ps=_FakePsutil(procs=[]), cpu_interval=0.0)
    assert not (await empty_top.run(SystemInfoParams(what="top"), ctx)).ok

    class _BrokenPs:
        def cpu_percent(self, interval: float | None = None) -> float:
            raise psutil.Error("fallo interno")

    broken = SystemInfo(ps=_BrokenPs(), cpu_interval=0.0)
    res = await broken.run(SystemInfoParams(what="cpu"), ctx)
    assert not res.ok
    assert res.message == "No he podido consultar el estado del equipo"
