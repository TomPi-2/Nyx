# Coste del prefijo · qwen2.5:7b · 29 herramientas

- Tokens del prefijo (sistema + herramientas + pregunta): **5467** de 8192 (66 % del contexto).
- Sistema y pregunta sin herramientas: 706. Herramientas: **4761** (~164 por herramienta).
- Primer token con la caché fría: **5.28 s**; caliente: **0.07 s**.

| Herramienta | Tokens (aprox.) |
| --- | --- |
| move_files | 345 |
| copy_files | 343 |
| delete_files | 304 |
| app_action | 299 |
| list_files | 288 |
| find_files | 247 |
| nyx_control | 202 |
| set_volume | 192 |
| media_control | 181 |
| set_alarm | 168 |
| set_timer | 147 |
| window_layout | 143 |
| rename_file | 142 |
| send_hotkey | 139 |
| open_nyx_settings | 138 |
| pending | 129 |
| cancel_alarm | 124 |
| nyx_info | 123 |
| open_path | 122 |
| open_app | 121 |
| open_settings | 121 |
| open_url | 117 |
| create_folder | 111 |
| screenshot | 104 |
| wait_for_window | 95 |
| close_app | 94 |
| focus_window | 82 |
| undo | 74 |
| list_alarms | 66 |

## Conclusiones (6.18, 2026-11-11)

- **Elegir herramientas por petición no sirve:** cambiaría el prefijo y cada petición pagaría la caché fría (5,3 s en vez de 0,07 s). Todas las herramientas van siempre.
- **No caben las de la 0.6:** faltan ~15 herramientas (~2.500 tokens). Con 8.192 de contexto, el prefijo se comería casi todo y no quedaría sitio para la memoria, el contexto ni los resultados del bucle de agente.
- **Más herramientas = el 7B duda más** (6.03): la batería bajó al 96 % con 28 y volvió al 100 % quitando reglas del prompt que nombraban herramientas.

## Propuesta (pendiente de aprobación)

1. **Descripciones más cortas** (objetivo: −30 % de tokens de herramientas): un solo ejemplo por herramienta salvo donde haga falta, descripciones de parámetros de 3–6 palabras, y los campos comunes de las herramientas de archivos (`FileSelection`) más compactos. Batería antes y después, dos veces.
2. **Quitar `wait_for_window` de la lista del modelo:** el ejecutor ya pone las esperas solo (`with_waits`). La herramienta sigue existiendo para los planes.
3. **Contexto de 12.288 tokens** (`llm.num_ctx`): +4.096 tokens ≈ +235 MB de VRAM con el 7B (caché KV en f16). Deja sitio a las herramientas que faltan. Hay que volver a medir la partida (`scripts/game_bench.py`) por si cuesta FPS.
4. **Lo frecuente y sin ambigüedad, al router** (ya se hace): más rápido y no depende del modelo.
