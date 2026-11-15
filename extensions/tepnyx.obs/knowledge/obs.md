# OBS Studio con Nyx

## Preparar OBS para Nyx

Nyx controla OBS por su servidor WebSocket, que viene dentro de OBS desde la versión 28. En
OBS: menú Herramientas → Configuración del servidor WebSocket → marca «Habilitar servidor
WebSocket» (puerto 4455, el que viene). Si tiene «Habilitar autenticación», pulsa «Mostrar
información de conexión», copia la contraseña y ponla en Ajustes de Nyx → Extensiones → OBS
Studio. OBS tiene que estar abierto para que Nyx lo use.

## Qué se le puede pedir

Empezar, parar, pausar y reanudar la grabación; empezar y terminar el directo (Nyx pregunta
antes); guardar la repetición (los últimos segundos, si el búfer de repetición está activado);
activar la cámara virtual; cambiar de escena por su nombre; silenciar o cambiar el volumen del
micro, del sonido del PC o de una fuente; mostrar u ocultar una fuente (la cámara, una imagen);
hacer una captura de lo que se ve; y decir si está grabando o emitiendo y qué escenas hay.

## Búfer de repetición

Para guardar repeticiones (clips de lo último que ha pasado) hay que activarlo en OBS:
Ajustes → Salida → Búfer de repetición, con los segundos que se quieran guardar. Después,
«Nyx, activa la repetición en OBS» y, cuando pase algo, «guarda la repetición».

## Si no funciona

«OBS no está abierto»: abre OBS y comprueba que el servidor WebSocket está habilitado.
«La contraseña no es correcta»: vuelve a copiarla de «Mostrar información de conexión».
Las grabaciones y capturas se guardan en la carpeta de grabaciones de OBS (Ajustes → Salida).
