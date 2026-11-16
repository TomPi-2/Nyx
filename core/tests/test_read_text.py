"""8.05: leer lo seleccionado y documentos (PDF, Word, texto) para resumirlos."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from nyx import textfiles
from nyx.brain.router import Route, route
from nyx.index.service import SystemIndex
from nyx.textfiles import DocumentError, extract, parse_pages
from nyx.tools.base import ToolContext
from nyx.tools.read_text import ReadText, ReadTextParams
from nyx.winapi.windows import Window


def make_pdf(path: Path, pages: list[str]) -> Path:
    """Un PDF de verdad, mínimo, con una línea de texto por página."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(bytes(out))
    return path


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
        )
    return path


def test_pdf_pages(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "informe.pdf", ["Primera pagina", "Segunda pagina", "Tercera"])
    whole = extract(pdf)
    assert "Primera pagina" in whole.text and "Tercera" in whole.text
    assert whole.partial == "" and whole.pages == 3
    some = extract(pdf, parse_pages("2-3"))
    assert "Primera" not in some.text and "Segunda" in some.text
    assert some.partial == "las páginas 2 a 3 de 3"
    with pytest.raises(DocumentError, match="solo tiene 3"):
        extract(pdf, (5, 6))


def test_word_and_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = extract(make_docx(tmp_path / "contrato.docx", ["Cláusula uno.", "Cláusula dos."]))
    assert doc.text == "Cláusula uno.\nCláusula dos."
    (tmp_path / "notas.txt").write_text("Hola\n\n\n\nadiós", encoding="utf-8")
    assert extract(tmp_path / "notas.txt").text == "Hola\n\nadiós"
    monkeypatch.setattr(textfiles, "MAX_CHARS", 30)
    (tmp_path / "largo.md").write_text("Una frase. " * 20, encoding="utf-8")
    long = extract(tmp_path / "largo.md")
    assert long.partial == "el principio" and long.text.endswith(".")
    with pytest.raises(DocumentError, match="solo leo"):
        extract(tmp_path / "foto.png")
    (tmp_path / "roto.docx").write_bytes(b"no es un zip")
    with pytest.raises(DocumentError, match="Word"):
        extract(tmp_path / "roto.docx")
    assert parse_pages("5 a 10") == (5, 10) and parse_pages("7") == (7, 7)
    with pytest.raises(DocumentError):
        parse_pages("diez")


async def test_document_by_name_and_newest(
    ctx: ToolContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nyx.tools.read_text as module
    from nyx.winapi import search

    old = make_pdf(tmp_path / "factura.pdf", ["Factura de luz"])
    new = make_docx(tmp_path / "contrato.docx", ["Contrato de alquiler."])
    import os

    os.utime(old, (1, 1))
    monkeypatch.setattr(module, "search_roots", lambda: [tmp_path])
    monkeypatch.setattr(search, "search", lambda q, roots, n: ([old, new], "prueba"))
    tool = ReadText()
    by_name = await tool.run(ReadTextParams(source="document", file="factura", kind="pdf"), ctx)
    assert by_name.ok and by_name.external == "Factura de luz"
    assert by_name.message == "He leído factura.pdf."
    newest = await tool.run(ReadTextParams(source="document"), ctx)
    assert newest.external == "Contrato de alquiler."
    none = await tool.run(ReadTextParams(source="document", kind="word", file="x"), ctx)
    assert none.ok  # «x» encuentra el .docx por el buscador falso
    missing = await tool.run(ReadTextParams(source="document", kind="text"), ctx)
    assert not missing.ok and missing.message == "No encuentro ningún documento de texto"


async def test_selection(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from nyx.winapi import games, selection, windows

    shown = [Window(1, "Nyx", "nyx-ui.exe"), Window(2, "Informe - Word", "winword.exe")]
    monkeypatch.setattr(windows, "list_windows", lambda: shown)
    monkeypatch.setattr(games, "window_is_game", lambda *a: False)
    seen: list[int] = []

    def uia(hwnd: int) -> str | None:
        seen.append(hwnd)
        return "El texto marcado."

    monkeypatch.setattr(selection, "uia_selection", uia)
    monkeypatch.setattr(selection, "copy_selection", lambda hwnd: None)
    tool = ReadText()
    got = await tool.run(ReadTextParams(source="selection"), ctx)
    assert got.ok and got.external == "El texto marcado." and seen == [2]  # Word, no Nyx
    assert "marcado" not in got.message  # lo leído no va al registro

    monkeypatch.setattr(selection, "uia_selection", lambda hwnd: None)
    copied: list[int] = []
    monkeypatch.setattr(selection, "copy_selection", lambda hwnd: copied.append(hwnd) or None)
    nothing = await tool.run(ReadTextParams(source="selection"), ctx)
    assert not nothing.ok and copied == [2]
    # En una terminal no se pulsa Ctrl+C (pararía lo que se ejecuta).
    shown[1] = Window(3, "PowerShell", "windowsterminal.exe")
    copied.clear()
    await tool.run(ReadTextParams(source="selection"), ctx)
    assert copied == []
    monkeypatch.setattr(games, "window_is_game", lambda *a: True)
    game = await tool.run(ReadTextParams(source="selection"), ctx)
    assert not game.ok and "juegos" in game.message


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("Resume lo que tengo seleccionado", {"source": "selection"}),
        ("Tradúceme lo seleccionado al inglés", {"source": "selection"}),
        ("¿Qué dice esto que he marcado?", {"source": "selection"}),
        (
            "Resume el PDF de Descargas",
            {"source": "document", "folder": "descargas", "kind": "pdf"},
        ),
        ("Resume el último Word", {"source": "document", "kind": "word"}),
        (
            "¿De qué va el PDF del contrato?",
            {"source": "document", "file": "contrato", "kind": "pdf"},
        ),
        (
            "Resume las páginas 5 a 10 del PDF del informe",
            {"source": "document", "file": "informe", "kind": "pdf", "pages": "5 a 10"},
        ),
    ],
)
def test_router(index: SystemIndex, text: str, args: dict[str, Any]) -> None:
    routed = route(text, index)
    assert isinstance(routed, Route) and routed.rule.startswith("read_")
    (call,) = routed.calls
    assert call.arguments == args


def test_router_leaves_the_clipboard_alone(index: SystemIndex) -> None:
    routed = route("Resume lo que tengo copiado", index)
    assert isinstance(routed, Route) and routed.rule == "clipboard_read"
