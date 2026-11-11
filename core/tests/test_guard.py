import pytest

from nyx.brain.guard import looks_like_code


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ('appaction({"app": "Rocket League", "action": "jump"})', True),
        ('app_action(app="Spotify")', True),
        ('{"display": "acciones", "spoken": "…"}', True),
        ("[acciones] open_app", True),
        ('<tool_call>{"name": "x"}</tool_call>', True),
        ("En alemán se dice Hallo.", False),
        ("Son las 10:50 (hora de Madrid).", False),
        ("La función f(x) = 2x es lineal.", False),
        ("Abriendo Spotify, como me pediste.", False),
    ],
)
def test_looks_like_code(text: str, code: bool) -> None:
    assert looks_like_code(text) is code
