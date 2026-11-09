import asyncio
import sys

import pytest

from nyx import main


async def test_exits_when_parent_dies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "PARENT_POLL_S", 0.05)
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(0.3)"
    )
    stop = asyncio.Event()
    await asyncio.wait_for(main._watch_parent_pid(child.pid, stop), timeout=5)
    assert stop.is_set()
    await child.wait()


async def test_missing_parent_stops_at_once() -> None:
    stop = asyncio.Event()
    await main._watch_parent_pid(999_999_999, stop)
    assert stop.is_set()
