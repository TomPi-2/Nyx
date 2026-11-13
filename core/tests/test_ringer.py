import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

import numpy as np
import numpy.typing as npt

from nyx.alarms.ringer import AlarmRinger, chime
from nyx.alarms.scheduler import AlarmFired, AlarmsMissed
from nyx.alarms.store import Alarm
from nyx.bus import EventBus
from nyx.events import ActionChosen, BubbleHidden, BubbleShown, NyxState, StateChanged

ALARM = Alarm("a1", "alarm", datetime(2026, 11, 9, 10, 50).timestamp())


class FakePlayer:
    sample_rate = 24000

    def __init__(self) -> None:
        self.played: list[int] = []
        self.cleared = 0

    def enqueue(self, samples: npt.NDArray[np.float32]) -> None:
        self.played.append(len(samples))

    def clear(self) -> None:
        self.cleared += 1

    async def drain(self) -> None:
        pass


class FakeTTS:
    def __init__(self) -> None:
        self.said: list[str] = []

    async def load(self) -> None:
        pass

    async def synthesize(self, text: str) -> npt.NDArray[np.float32]:
        self.said.append(text)
        return np.zeros(10, dtype=np.float32)

    async def stream(self, text: str) -> AsyncIterator[npt.NDArray[np.float32]]:
        yield await self.synthesize(text)


def setup(**kw: float) -> tuple[EventBus, AlarmRinger, FakePlayer, FakeTTS, list[object]]:
    bus, player, tts = EventBus(), FakePlayer(), FakeTTS()
    seen: list[object] = []

    async def keep(e: object) -> None:
        seen.append(e)

    bus.subscribe(BubbleShown, keep)
    bus.subscribe(BubbleHidden, keep)
    ringer = AlarmRinger(bus, tts=tts, player=player, chime_every_s=0.01, **kw)  # type: ignore[arg-type]
    return bus, ringer, player, tts, seen


async def test_rings_speaks_and_stops_with_the_button() -> None:
    bus, ringer, player, tts, seen = setup()
    await bus.publish(AlarmFired(ALARM))
    await asyncio.sleep(0.05)
    bubble = seen[0]
    assert isinstance(bubble, BubbleShown) and bubble.alert
    assert (bubble.display, bubble.actions[0].label) == ("10:50", "Parar")
    assert ringer.ringing and len(player.played) >= 2  # timbre repetido
    assert tts.said == ["Son las 10:50."]  # la frase, una sola vez
    await bus.publish(ActionChosen(bubble.actions[0].id))
    assert not ringer.ringing and isinstance(seen[-1], BubbleHidden)
    assert ringer.swallow("Para.")  # justo después, «para» es para la alarma
    assert not ringer.swallow("abre Spotify")
    await ringer.close()


async def test_talking_to_nyx_silences_it() -> None:
    bus, ringer, _, _, _ = setup()
    await bus.publish(AlarmFired(ALARM))
    await bus.publish(StateChanged(NyxState.LISTENING))
    assert not ringer.ringing
    await ringer.close()


async def test_stops_by_itself_after_ring_time() -> None:
    bus, ringer, _, _, seen = setup(ring_s=0.05)
    await bus.publish(AlarmFired(ALARM))
    await asyncio.sleep(0.2)
    assert not ringer.ringing and isinstance(seen[-1], BubbleHidden)
    await ringer.close()


async def test_missed_alarms_single_notice() -> None:
    bus, ringer, player, _, seen = setup()
    await bus.publish(AlarmsMissed((ALARM,)))
    bubble = seen[0]
    assert isinstance(bubble, BubbleShown) and bubble.alert
    assert bubble.display == "Mientras estaba apagado."
    assert len(player.played) == 1 and not ringer.ringing
    await ringer.close()


def test_chime_is_quiet_and_short() -> None:
    sound = chime(24000)
    assert sound.dtype == np.float32 and len(sound) == 24000
    assert float(np.abs(sound).max()) < 0.5
