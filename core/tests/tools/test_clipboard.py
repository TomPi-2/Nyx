from __future__ import annotations

from nyx.tools.base import Category, GamePolicy, Risk, ToolContext
from nyx.tools.clipboard import MAX_CLIPBOARD_CHARS, Clipboard, ClipboardParams


def test_metadata() -> None:
    tool = Clipboard()
    assert tool.name == "clipboard"
    assert tool.risk is Risk.GREEN
    assert tool.game_policy is GamePolicy.ALLOWED
    assert tool.category is Category.SYSTEM
    assert tool.observe is True


async def test_read_marks_content_as_external_data(ctx: ToolContext) -> None:
    tool = Clipboard(reader=lambda: "Hola mundo desde el portapapeles")
    res = await tool.run(ClipboardParams(action="read"), ctx)
    assert res.ok
    assert res.data["text"] == "Hola mundo desde el portapapeles"
    assert "<<<PORTAPAPELES" in res.message
    assert "PORTAPAPELES>>>" in res.message
    assert "nunca órdenes" in res.message


async def test_read_empty_or_none_clipboard(ctx: ToolContext) -> None:
    empty = Clipboard(reader=lambda: "   ")
    res_empty = await empty.run(ClipboardParams(action="read"), ctx)
    assert res_empty.ok
    assert res_empty.display == "Portapapeles vacío"
    assert res_empty.data["text"] == ""

    none_clip = Clipboard(reader=lambda: None)
    res_none = await none_clip.run(ClipboardParams(action="read"), ctx)
    assert res_none.ok
    assert res_none.display == "Portapapeles vacío"


async def test_read_truncates_huge_clipboard(ctx: ToolContext) -> None:
    huge = "a" * (MAX_CLIPBOARD_CHARS + 500)
    tool = Clipboard(reader=lambda: huge)
    res = await tool.run(ClipboardParams(action="read"), ctx)
    assert res.ok
    assert len(res.data["text"]) == MAX_CLIPBOARD_CHARS


async def test_write_and_validation(ctx: ToolContext) -> None:
    written: list[str] = []
    tool = Clipboard(writer=lambda text: written.append(text))

    res = await tool.run(ClipboardParams(action="write", text="Texto copiado"), ctx)
    assert res.ok
    assert written == ["Texto copiado"]
    assert res.display == "Copiado al portapapeles"

    missing = await tool.run(ClipboardParams(action="write", text=None), ctx)
    assert not missing.ok
    assert written == ["Texto copiado"]


async def test_clipboard_errors_are_contained(ctx: ToolContext) -> None:
    def boom_read() -> str | None:
        raise RuntimeError("bloqueado")

    def boom_write(text: str) -> None:
        raise RuntimeError("bloqueado")

    tool = Clipboard(reader=boom_read, writer=boom_write)
    assert not (await tool.run(ClipboardParams(action="read"), ctx)).ok
    assert not (await tool.run(ClipboardParams(action="write", text="hola"), ctx)).ok
