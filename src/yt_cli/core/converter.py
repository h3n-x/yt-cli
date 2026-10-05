"""Conversión de formatos post-descarga mediante ffmpeg/ffprobe.

Regla de seguridad no negociable: nunca se construye un comando como string
y se pasa a una shell. Siempre se invoca `subprocess.run` con una lista de
argumentos explícita y `shell=False` (el valor por defecto, pero se es
explícito aquí para que quede documentado en el propio código).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from yt_cli.models.enums import AudioFormat, VideoFormat


class FFmpegNotFoundError(RuntimeError):
    """ffmpeg o ffprobe no están instalados / no están en PATH."""


class ConversionError(RuntimeError):
    """ffmpeg devolvió un código de salida distinto de cero."""


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegNotFoundError(
            f"'{name}' no se encontró en PATH. Instálalo con: sudo pacman -S ffmpeg"
        )
    return path


_AUDIO_CODECS: dict[AudioFormat, str] = {
    AudioFormat.MP3: "libmp3lame",
    AudioFormat.OGG: "libvorbis",
    AudioFormat.OPUS: "libopus",
    AudioFormat.FLAC: "flac",
    AudioFormat.WAV: "pcm_s16le",
    AudioFormat.M4A: "aac",
    AudioFormat.AAC: "aac",
}

_VIDEO_CONTAINER_ARGS: dict[VideoFormat, list[str]] = {
    VideoFormat.MP4: ["-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart"],
    VideoFormat.MKV: ["-c:v", "copy", "-c:a", "copy"],
    VideoFormat.WEBM: ["-c:v", "libvpx-vp9", "-c:a", "libopus"],
    VideoFormat.MOV: ["-c:v", "copy", "-c:a", "copy"],
}


class FFmpegConverter:
    """Ejecuta conversiones puntuales con ffmpeg, fuera del flujo normal de
    yt-dlp (por ejemplo, cuando el usuario pide re-convertir un archivo ya
    descargado con `yt-cli convert`).
    """

    def __init__(self) -> None:
        self._ffmpeg = _require_binary("ffmpeg")
        self._ffprobe = _require_binary("ffprobe")

    def convert_audio(
        self, source: Path, destination: Path, audio_format: AudioFormat, bitrate_kbps: int | None
    ) -> Path:
        codec = _AUDIO_CODECS[audio_format]
        args = [self._ffmpeg, "-y", "-i", str(source), "-vn", "-c:a", codec]
        if bitrate_kbps is not None and audio_format != AudioFormat.FLAC:
            args += ["-b:a", f"{bitrate_kbps}k"]
        args.append(str(destination))
        self._run(args)
        return destination

    def convert_video(self, source: Path, destination: Path, video_format: VideoFormat) -> Path:
        args = [self._ffmpeg, "-y", "-i", str(source), *_VIDEO_CONTAINER_ARGS[video_format], str(destination)]
        self._run(args)
        return destination

    def probe_duration_seconds(self, media_path: Path) -> float:
        args = [
            self._ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ]
        result = self._run(args)
        try:
            return float(result.stdout.strip())
        except ValueError as exc:
            raise ConversionError(f"ffprobe no devolvió una duración válida para {media_path}") from exc

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(  # noqa: S603 - lista de argumentos fija, sin shell
            args,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ConversionError(
                f"ffmpeg falló (código {result.returncode}) al ejecutar: {' '.join(args)}\n"
                f"stderr: {result.stderr.strip()[-2000:]}"
            )
        return result
