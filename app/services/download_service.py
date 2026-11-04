"""Motor de transferência baseado na API Python do yt-dlp."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.models import (
    DownloadMode,
    DownloadPlan,
    DownloadProgress,
    DownloadResult,
    ProgressStage,
    ResultStatus,
)
from app.services.dependencies import DependencyPaths, DependencyReport
from app.services.output_validator import OutputValidator
from app.services.process_utils import hidden_process_kwargs
from app.services.url_validator import validate_supported_video_url

ProgressCallback = Callable[[DownloadProgress], None]


class SanitizedLogger:
    """Adapta o logger do yt-dlp sem registrar URLs ou tokens sensíveis."""

    def __init__(self, sink: Any) -> None:
        self.sink = sink

    def debug(self, message: str) -> None:
        self._write("debug", message)

    def info(self, message: str) -> None:
        self._write("info", message)

    def warning(self, message: str) -> None:
        self._write("warning", message)

    def error(self, message: str) -> None:
        self._write("error", message)

    def _write(self, level: str, message: str) -> None:
        clean = _sanitize_detail(str(message))
        if callable(self.sink):
            self.sink(level, clean)
            return
        method = getattr(self.sink, level, None)
        if callable(method):
            method(clean)


class DownloadCancelled(Exception):
    """Sinaliza cancelamento solicitado pelo usuário."""


class DownloadService:
    """Executa uma tarefa de vídeo ou áudio sem conhecer widgets Qt."""

    def __init__(self, *, logger: Any | None = None) -> None:
        self.logger = logger

    def download(
        self,
        url: str,
        plan: DownloadPlan,
        *,
        output_template: str | None = None,
        deps: DependencyReport | DependencyPaths | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        output_validator: OutputValidator | None = None,
    ) -> DownloadResult:
        validation = validate_supported_video_url(url)
        if not validation.valid or validation.normalized_url is None:
            return DownloadResult(ResultStatus.ERROR, error_message=validation.message)

        cancel_event = cancel_event or threading.Event()
        dependency_error = _dependency_error(plan, deps)
        if dependency_error is not None:
            return DownloadResult(ResultStatus.ERROR, error_message=dependency_error)

        paths: list[Path] = []
        options = self._build_options(
            plan,
            output_template=output_template,
            deps=deps,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            paths=paths,
        )
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([validation.normalized_url])
        except DownloadCancelled:
            _emit(
                progress_callback,
                DownloadProgress(ProgressStage.CANCELLED, "Download cancelado."),
            )
            return DownloadResult(ResultStatus.CANCELLED, tuple(paths))
        except DownloadError as exc:
            detail = _sanitize_detail(str(exc))
            if cancel_event.is_set():
                return DownloadResult(ResultStatus.CANCELLED, tuple(paths), technical_detail=detail)
            _emit(
                progress_callback,
                DownloadProgress(ProgressStage.FAILED, "Falha no download."),
            )
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message=_download_error_message(detail, url),
                technical_detail=detail,
            )
        except Exception as exc:
            detail = _sanitize_detail(str(exc))
            if cancel_event.is_set():
                return DownloadResult(ResultStatus.CANCELLED, tuple(paths), technical_detail=detail)
            _emit(
                progress_callback,
                DownloadProgress(ProgressStage.FAILED, "Falha no download."),
            )
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="Não foi possível concluir o download.",
                technical_detail=detail,
            )

        if cancel_event.is_set():
            return DownloadResult(ResultStatus.CANCELLED, tuple(paths))
        if plan.transcode:
            transcode_result = self._transcode_to_mp4(
                plan,
                paths,
                deps=deps,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
            if transcode_result is not None:
                return transcode_result
        if output_validator is not None:
            validation = output_validator.validate(paths, plan.mode, plan.output_extension)
            if not validation.valid:
                _emit(
                    progress_callback,
                    DownloadProgress(ProgressStage.FAILED, validation.message),
                )
                return DownloadResult(
                    ResultStatus.ERROR,
                    tuple(paths),
                    error_message=validation.message,
                    technical_detail=validation.technical_detail,
                )
            paths[:] = [validation.path] if validation.path is not None else paths
        _emit(
            progress_callback,
            DownloadProgress(
                ProgressStage.VALIDATING,
                "Transferência concluída; aguardando validação do arquivo final.",
            ),
        )
        return DownloadResult(ResultStatus.SUCCESS, tuple(paths))

    def _build_options(
        self,
        plan: DownloadPlan,
        *,
        output_template: str | None,
        deps: DependencyReport | DependencyPaths | None,
        cancel_event: threading.Event,
        progress_callback: ProgressCallback | None,
        paths: list[Path],
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": plan.format_expression,
            "noplaylist": True,
            "overwrites": False,
            "retries": 3,
            "quiet": True,
            # A interface própria exibe o progresso por item. Evita que o
            # progresso interno do yt-dlp apareça no CMD e reinicie por stream.
            "noprogress": True,
            "no_warnings": True,
            "outtmpl": output_template or str(plan.destination / "%(title)s [%(id)s].%(ext)s"),
            "progress_hooks": [
                self._progress_hook(
                    cancel_event,
                    progress_callback,
                    paths,
                    expected_streams=_expected_download_streams(plan),
                ),
            ],
            "postprocessor_hooks": [
                self._postprocessor_hook(cancel_event, progress_callback, paths),
            ],
        }
        if self.logger is not None:
            options["logger"] = SanitizedLogger(self.logger)
        options.update(_dependency_options(deps))
        if plan.mode is DownloadMode.VIDEO:
            if plan.transcode and plan.video_format_id and plan.audio_format_id:
                options["merge_output_format"] = "mkv"
            elif plan.output_container in {"mp4", "webm", "mkv"}:
                options["merge_output_format"] = plan.output_container
        postprocessors = _postprocessor_options(plan)
        if postprocessors:
            options["postprocessors"] = postprocessors
        return options

    def _transcode_to_mp4(
        self,
        plan: DownloadPlan,
        paths: list[Path],
        *,
        deps: DependencyReport | DependencyPaths | None,
        cancel_event: threading.Event,
        progress_callback: ProgressCallback | None,
    ) -> DownloadResult | None:
        ffmpeg = _ffmpeg_executable(deps)
        source = _select_transcode_source(paths)
        if ffmpeg is None or source is None:
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="Não foi possível localizar a mídia para conversão MP4.",
            )
        video_encoder = _select_h264_encoder(ffmpeg)
        if video_encoder is None:
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="O FFmpeg disponível não oferece um codificador H.264 para MP4.",
            )
        output = source.with_suffix(".mp4")
        if output == source:
            output = source.with_name(f"{source.stem} (converted).mp4")
        duration = _probe_media_duration(_ffprobe_executable(deps), source)
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(source),
            "-progress",
            "pipe:1",
            "-nostats",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            video_encoder,
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
        _emit(
            progress_callback,
            DownloadProgress(
                ProgressStage.CONVERTING,
                "Convertendo para MP4...",
                percentage=0,
            ),
        )
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                **hidden_process_kwargs(),
            )
            progress_queue: Queue[str] = Queue()

            def read_progress() -> None:
                stdout = getattr(process, "stdout", None)
                if stdout is None:
                    return
                for line in stdout:
                    progress_queue.put(line.strip())

            progress_reader = threading.Thread(target=read_progress, daemon=True)
            progress_reader.start()
            out_time_us = 0
            last_percentage = 0.0

            def emit_progress_lines() -> None:
                nonlocal last_percentage, out_time_us
                while True:
                    try:
                        line = progress_queue.get_nowait()
                    except Empty:
                        return
                    key, separator, value = line.partition("=")
                    if not separator:
                        continue
                    if key == "out_time_us":
                        try:
                            out_time_us = max(0, int(value))
                        except ValueError:
                            continue
                    if key != "progress" or duration is None:
                        continue
                    percentage = min(99.0, out_time_us / (duration * 10_000))
                    if percentage > last_percentage:
                        last_percentage = percentage
                        _emit(
                            progress_callback,
                            DownloadProgress(
                                ProgressStage.CONVERTING,
                                "Convertendo para MP4...",
                                percentage=percentage,
                            ),
                        )

            while process.poll() is None:
                if cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return DownloadResult(ResultStatus.CANCELLED, tuple(paths))
                emit_progress_lines()
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
            progress_reader.join(timeout=1)
            emit_progress_lines()
        except subprocess.TimeoutExpired:
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="A conversão para MP4 excedeu o tempo esperado.",
            )
        except OSError as exc:
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="Não foi possível iniciar a conversão para MP4.",
                technical_detail=_sanitize_detail(str(exc)),
            )
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read()
        if process.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            return DownloadResult(
                ResultStatus.ERROR,
                tuple(paths),
                error_message="A conversão para MP4 falhou após a transferência.",
                technical_detail=_sanitize_detail(stderr),
            )
        _emit(
            progress_callback,
            DownloadProgress(
                ProgressStage.CONVERTING,
                "Conversão para MP4 concluída.",
                percentage=100,
                phase_complete=True,
            ),
        )
        paths[:] = [path for path in paths if path != source]
        paths.append(output)
        try:
            source.unlink(missing_ok=True)
        except OSError:
            # A mídia intermediária pertence à tarefa atual; se estiver bloqueada,
            # preservá-la é mais seguro do que remover qualquer arquivo externo.
            pass
        return None

    @staticmethod
    def _progress_hook(
        cancel_event: threading.Event,
        callback: ProgressCallback | None,
        paths: list[Path],
        *,
        expected_streams: int = 1,
    ) -> Callable[[dict[str, Any]], None]:
        stream_progress: dict[str, float] = {}
        finished_streams: set[str] = set()
        expected_streams = max(1, expected_streams)

        def hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise DownloadCancelled
            status = data.get("status")
            filename = data.get("filename") or data.get("tmpfilename")
            if isinstance(filename, str):
                path = Path(filename)
                if path not in paths:
                    paths.append(path)
            stream_key = _progress_stream_key(data)
            if status == "downloading":
                downloaded = _int_or_none(data.get("downloaded_bytes"))
                total = _int_or_none(data.get("total_bytes")) or _int_or_none(
                    data.get("total_bytes_estimate")
                )
                stream_percentage = _progress_percentage_from_data(data)
                if stream_percentage is not None:
                    stream_progress[stream_key] = max(
                        stream_progress.get(stream_key, 0.0), stream_percentage
                    )
                percentage = min(
                    99.0,
                    _aggregate_download_percentage(stream_progress, expected_streams),
                )
                _emit(
                    callback,
                    DownloadProgress(
                        ProgressStage.DOWNLOADING,
                        "Baixando mídia...",
                        percentage=percentage,
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        speed=_number_or_none(data.get("speed")),
                        eta=_int_or_none(data.get("eta")),
                    ),
                )
            elif status == "finished":
                stream_progress[stream_key] = 100.0
                finished_streams.add(stream_key)
                phase_complete = len(finished_streams) >= expected_streams
                _emit(
                    callback,
                    DownloadProgress(
                        ProgressStage.DOWNLOADING,
                        "Transferência concluída; finalizando pós-processamento.",
                        percentage=_aggregate_download_percentage(
                            stream_progress, expected_streams
                        ),
                        phase_complete=phase_complete,
                    ),
                )

        return hook

    @staticmethod
    def _postprocessor_hook(
        cancel_event: threading.Event,
        callback: ProgressCallback | None,
        paths: list[Path],
    ) -> Callable[[dict[str, Any]], None]:
        def hook(data: dict[str, Any]) -> None:
            if cancel_event.is_set():
                _emit(
                    callback,
                    DownloadProgress(
                        ProgressStage.CONVERTING,
                        "Finalizando conversão (cancelamento limitado)...",
                    ),
                )
            status = data.get("status")
            name = str(data.get("postprocessor") or data.get("postprocessor_key") or "")
            info = data.get("info_dict")
            if isinstance(info, dict):
                filename = info.get("filepath") or info.get("_filename")
                if isinstance(filename, str):
                    path = Path(filename)
                    if path not in paths:
                        paths.append(path)
            if status == "started":
                stage = (
                    ProgressStage.CONVERTING
                    if "convert" in name.lower() or "audio" in name.lower()
                    else ProgressStage.MERGING
                )
                description = (
                    "Convertendo para MP3..."
                    if "extractaudio" in name.lower()
                    else "Convertendo mídia..."
                    if stage is ProgressStage.CONVERTING
                    else "Mesclando streams..."
                )
                _emit(callback, DownloadProgress(stage, description))
            elif status == "finished":
                _emit(
                    callback,
                    DownloadProgress(ProgressStage.VALIDATING, "Validando arquivo final..."),
                )

        return hook


def _dependency_options(deps: DependencyReport | DependencyPaths | None) -> dict[str, Any]:
    if isinstance(deps, DependencyReport):
        return deps.paths.as_yt_dlp_options()
    if isinstance(deps, DependencyPaths):
        return deps.as_yt_dlp_options()
    return {}


def _ffmpeg_executable(deps: DependencyReport | DependencyPaths | None) -> Path | None:
    if isinstance(deps, DependencyReport):
        location = deps.paths.ffmpeg_location
    elif isinstance(deps, DependencyPaths):
        location = deps.ffmpeg_location
    else:
        location = None
    if location is None:
        return None
    if location.is_file():
        return location
    candidate = location / "ffmpeg.exe"
    return candidate if candidate.is_file() else None


def _ffprobe_executable(deps: DependencyReport | DependencyPaths | None) -> Path | None:
    if not isinstance(deps, DependencyReport):
        return None
    path = deps.by_key("ffprobe").path
    return path if path is not None and path.is_file() else None


def _probe_media_duration(ffprobe: Path | None, source: Path) -> float | None:
    if ffprobe is None:
        return None
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=10,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def _expected_download_streams(plan: DownloadPlan) -> int:
    return 2 if plan.video_format_id and plan.audio_format_id else 1


def _progress_stream_key(data: dict[str, Any]) -> str:
    filename = data.get("filename") or data.get("tmpfilename")
    if isinstance(filename, str) and filename:
        return filename.removesuffix(".part")
    info = data.get("info_dict")
    if isinstance(info, dict):
        format_id = info.get("format_id")
        if isinstance(format_id, str) and format_id:
            return f"format:{format_id}"
    return "stream"


def _progress_percentage_from_data(data: dict[str, Any]) -> float | None:
    downloaded = _int_or_none(data.get("downloaded_bytes"))
    total = _int_or_none(data.get("total_bytes")) or _int_or_none(data.get("total_bytes_estimate"))
    if downloaded is not None and total:
        return min(100.0, downloaded * 100 / total)
    fragment_index = _int_or_none(data.get("fragment_index"))
    fragment_count = _int_or_none(data.get("fragment_count"))
    if fragment_index is not None and fragment_count:
        return min(100.0, fragment_index * 100 / fragment_count)
    return None


def _aggregate_download_percentage(
    stream_progress: dict[str, float], expected_streams: int
) -> float:
    if not stream_progress:
        return 0.0
    divisor = max(expected_streams, len(stream_progress))
    return min(100.0, sum(stream_progress.values()) / divisor)


def _select_transcode_source(paths: list[Path]) -> Path | None:
    """Prefere o contêiner intermediário já mesclado pelo yt-dlp."""
    candidates = [path for path in reversed(paths) if path.is_file()]
    return next((path for path in candidates if path.suffix.lower() == ".mkv"), None) or (
        candidates[0] if candidates else None
    )


def _select_h264_encoder(ffmpeg: Path) -> str | None:
    """Escolhe um codificador H.264 realmente exposto pelo FFmpeg local."""
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=5,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    available = f"{result.stdout}\n{result.stderr}"
    for encoder in ("libx264", "libopenh264", "h264_mf"):
        if re.search(rf"\s{re.escape(encoder)}\s", available):
            return encoder
    return None


def _dependency_error(
    plan: DownloadPlan, deps: DependencyReport | DependencyPaths | None
) -> str | None:
    if not plan.requires_ffmpeg:
        return None
    if isinstance(deps, DependencyReport) and not deps.ffmpeg_ready:
        return "FFmpeg e FFprobe são necessários para unir/converter mídia."
    if isinstance(deps, DependencyPaths) and deps.ffmpeg_location is None:
        return "FFmpeg e FFprobe são necessários para unir/converter mídia."
    if deps is None:
        return "FFmpeg e FFprobe são necessários para unir/converter mídia."
    return None


def _postprocessor_options(plan: DownloadPlan) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for processor in plan.postprocessors:
        options = {key: value for key, value in processor.options}
        if processor.name == "FFmpegExtractAudio":
            result.append({"key": processor.name, **options})
        elif processor.name == "FFmpegTranscode":
            # A transcodificação é executada pelo serviço com argumentos explícitos.
            continue
    return result


def _emit(callback: ProgressCallback | None, event: DownloadProgress) -> None:
    if callback is not None:
        callback(event)


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _number_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _sanitize_detail(detail: str) -> str:
    sanitized = re.sub(r"https?://\S+", "[URL omitida]", detail)
    sanitized = re.sub(
        r"(?i)(cookie|authorization|token|signature)\s*[:=]\s*\S+",
        r"\1=[omitido]",
        sanitized,
    )
    return sanitized[:800]


def _download_error_message(detail: str, url: str = "") -> str:
    lower = detail.lower()
    if any(
        term in lower
        for term in (
            "unavailable",
            "private video",
            "deleted video",
            "you need to log in",
            "login to access",
            "cookies-from-browser",
            "authentication",
            "sign in",
        )
    ):
        if any(
            term in lower
            for term in (
                "you need to log in",
                "login to access",
                "cookies-from-browser",
                "authentication",
                "sign in",
            )
        ):
            return "Este conteúdo exige autenticação para ser acessado neste ambiente."
        return "Vídeo não disponível."
    if "403" in lower or "po token" in lower or "verification" in lower:
        if "twitch.tv" in url.casefold():
            return (
                "A Twitch recusou este download nesta sessão. Analise novamente e tente "
                "outra qualidade."
            )
        return (
            "O YouTube restringiu este download nesta sessão. Atualize dependências "
            "ou tente outro vídeo autorizado."
        )
    if "ffmpeg" in lower or "ffprobe" in lower:
        return "FFmpeg e FFprobe são necessários para unir/converter mídia."
    if "permission" in lower or "access is denied" in lower:
        return "Não foi possível salvar na pasta escolhida."
    if "space" in lower or "disk full" in lower:
        return "Não foi possível salvar na pasta escolhida: verifique o espaço livre."
    if "network" in lower or "connection" in lower or "timed out" in lower:
        return "Não foi possível concluir o download. Verifique sua conexão."
    return "Não foi possível concluir o download."
