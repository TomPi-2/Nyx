import pytest

from nyx.brain.reply import Reply
from nyx.brain.service import worth_remembering
from nyx.executor import ToolCall, fix_enums
from nyx.tools.registry import default_registry


@pytest.mark.parametrize(
    ("spoken", "keep"),
    [
        ("pausa", False),
        ("pon música", False),
        ("aún no sé hacer eso", False),
        ("Aún no sé hacer eso.", False),
        ("Son las 21:36.", True),
        ("En alemán se dice Hallo.", True),
        ("Un agujero negro es un objeto con mucha gravedad", True),
    ],
)
def test_odd_replies_are_not_remembered(spoken: str, keep: bool) -> None:
    assert worth_remembering(Reply(display="x", spoken=spoken)) is keep


def test_fix_enums() -> None:
    reg = default_registry()
    fixed = fix_enums([ToolCall("media_control", {"action": "playpause"})], reg)
    assert fixed == [ToolCall("media_control", {"action": "play_pause"})]
    same = [ToolCall("window_layout", {"action": "maximize", "name": "Chrome"})]
    assert fix_enums(same, reg) == same
    unknown = [ToolCall("media_control", {"action": "bailar"})]
    assert fix_enums(unknown, reg) == unknown  # sin equivalente: lo rechazará la validación
