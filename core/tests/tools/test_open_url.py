import pytest

from nyx.tools.base import ToolContext
from nyx.tools.open_url import OpenUrl, OpenUrlParams, to_url
from tests.tools.fakes import FakeDesktop


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("marca.com", "https://marca.com"),
        ("marca punto com", "https://marca.com"),
        ("https://claude.ai/new", "https://claude.ai/new"),
        ("www.elpais.es/deportes", "https://www.elpais.es/deportes"),
        ("YouTube", None),
        ("javascript:alert(1)", None),
        ("file:///C:/Windows", None),
    ],
)
def test_to_url(text: str, url: str | None) -> None:
    assert to_url(text) == url


async def test_known_site(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenUrl().run(OpenUrlParams(target="youtube"), ctx)
    assert result.ok
    assert desktop.opened == ["https://www.youtube.com"]


async def test_domain(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenUrl().run(OpenUrlParams(target="marca punto com"), ctx)
    assert result.ok
    assert desktop.opened == ["https://marca.com"]


async def test_unknown_site(ctx: ToolContext, desktop: FakeDesktop) -> None:
    result = await OpenUrl().run(OpenUrlParams(target="la web de mi primo"), ctx)
    assert not result.ok
    assert desktop.opened == []
