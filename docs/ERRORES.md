# Errores conocidos

Fallos vistos al usar Nyx que quedan pendientes de corregir. Se apuntan aquí para no perderlos y se corrigen por tandas sin parar el plan de fases. Al corregir uno, se mueve a «Corregidos» con la fecha y el commit, y se añade su frase a la batería de pruebas (`core/tests`).

## Pendientes

| Fecha | Frase o situación | Qué pasa | Qué debería pasar | Pista |
| --- | --- | --- | --- | --- |
| 2026-11-10 | «Explícame qué es un agujero negro» (escrito, portátil) | Responde que aún no puede buscar en internet. | Explicarlo con el LLM local, sin internet: es conocimiento general. | Probablemente «explícame» o «qué es» acaba en la negativa de búsqueda web en vez de en una pregunta al LLM. Revisar el router y las negativas fijas (`refusal`). |
| 2026-11-10 | «Elimina la carpeta llamada "carpeta nueva" del escritorio» | Dice que no hay ningún archivo así. | Encontrar la carpeta (en Windows suele llamarse «Nueva carpeta») y pedir confirmación para moverla a la papelera. | Revisar cómo se extrae el nombre con «llamada» y comillas, y si la búsqueda difusa tolera el orden de las palabras. Si no existe, sugerir la más parecida (SPEC sección 14). |

## Corregidos

| Fecha | Error | Commit |
| --- | --- | --- |
