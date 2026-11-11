import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from nyx.alarms.scheduler import AlarmFired, AlarmScheduler, AlarmsMissed
from nyx.alarms.spoken import (
    fired_text,
    missed_text,
    next_occurrence,
    short_duration,
    spoken_duration,
)
from nyx.alarms.store import Alarm, AlarmStore
from nyx.bus import EventBus
from nyx.executor import Executor, ToolCall
from nyx.tools.base import ToolContext
from nyx.tools.registry import default_registry

# Lunes 9 de noviembre de 2026, 18:00 (hora local).
NOW = datetime(2026, 11, 9, 18, 0).timestamp()


class Clock:
    def __init__(self, t: float = NOW) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def collect(bus: EventBus) -> list[object]:
    seen: list[object] = []

    async def keep(e: object) -> None:
        seen.append(e)

    bus.subscribe(AlarmFired, keep)
    bus.subscribe(AlarmsMissed, keep)
    return seen


def test_store_persists_and_states(tmp_path: Path) -> None:
    store = AlarmStore(tmp_path / "a.db")
    a = store.add("alarm", NOW + 60, label="llamar")
    b = store.add("timer", NOW + 30, duration_s=30)
    store.close()
    store = AlarmStore(tmp_path / "a.db")  # tras reiniciar siguen ahí, en orden
    assert [x.id for x in store.pending()] == [b.id, a.id]
    assert store.cancel(a.id) and not store.cancel(a.id)
    assert store.mark_fired(b.id) and not store.mark_fired(b.id)
    assert store.pending() == []


async def test_scheduler_fires_when_due(tmp_path: Path) -> None:
    bus, clock = EventBus(), Clock()
    seen = collect(bus)
    sched = AlarmScheduler(AlarmStore(tmp_path / "a.db"), bus, clock)
    timer = sched.add("timer", NOW + 300, duration_s=300)
    assert await sched.fire_due() == NOW + 300 and seen == []
    clock.t += 300
    assert await sched.fire_due() is None
    assert seen == [AlarmFired(timer)]
    assert await sched.fire_due() is None and len(seen) == 1  # solo una vez


async def test_missed_alarms_are_announced_once(tmp_path: Path) -> None:
    store = AlarmStore(tmp_path / "a.db")
    old1 = store.add("alarm", NOW - 3600)
    old2 = store.add("timer", NOW - 600, duration_s=60)
    late = store.add("alarm", NOW - 30)  # poco retraso: suena normal
    bus, clock = EventBus(), Clock()
    seen = collect(bus)
    sched = AlarmScheduler(store, bus, clock)
    await sched.start()
    await asyncio.sleep(0.05)
    await sched.close()
    assert seen[0] == AlarmsMissed((old1, old2))
    assert seen[1:] == [AlarmFired(late)]
    assert store.pending() == []


async def test_loop_wakes_up_for_a_new_short_timer(tmp_path: Path) -> None:
    bus = EventBus()
    seen = collect(bus)
    sched = AlarmScheduler(AlarmStore(tmp_path / "a.db"), bus)
    await sched.start()
    sched.add("timer", sched.clock() + 0.1, duration_s=1)
    for _ in range(40):
        if seen:
            break
        await asyncio.sleep(0.05)
    await sched.close()
    assert len(seen) == 1 and isinstance(seen[0], AlarmFired)


def test_durations_and_texts() -> None:
    assert short_duration(90 * 60) == "1 h 30 min"
    assert short_duration(45) == "45 s"
    assert spoken_duration(60) == "1 minuto"
    assert spoken_duration(3600 + 120 + 5) == "1 hora, 2 minutos y 5 segundos"
    now = datetime(2026, 11, 9, 18, 0)
    assert next_occurrence(19, 30, now) == datetime(2026, 11, 9, 19, 30)
    assert next_occurrence(7, 0, now) == datetime(2026, 11, 10, 7, 0)  # ya pasó: mañana
    assert next_occurrence(19, 30, now, tomorrow=True) == datetime(2026, 11, 10, 19, 30)
    alarm = Alarm("x", "alarm", datetime(2026, 11, 9, 10, 50).timestamp())
    assert fired_text(alarm) == ("10:50", "alarma", "Son las 10:50.")
    timer = Alarm("y", "timer", NOW, duration_s=300)
    assert fired_text(timer)[2] == "Se acabó el temporizador de 5 minutos."
    assert missed_text([alarm, timer]) == (
        "Mientras estaba apagado",
        "alarma de las 10:50 (y 1 más)",
    )


