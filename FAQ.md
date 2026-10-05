# Preguntas frecuentes

**Me sale `zsh: no matches found: ...` y yt-cli no imprime nada.**
Ocurre **antes** de que yt-cli se ejecute: el shell interpreta `?` como un glob y `&` como
"ejecutar en segundo plano". Pon la URL entre comillas dobles:

```bash
yt-cli audio "https://music.youtube.com/playlist?list=XYZ&si=abc"
```

**¿Cómo descargo una playlist o un álbum de YouTube Music en audio?**
`yt-cli audio "<URL de la playlist>"` (detecta que es una playlist), o de forma explícita
`yt-cli playlist "<URL>" --audio -f opus`. Si un tema no está disponible, se salta, se
sigue con el resto y al final se lista qué falló y por qué; el código de salida es 3
(parcial). `yt-cli history --failed` muestra el detalle después.

**Un video da "Video unavailable". ¿Es un bug?**
Normalmente no: el video fue eliminado, es privado o está bloqueado en tu región. Si el
mensaje habla de verificar que no eres un bot o de restricción de edad, configura las
cookies de un navegador con sesión iniciada en YouTube:
`yt-cli config set network.cookies_from_browser firefox`.

**¿Cómo sincronizo una playlist sin volver a descargar lo que ya tengo?**
Usa `--archive` (o `yt-cli config set downloads.use_download_archive true`). yt-cli
registra cada video descargado en `~/.local/share/yt-cli/archive.txt` y lo salta la
próxima vez; en el resumen aparece como "ya descargadas antes".

**`doctor` dice que falta un runtime JavaScript.**
Desde finales de 2025, YouTube exige resolver retos JavaScript y yt-dlp necesita un
runtime externo. En Arch, el paquete `yt-dlp` ya instala `deno`; en otras distros instala
`deno` (recomendado), `node`, `bun` o `quickjs`.

**No se incrusta la carátula en opus/flac/ogg.**
yt-dlp necesita el módulo `mutagen` para esos formatos (`sudo pacman -S python-mutagen`;
el paquete de yt-cli ya lo declara). En `wav`, `aac` y video `webm` no es posible incrustar
carátulas, así que yt-cli no lo intenta.

**¿Dónde se guardan las descargas?**
En `~/Downloads/yt-cli/` por defecto: `yt-cli config set general.download_directory ~/Music`,
o `-o <dir>` en cada comando. La plantilla por defecto crea una carpeta por canal; para
archivos sueltos usa `yt-cli config set downloads.filename_template '{title}.{ext}'`.

**¿Qué hace `overwrite_policy = "rename"`?**
Si el archivo destino ya existe, añade un sufijo: `Video.mp4`, `Video (1).mp4`, … Se
calcula con la misma lógica de nombres que usa yt-dlp. Solo aplica a descargas
individuales, no a playlists/canales.

**¿Puedo pasarle a yt-dlp una opción que yt-cli no expone?**
Sí, en la sección `[ytdlp]` de `config.toml` o con
`yt-cli config set ytdlp.<opción> <valor>`, usando los nombres de la API de Python de
yt-dlp (p. ej. `geo_bypass_country`, `sleep_interval`). Las opciones que yt-cli gestiona
internamente (formato, rutas, postprocesadores, progreso) se ignoran con un aviso.

**¿Cómo actualizo yt-cli?**
Depende de cómo lo instalaste: paquete de Arch → `git pull` + `makepkg -si -p
packaging/PKGBUILD`; pipx/uv → `pipx upgrade yt-cli` / `uv tool upgrade yt-cli`.
`yt-cli update` comprueba si hay una versión nueva y te dice el comando adecuado.

**¿Puedo usar un proxy o limitar la velocidad?**
`yt-cli config set network.proxy "http://usuario:pass@host:puerto"` (se guarda con
permisos 0600 y se oculta en `config show`) y
`yt-cli config set network.rate_limit_kbps 500`.

**¿Puedo desactivar los colores o usar la salida en scripts?**
`NO_COLOR=1 yt-cli ...` desactiva los colores. `search`, `history` y `version` aceptan
`--json`. Los códigos de salida están documentados en el README y en `man yt-cli`.

**¿Esto elude protecciones de YouTube (DRM)?**
No. yt-cli usa yt-dlp para contenido accesible públicamente; el usuario es responsable
de cumplir los Términos de Servicio de YouTube.
