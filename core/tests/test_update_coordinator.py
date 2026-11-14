"""Cuándo se aplica una actualización descargada (9.06; SPEC §15, pasos 3 a 5)."""

from __future__ import annotations

from typing import Any

import pytest

from nyx.bridge.protocol import UpdateMsg, client_adapter
from nyx.bus import EventBus
from nyx.events import ActionChosen, BubbleHidden, BubbleShown, UpdateApply, UpdateOffered
from nyx.settings.model import Settings
from nyx.update.coordinator import ASK_AGAIN_S, IDLE_FOR_AUTO_S, LATER, NOW, UPDATE
from nyx.update.coordinator import UpdateCoordinator as Coordinator
from nyx.update.moment import UpdateGate


class World:
    def __init__(self, mode: str) -> None:
        self.bus = EventBus()
        self.settings = Settings()
        self.settings.updates.mode = mode  # type: ignore[assignment]
        self.gate = UpdateGate()
        self.busy: str | None = None
        self.gate.add("pipeline", lambda: self.busy)
        self.now = 0.0
        self.idle = 0.0
        self.backups: list[str] = []
        self.seen: list[Any] = []

        async def on_any(e: Any) -> None:
            self.seen.append(e)

        for kind in (BubbleShown, BubbleHidden, UpdateApply):
            self.bus.subscribe(kind, on_any)
        self.c = Coordinator(
            self.bus,
            self.settings,
            self.gate,
            idle=lambda: self.idle,
            clock=lambda: self.now,
            backup=self.backups.append,
            poll_s=3600,  # las vueltas las da la prueba con step()
        )

    def bubbles(self) -> list[BubbleShown]:
        return [e for e in self.seen if isinstance(e, BubbleShown)]

    def applied(self) -> list[UpdateApply]:
        return [e for e in self.seen if isinstance(e, UpdateApply)]


async def test_ask_now_or_later() -> None:
    w = World("preguntar")
    w.busy = "una petición en curso"
    await w.bus.publish(UpdateOffered("1.4.0"))
    await w.c.step()
    assert w.bubbles() == []  # no es buen momento
    w.busy = None
    await w.c.step()
    asked = w.bubbles()[-1]
    assert asked.display == "Nyx 1.4.0 está lista" and "¿Ahora?" in (asked.secondary or "")
    assert [a.id for a in asked.actions] == [NOW, LATER]
    await w.c.step()
    assert len(w.bubbles()) == 1  # no insiste
    await w.bus.publish(ActionChosen(LATER))
    assert any(isinstance(e, BubbleHidden) for e in w.seen) and w.applied() == []
    w.now += ASK_AGAIN_S
    await w.c.step()
    assert len(w.bubbles()) == 2  # a las 4 h vuelve a preguntar
    await w.bus.publish(ActionChosen(NOW))
    assert w.backups == ["1.4.0"] and [a.version for a in w.applied()] == ["1.4.0"]
    w.c.close()


async def test_automatic_waits_for_an_idle_pc() -> None:
    w = World("automatico")
    await w.bus.publish(UpdateOffered("2.0.1"))
    await w.c.step()
    assert w.applied() == [] and w.bubbles() == []
    w.idle = IDLE_FOR_AUTO_S
    await w.c.step()
    assert [a.version for a in w.applied()] == ["2.0.1"]
    await w.c.step()
    assert len(w.applied()) == 1  # una sola vez
    w.c.close()


async def test_only_notify_never_applies_alone() -> None:
    w = World("avisar")
    w.idle = 10 * IDLE_FOR_AUTO_S
    await w.bus.publish(UpdateOffered("1.5.0"))
    await w.c.step()
    await w.c.step()
    assert len(w.bubbles()) == 1 and w.applied() == []
    assert [a.id for a in w.bubbles()[0].actions] == [UPDATE]
    await w.bus.publish(ActionChosen(UPDATE))
    assert [a.version for a in w.applied()] == ["1.5.0"]
    w.c.close()


def test_update_message_from_the_app() -> None:
    msg = client_adapter.validate_json('{"type": "update", "action": "ready", "version": "1.4.0"}')
    assert isinstance(msg, UpdateMsg) and msg.version == "1.4.0"
    with pytest.raises(ValueError):
        client_adapter.validate_json('{"type": "update", "action": "ready", "version": "1 4"}')
