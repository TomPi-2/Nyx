"""list_items: listas de Nyx (la compra, pendientes…; tarea 8.01). Verde, con deshacer.

«Añade leche y huevos a la lista de la compra», «quita el pan», «¿qué hay en la lista?»,
«vacía la lista de la compra», «tacha los huevos», «¿qué listas tengo?». Todo local
(`organizer/store.py`); quitar y vaciar se pueden deshacer y nada se borra del todo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from nyx.organizer.store import DEFAULT_LIST, OrganizerStore, list_key, split_items
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult

Action = Literal["add", "remove", "read", "clear", "done", "lists"]


def spoken_join(words: list[str]) -> str:
    """["a", "b", "c"] → «a, b y c»."""
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " y " + words[-1]


def list_label(name: str) -> str:
    return f"la lista «{list_key(name)}»"


class ListItemsParams(Params):
    action: Action = Field(description="add, remove, read, clear, done (tachar) o lists")
    list: str = Field(default="", max_length=60, description="La lista: compra, pendientes…")
    items: str = Field(default="", max_length=500, description="Lo que se añade o se quita")


class ListItems(Tool[ListItemsParams]):
    name = "list_items"
    description = "Listas de Nyx (la compra…): añadir, quitar, leer, tachar o vaciar."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = ListItemsParams
    observe = True

    async def run(self, params: ListItemsParams, ctx: ToolContext) -> ToolResult:
        store = ctx.organizer
        if store is None:
            return ToolResult.fail("Las listas no están disponibles")
        name = params.list or DEFAULT_LIST
        label = list_label(name)
        if params.action == "lists":
            return self._lists(store)
        if params.action == "read":
            return self._read(store, name, label)
        if params.action == "clear":
            removed = store.clear(name)
            if not removed:
                return ToolResult(
                    ok=True, message=f"{label.capitalize()} ya está vacía.", speak=True
                )

            async def back() -> str:
                store.restore(removed)
                return f"He devuelto {len(removed)} a {label}"

            return ToolResult(
                ok=True,
                message=f"He vaciado {label} ({len(removed)}).",
                display=f"{label.capitalize()}, vacía",
                undo=Undo(f"Vaciar {label}", back),
            )
        things = split_items(params.items)
        if not things:
            return ToolResult.fail("¿Qué pongo en la lista?")
        if params.action == "add":
            return self._add(store, name, label, things)
        if not params.list:
            # «Tacha los huevos»: la lista donde esté (si está en una sola).
            where = [t for t, _ in store.lists() if store.find_items(t, things[0])]
            if len(where) > 1:
                options = spoken_join([f"«{t}»" for t in where])
                return ToolResult.fail(f"Está en varias listas: {options}. ¿En cuál?")
            if where:
                name, label = where[0], list_label(where[0])
        return self._change(store, name, label, things, done=params.action == "done")

    def _lists(self, store: OrganizerStore) -> ToolResult:
        found = store.lists()
        if not found:
            return ToolResult(ok=True, message="No tienes ninguna lista.", speak=True)
        parts = [f"«{title}» ({n})" for title, n in found]
        return ToolResult(
            ok=True, message=f"Tienes estas listas: {spoken_join(parts)}.", speak=True
        )

    def _read(self, store: OrganizerStore, name: str, label: str) -> ToolResult:
        items = store.items(name)
        if not items:
            return ToolResult(ok=True, message=f"{label.capitalize()} está vacía.", speak=True)
        texts = [f"{i.text} (hecho)" if i.done else i.text for i in items]
        return ToolResult(
            ok=True,
            message=f"En {label}: {spoken_join(texts)}.",
            display=label.capitalize(),
            secondary=", ".join(texts)[:300],
            speak=True,
        )

    def _add(self, store: OrganizerStore, name: str, label: str, things: list[str]) -> ToolResult:
        added, already = store.add_items(name, things)
        if not added:
            return ToolResult(
                ok=True, message=f"Ya estaba en {label}: {spoken_join(already)}.", speak=True
            )
        new = [t for t in things if t not in already]

        async def back() -> str:
            store.remove(added)
            return f"Quitado de {label}"

        extra = f" (ya estaba: {spoken_join(already)})" if already else ""
        return ToolResult(
            ok=True,
            message=f"Apuntado en {label}: {spoken_join(new)}{extra}.",
            display=f"En {label}",
            secondary=", ".join(new)[:300],
            undo=Undo(f"Añadir a {label}", back),
        )

    def _change(
        self, store: OrganizerStore, name: str, label: str, things: list[str], *, done: bool
    ) -> ToolResult:
        ids: list[int] = []
        names: list[str] = []
        for thing in things:
            found = store.find_items(name, thing)
            if not found:
                return ToolResult.fail(f"No encuentro «{thing}» en {label}")
            if len(found) > 1:
                options = spoken_join([f"«{i.text}»" for i in found[:5]])
                return ToolResult.fail(f"Hay varias: {options}. ¿Cuál?")
            ids.append(found[0].id)
            names.append(found[0].text)
        if done:
            store.set_done(ids, True)

            async def undone() -> str:
                store.set_done(ids, False)
                return "Ya no está tachado"

            return ToolResult(
                ok=True,
                message=f"Tachado en {label}: {spoken_join(names)}.",
                undo=Undo(f"Tachar en {label}", undone),
            )
        store.remove(ids)

        async def back() -> str:
            store.restore(ids)
            return f"Vuelve a estar en {label}"

        return ToolResult(
            ok=True,
            message=f"Quitado de {label}: {spoken_join(names)}.",
            undo=Undo(f"Quitar de {label}", back),
        )
