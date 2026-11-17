# Modos de Nyx — propuesta (tarea 8.09)

> **Aprobada por el usuario el 2026-11-17** con las respuestas de la sección 6; hecha en las
> tareas 8.10–8.12 (`core/nyx/modes/manager.py`, Ajustes → Modos). Parte de HOJA-DE-RUTA §5 y
> de la decisión de la 7.10 (Noche abre Configuración).

## 1. Qué es un modo

Un perfil que cambia cómo se comporta Nyx y prepara el PC para algo. Tiene:

| Parte | Qué es | Ejemplo |
| --- | --- | --- |
| Disparadores | Voz, la bandeja, una hora o una app abierta | «modo trabajo»; Noche a las 23:00 |
| Al entrar | Acciones de una lista cerrada (las herramientas verdes y amarillas de siempre) | abrir y colocar apps, volumen, ocultar apps, abrir una página de Configuración |
| Al salir | Se deshace lo que hizo al entrar, con el «Deshacer» de cada herramienta | vuelve el volumen, vuelven las apps ocultas |
| Cómo es Nyx | Voz (normal, baja o nada), burbujas (todo, sin contenido o nada), activación por voz sí o no, tono | Privacidad: sin activación por voz y burbujas sin contenido |
| Herramientas | Permitidas, diferidas o bloqueadas por modo | Privacidad bloquea la búsqueda en internet |

Solo hay **un modo elegido** a la vez. **Partida tiene prioridad**: si empieza una partida en
modo Trabajo, manda Partida y, al acabar, se vuelve a Trabajo.

## 2. Partida no cambia

Partida pasa a mostrarse como un modo (en Ajustes y en la bandeja), pero **su código y su
comportamiento se quedan como están** (`game/`: detector, `GameGate`, políticas y tiempos). El
gestor de modos solo escucha `GameStateChanged` para saber que Partida manda y volver al modo
anterior al acabar. Así no hay riesgo de perder FPS ni de cambiar lo ya medido. Antes de cerrar
la 0.8 se prueba jugando que Partida sigue igual.

## 3. Los tres modos nuevos

| Modo | Al entrar | Nyx | Herramientas |
| --- | --- | --- | --- |
| **Trabajo** | Abre y coloca las apps que elijas (Ajustes → Modos); silencia las que distraen (Discord, WhatsApp… las que elijas) | Voz baja, burbujas normales | Todas |
| **Noche** | Volumen al 20 % (ajustable); abre la luz nocturna y «no molestar» en Configuración (Windows no deja cambiarlas a una app: decisión de la 7.10) | Voz más suave y más lenta; sin sonidos de Nyx (las alarmas suenan, más bajas) | Todas |
| **Privacidad** | Oculta las apps que elijas (`hide_apps`, 8.08) | Sin activación por voz (solo `Win+Alt+H`); burbujas sin contenido («Hecho», sin el texto de la nota, la cita o lo dictado) | Bloquea la búsqueda en internet y abrir webs; leer lo seleccionado o el portapapeles, permitido |

Disparadores: los tres por voz («modo trabajo», «activa el modo noche», «sal del modo
privacidad», «¿en qué modo estás?») y desde la bandeja. Automáticos, **apagados por defecto**:
Noche a una hora; Trabajo al abrir una app (VS Code, Teams…).

## 4. Modos de extensiones (8.11)

El tipo `mode` del manifiesto: solo JSON, sin código. Un modo de fuera puede usar las mismas
acciones de la lista cerrada y lo mismo que un preajuste (voz, burbujas, tono). **Nunca**
políticas de herramientas, seguridad, privacidad ni la activación por voz: eso solo lo deciden
los modos de Nyx. Será el tercer ejemplo de la guía de extensiones.

## 5. Cómo se ve

En Ajustes, una sección **Modos** con cada modo, sus apps y su disparador automático. Junto a
Nyx, un indicador pequeño del modo activo (y nada en Partida, como hasta ahora). Va en el
prototipo de la 8.12, que se enseña antes de hacerlo.

## 6. Dudas para el usuario (respondidas el 2026-11-17)

Respuestas: 1, Partida se queda tal cual por dentro; 2, Privacidad corta **toda** la red de
Nyx; 3, los automáticos, apagados por defecto; 4, en Noche las alarmas suenan como siempre.

1. ¿Vale que Partida se quede tal cual por dentro y solo se vea como un modo?
2. ¿Privacidad bloquea toda la red de Nyx (búsqueda y webs) o solo la búsqueda?
3. ¿Los automáticos (Noche por hora, Trabajo por app) apagados por defecto?
4. ¿Noche baja también el volumen de las alarmas, o suenan como siempre?
