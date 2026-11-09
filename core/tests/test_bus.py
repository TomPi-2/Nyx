from dataclasses import dataclass

from nyx.bus import EventBus


@dataclass
class Base:
    n: int


@dataclass
class Child(Base):
    pass


async def test_publish_reaches_subscribers_of_type_and_base() -> None:
    bus = EventBus()
    got: list[str] = []

    async def on_base(e: Base) -> None:
        got.append(f"base{e.n}")

    async def on_child(e: Child) -> None:
        got.append(f"child{e.n}")

    bus.subscribe(Base, on_base)
    bus.subscribe(Child, on_child)
    await bus.publish(Child(1))
    await bus.publish(Base(2))
    assert sorted(got) == ["base1", "base2", "child1"]


async def test_failing_handler_does_not_block_others() -> None:
    bus = EventBus()
    got: list[int] = []

    async def bad(_: Base) -> None:
        raise RuntimeError("boom")

    async def good(e: Base) -> None:
        got.append(e.n)

    bus.subscribe(Base, bad)
    bus.subscribe(Base, good)
    await bus.publish(Base(7))
    assert got == [7]


async def test_unsubscribe() -> None:
    bus = EventBus()
    got: list[int] = []

    async def handler(e: Base) -> None:
        got.append(e.n)

    unsubscribe = bus.subscribe(Base, handler)
    unsubscribe()
    await bus.publish(Base(1))
    assert got == []
