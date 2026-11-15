# Spotify con Nyx

## Qué se le puede pedir

Poner una canción, un artista, un disco o una lista concretos («pon Bohemian Rhapsody en
Spotify», «pon mi lista de correr»), añadir una canción a la cola, guardar la que suena en tus
favoritas, decir qué suena, y aleatorio o repetir. Pausar, seguir y pasar de canción los hace
Nyx siempre, con Spotify o con cualquier otra app de música, sin conectar nada.

## Por qué hay que conectar una app propia

Desde febrero de 2026 Spotify solo deja que cada app la usen 5 personas y que su dueño tenga
Premium, así que Nyx no puede traer una app común para todos. Cada persona crea la suya (es
gratis y se hace una vez) y Nyx la usa. Poner música desde otra app exige Spotify Premium. Sin
conectarla, «pon X en Spotify» abre la búsqueda en la app de Spotify para que le des tú.

## Cómo conecto Spotify

1. Entra en developer.spotify.com/dashboard con tu cuenta de Spotify (la de Premium) y acepta
   las condiciones de desarrollador.
2. Pulsa «Create app». Nombre: «Nyx» (o el que quieras). Descripción: «Asistente de voz».
3. En «Redirect URIs» escribe exactamente `http://127.0.0.1/callback` y pulsa «Add» (sin
   puerto: Nyx elige uno libre). En «Which API/SDKs are you planning to use?» marca «Web API».
4. Acepta y guarda. En la app creada, abre «Settings» y copia el «Client ID».
5. En Nyx: Ajustes → Extensiones → Spotify, pega el Client ID en su campo.
6. Dile a Nyx «conecta Spotify»: se abre el navegador, entras y aceptas. Nyx te avisa cuando
   esté. No hace falta el «Client secret» y nunca se lo des a nadie.

## Si no funciona

«Spotify ha cerrado la sesión»: Spotify lo hace cada seis meses; dile «conecta Spotify» otra
vez. «Solo con Premium»: poner música desde otra app exige Premium. «No encuentro Spotify
abierto»: abre la app de Spotify (o el reproductor web) y vuelve a pedirlo. Si al conectar sale
«INVALID_CLIENT: Invalid redirect URI», revisa que la dirección del paso 3 sea exactamente
`http://127.0.0.1/callback`.
