"""Validação física do resultado depois de transferência e pós-processamento."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.models import DownloadMode
from app.services.process_utils import hidden_process_kwargs


@dataclass(frozen=True, slots=True)
class OutputValidation:
    valid: bool
    path: Path | None
    message: str
    technical_detail: str | None = None
    stream_types: tuple[str, ...] = field(default_factory=tuple)


class OutputValidator:
    """Confirma existência, extensão, tamanho e streams do arquivo reportado."""

    def __init__(self, ffprobe_path: Path | str | None, *, timeout_seconds: float = 10.0) -> None:
        self.ffprobe_path = Path(ffprobe_path) if ffprobe_path else None
        self.timeout_seconds = timeout_seconds

    def validate(
        self,
        reported_paths: list[Path] | tuple[Path, ...],
        mode: DownloadMode,
        expected_extension: str | None,
    ) -> OutputValidation:
        extension = None
        if expected_extension:
            extension = expected_extension.lower()
            if not extension.startswith("."):
                extension = f".{extension}"
        candidate = self._find_candidate(reported_paths, extension)
        if candidate is None:
            return OutputValidation(
                False, None, "O arquivo final não foi encontrado após o download."
            )
        if candidate.stat().st_size <= 0:
            return OutputValidation(False, candidate, "O arquivo final está vazio.")
        if mode is DownloadMode.MP3 and candidate.suffix.lower() != ".mp3":
            return OutputValidation(False, candidate, "A conversão não produziu um arquivo MP3.")
        if self.ffprobe_path is None or not self.ffprobe_path.is_file():
            return OutputValidation(
                False,
                candidate,
                "FFprobe é necessário para validar o arquivo final.",
            )

        probe = self._probe(candidate)
        if not probe.valid:
            return OutputValidation(False, candidate, probe.message, probe.technical_detail)
        stream_types = probe.stream_types
        if mode is DownloadMode.VIDEO:
            if "video" not in stream_types or "audio" not in stream_types:
                return OutputValidation(
                    False,
                    candidate,
                    "O arquivo final não contém vídeo e áudio válidos.",
                    stream_types=stream_types,
                )
        elif "audio" not in stream_types or "video" in stream_types:
            return OutputValidation(
                False,
                candidate,
                "O arquivo final MP3 não contém somente uma trilha de áudio válida.",
                stream_types=stream_types,
            )
        return OutputValidation(
            True,
            candidate,
            "Arquivo final validado com sucesso.",
            stream_types=stream_types,
        )

    @staticmethod
    def _find_candidate(
        reported_paths: list[Path] | tuple[Path, ...], extension: str | None
    ) -> Path | None:
        for raw_path in reversed(reported_paths):
            path = Path(raw_path)
            if (
                path.is_file()
                and (extension is None or path.suffix.lower() == extension)
                and not path.name.lower().endswith((".part", ".ytdl", ".tmp"))
            ):
                return path
        return None

    def _probe(self, path: Path) -> OutputValidation:
        try:
            result = subprocess.run(
                [
                    str(self.ffprobe_path),
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self.timeout_seconds,
                **hidden_process_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return OutputValidation(False, path, "A validação do arquivo excedeu o tempo limite.")
        except OSError as exc:
            return OutputValidation(False, path, "Não foi possível executar FFprobe.", str(exc))
        if result.returncode != 0:
            return OutputValidation(
                False, path, "FFprobe rejeitou o arquivo final.", result.stderr[:500]
            )
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            return OutputValidation(False, path, "A resposta de FFprobe não é válida.", str(exc))
        streams = data.get("streams")
        if not isinstance(streams, list):
            return OutputValidation(False, path, "FFprobe não encontrou trilhas de mídia.")
        types = tuple(
            sorted(
                {
                    stream["codec_type"]
                    for stream in streams
                    if isinstance(stream, dict) and stream.get("codec_type")
                }
            )
        )
        return OutputValidation(True, path, "Streams lidos.", stream_types=types)