# --- herramientas a través del ejecutor ---


@pytest.fixture
def sched(tmp_path: Path) -> AlarmScheduler:
    return AlarmScheduler(AlarmStore(tmp_path / "a.db"), EventBus(), Clock())


def executor(ctx: ToolContext, sched: AlarmScheduler) -> Executor:
    ctx.alarms = sched
    return Executor(default_registry(), ctx)


async def test_set_timer_and_undo(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    result = await ex.run(ToolCall("set_timer", {"minutes": 5, "label": "la pizza"}))
    assert result.ok and result.display == "Temporizador 5 min"
    assert result.secondary == "suena a las 18:05 · la pizza"
    assert [a.due for a in sched.pending()] == [NOW + 300]
    assert (await ex.run(ToolCall("undo"))).ok
    assert sched.pending() == []


async def test_set_alarm_today_or_tomorrow(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    later = await ex.run(ToolCall("set_alarm", {"time": "19:30"}))
    assert later.display == "Alarma 19:30" and later.secondary == "hoy"
    passed = await ex.run(ToolCall("set_alarm", {"time": "7:00", "label": "gimnasio"}))
    assert passed.display == "Recordatorio 07:00"
    assert passed.secondary == "mañana · gimnasio"
    assert len(sched.pending()) == 2


def test_invalid_alarm_params_are_reported(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    assert "time" in ex.check([ToolCall("set_alarm", {"time": "25:00"})])
    assert ex.check([ToolCall("set_timer", {})])


# --- 6.03: ver y quitar alarmas (antes el LLM decía «no tienes» sin mirar) ---


async def test_list_alarms_says_what_is_pending(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    empty = await ex.run(ToolCall("list_alarms"))
    assert empty.ok and empty.message == "No tienes alarmas ni temporizadores"
    await ex.run(ToolCall("set_timer", {"minutes": 5}))
    await ex.run(ToolCall("set_alarm", {"time": "23:30", "label": "llamar a mamá"}))
    listed = await ex.run(ToolCall("list_alarms"))
    assert listed.message.startswith("2 pendientes: temporizador de 5 minutos: quedan 5 minutos")
    assert "recordatorio a las 23:30" in listed.message and "«llamar a mamá»" in listed.message
    assert listed.display == "2 pendientes"


async def test_cancel_alarm_by_time_label_or_kind(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    await ex.run(ToolCall("set_alarm", {"time": "07:00"}))
    await ex.run(ToolCall("set_alarm", {"time": "23:30", "label": "llamar a mamá"}))
    await ex.run(ToolCall("set_timer", {"minutes": 5}))
    which = await ex.run(ToolCall("cancel_alarm"))  # hay tres: hay que decir cuál
    assert not which.ok and which.message == "¿Cuál quito?"
    assert (await ex.run(ToolCall("cancel_alarm", {"which": "7"}))).ok
    assert (await ex.run(ToolCall("cancel_alarm", {"which": "mamá"}))).ok
    assert (await ex.run(ToolCall("cancel_alarm", {"which": "el temporizador"}))).ok
    assert sched.pending() == []
    nothing = await ex.run(ToolCall("cancel_alarm"))
    assert not nothing.ok and nothing.message == "No tienes alarmas ni temporizadores"


async def test_cancel_all(ctx: ToolContext, sched: AlarmScheduler) -> None:
    ex = executor(ctx, sched)
    await ex.run(ToolCall("set_alarm", {"time": "07:00"}))
    await ex.run(ToolCall("set_alarm", {"time": "08:00"}))
    result = await ex.run(ToolCall("cancel_alarm", {"which": "todas"}))
    assert result.ok and result.display == "2 quitadas" and sched.pending() == []
