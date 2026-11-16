"""app_reminder: recordatorios que saltan al abrir una app (tarea 8.03). Verde, con deshacer.

«Cuando abra Discord, recuérdame que le pase el enlace a Ana», «recuérdame mirar el correo
la próxima vez que abra Outlook», «¿qué recordatorios tengo para cuando abra algo?», «quita
el recordatorio de Discord». Saltan una vez (`organizer/context.py`), nunca en partida.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

from nyx.index.aliases import normalize
from nyx.safety.undo import Undo
from nyx.tools.base import Category, GamePolicy, Params, Risk, Tool, ToolContext, ToolResult
from nyx.tools.list_items import spoken_join


class AppReminderParams(Params):
    action: Literal["add", "list", "delete"] = Field(description="add, list o delete")
    app: str = Field(default="", max_length=100, description="La app que se abre")
    text: str = Field(default="", max_length=200, description="Lo que hay que recordar")


class AppReminderTool(Tool[AppReminderParams]):
    name = "app_reminder"
    description = "Recordatorio que salta al abrir una app («cuando abra Discord, recuérdame…»)."
    risk = Risk.GREEN
    game_policy = GamePolicy.ALLOWED
    category = Category.TIME
    params_model = AppReminderParams
    observe = True

    async def run(self, params: AppReminderParams, ctx: ToolContext) -> ToolResult:
        store = ctx.organizer
        if store is None:
            return ToolResult.fail("Los recordatorios no están disponibles")
        if params.action == "list":
            pending = store.app_reminders()
            if not pending:
                return ToolResult(
                    ok=True, message="No tienes recordatorios para cuando abras algo.", speak=True
                )
            parts = [f"al abrir {r.app}, {r.text}" for r in pending]
            return ToolResult(ok=True, message=f"Tienes: {spoken_join(parts)}.", speak=True)
        if params.action == "delete":
            wanted = normalize(params.app or params.text)
            found = [
                r
                for r in store.app_reminders()
                if wanted and (wanted in normalize(r.app) or wanted in normalize(r.text))
            ]
            if not found:
                return ToolResult.fail("No encuentro ese recordatorio")
            for r in found:
                store.delete_app_reminder(r.id)

            async def restore() -> str:
                for r in found:
                    store.delete_app_reminder(r.id, False)
                return "Recordatorio recuperado"

            return ToolResult(
                ok=True,
                message=f"Quitado: {spoken_join([r.text for r in found])}.",
                undo=Undo("Quitar el recordatorio", restore),
            )
        if not params.app.strip() or not params.text.strip():
            return ToolResult.fail("¿Al abrir qué app, y qué te recuerdo?")
        from nyx.tools.focus_window import process_for

        process = await asyncio.to_thread(process_for, ctx, params.app)
        reminder = store.add_app_reminder(params.app, process, params.text)

        async def back() -> str:
            store.delete_app_reminder(reminder.id)
            return "Recordatorio quitado"

        return ToolResult(
            ok=True,
            message=f"Cuando abras {reminder.app}, te recuerdo: {reminder.text}.",
            display="Recordatorio al abrir " + reminder.app,
            secondary=reminder.text,
            undo=Undo("Apuntar el recordatorio", back),
        )
