# Nyx — instrucciones para Gemini

Las instrucciones del proyecto son las mismas para cualquier agente y están en
[CLAUDE.md](CLAUDE.md): **léelo entero antes de nada** y síguelo igual que si fuera para ti
(donde dice «Claude», entiende «el agente»). La especificación es [docs/SPEC.md](docs/SPEC.md).

## Lo que estás haciendo

Estás continuando el plan de la versión en curso: [docs/PLAN-0.6.md](docs/PLAN-0.6.md).

1. Lee la sección **0** del plan entera (reglas, comprobaciones, commits y trampas conocidas)
   y la sección **1** si la tarea añade una herramienta.
2. Haz **solo la tarea que te pida el usuario** (por número, p. ej. «6.09»). Si no te dice
   cuál, mira el Registro (sección 9 del plan) y propón la siguiente según el orden de la
   sección 2, sin empezarla hasta que diga que sí.
3. Las tareas marcadas **DECISIÓN** requieren parar y preguntar. Las marcadas **Claude** son
   delicadas: si el usuario te pide hacerlas igualmente, sigue el diseño al pie de la letra.
4. Al terminar: comprobaciones de la sección 0.3 en verde, fila en el Registro, línea en
   `CHANGELOG.md`, un commit. Después, di qué has hecho y qué tiene que probar el usuario.

## Reglas extra para ti

- No cambies archivos que la tarea no menciona, salvo los que la plantilla de herramientas
  (sección 1 del plan) obliga a tocar.
- No inventes nombres de funciones, clases o archivos: búscalos en el código antes de usarlos.
  Si el plan nombra algo que no existe, para y pregunta.
- No escribas código con heredocs en la terminal; edita los archivos directamente.
- Si una comprobación falla y no sabes por qué tras dos intentos, para y explícalo: no
  desactives pruebas, no añadas `# type: ignore` ni `noqa` para esquivarlas.
- Responde al usuario en español de España.
- Cuando el usuario vuelva a Claude, Claude revisará lo que hayas hecho: deja en «Notas para
  la revisión» del Registro cualquier duda, atajo o cosa que no hayas podido probar.
