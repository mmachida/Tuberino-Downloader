"""Modelos de domínio independentes da UI e do yt-dlp."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class DownloadMode(StrEnum):
    VIDEO = "VIDEO"
    MP3 = "MP3"


class ContentSourceKind(StrEnum):
    VIDEO = "video"
    PLAYLIST = "playlist"
    TWITCH_VOD = "twitch_vod"
    TWITCH_CLIP = "twitch_clip"
    TWITTER_VIDEO = "twitter_video"
    INSTAGRAM_VIDEO = "instagram_video"


class PlaylistQuality(StrEnum):
    BEST = "best"
    WORST = "worst"


class AppState(StrEnum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    READY = "READY"
    DOWNLOADING = "DOWNLOADING"
    POSTPROCESSING = "POSTPROCESSING"
    VALIDATING = "VALIDATING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class OutputProfile(StrEnum):
    MP4_COMPATIBLE = "mp4_compatible"
    ORIGINAL = "original"
    CONVERT_MP4 = "convert_mp4"


class StreamKind(StrEnum):
    VIDEO_ONLY = "video_only"
    AUDIO_ONLY = "audio_only"
    VIDEO_AUDIO = "video_audio"


class ProgressStage(StrEnum):
    ANALYZING = "ANALYZING"
    DOWNLOADING = "DOWNLOADING"
    MERGING = "MERGING"
    CONVERTING = "CONVERTING"
    VALIDATING = "VALIDATING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class FormatOption:
    """Representação enxuta de um stream real retornado pelo yt-dlp."""

    format_id: str
    stream_kind: StreamKind
    ext: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    protocol: str | None = None
    filesize: int | None = None
    filesize_approx: int | None = None
    tbr: float | None = None
    vbr: float | None = None
    abr: float | None = None
    dynamic_range: str | None = None
    format_note: str | None = None
    audio_format_id: str | None = None
    label: str = ""
    available: bool = True

    def __post_init__(self) -> None:
        if not self.format_id.strip():
            raise ValueError("format_id não pode ser vazio")
        if self.width is not None and self.width <= 0:
            raise ValueError("width deve ser positivo")
        if self.height is not None and self.height <= 0:
            raise ValueError("height deve ser positivo")
        if self.fps is not None and self.fps <= 0:
            raise ValueError("fps deve ser positivo")
        if self.filesize is not None and self.filesize < 0:
            raise ValueError("filesize não pode ser negativo")
        if self.filesize_approx is not None and self.filesize_approx < 0:
            raise ValueError("filesize_approx não pode ser negativo")

    @property
    def has_video(self) -> bool:
        return self.stream_kind in (StreamKind.VIDEO_ONLY, StreamKind.VIDEO_AUDIO)

    @property
    def has_audio(self) -> bool:
        return self.stream_kind in (StreamKind.AUDIO_ONLY, StreamKind.VIDEO_AUDIO)

    @property
    def estimated_size(self) -> int | None:
        return self.filesize if self.filesize is not None else self.filesize_approx


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Metadados de apresentação e opções já normalizadas para a UI."""

    video_id: str
    webpage_url: str
    title: str
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    live_status: str | None = None
    formats: tuple[FormatOption, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.video_id.strip():
            raise ValueError("video_id não pode ser vazio")
        if not self.webpage_url.strip():
            raise ValueError("webpage_url não pode ser vazio")
        if not self.title.strip():
            raise ValueError("title não pode ser vazio")
        if self.duration is not None and self.duration < 0:
            raise ValueError("duration não pode ser negativa")

    @property
    def video_options(self) -> tuple[FormatOption, ...]:
        return tuple(option for option in self.formats if option.has_video)

    @property
    def audio_options(self) -> tuple[FormatOption, ...]:
        return tuple(option for option in self.formats if option.has_audio and not option.has_video)


@dataclass(frozen=True, slots=True)
class ContentItem:
    """Item visualizável e selecionável de vídeo ou playlist."""

    video_id: str
    webpage_url: str
    title: str
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    formats: tuple[FormatOption, ...] = field(default_factory=tuple)
    selected: bool = True
    available: bool = True
    availability_error: str | None = None

    def __post_init__(self) -> None:
        if not self.video_id.strip():
            raise ValueError("video_id não pode ser vazio")
        if not self.webpage_url.strip():
            raise ValueError("webpage_url não pode ser vazio")
        if not self.title.strip():
            raise ValueError("title não pode ser vazio")
        if self.duration is not None and self.duration < 0:
            raise ValueError("duration não pode ser negativa")
        if not self.available and self.selected:
            object.__setattr__(self, "selected", False)

    def as_video_info(self) -> VideoInfo:
        return VideoInfo(
            video_id=self.video_id,
            webpage_url=self.webpage_url,
            title=self.title,
            uploader=self.uploader,
            duration=self.duration,
            thumbnail=self.thumbnail,
            formats=self.formats,
        )


@dataclass(frozen=True, slots=True)
class ContentCollection:
    """Resultado de uma análise, com um ou muitos itens selecionáveis."""

    source_kind: ContentSourceKind
    source_url: str
    title: str
    items: tuple[ContentItem, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.source_url.strip():
            raise ValueError("source_url não pode ser vazio")
        if not self.items:
            raise ValueError("content collection precisa de pelo menos um item")

    @property
    def selected_items(self) -> tuple[ContentItem, ...]:
        return tuple(item for item in self.items if item.selected and item.available)


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """Pedido validado antes de construir um plano de execução."""

    video_id: str
    url: str
    mode: DownloadMode
    destination: Path
    selected_format: FormatOption | None = None
    profile: OutputProfile = OutputProfile.MP4_COMPATIBLE
    mp3_bitrate: int = 192

    def __post_init__(self) -> None:
        if not self.video_id.strip() or not self.url.strip():
            raise ValueError("video_id e url são obrigatórios")
        if self.mode is DownloadMode.MP3 and self.mp3_bitrate not in {128, 192, 320}:
            raise ValueError("mp3_bitrate deve ser 128, 192 ou 320")
        if self.destination == Path(""):
            raise ValueError("destination é obrigatório")


@dataclass(frozen=True, slots=True)
class PostProcessorSpec:
    """Descrição serializável de um pós-processador, sem depender do yt-dlp."""

    name: str
    options: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DownloadPlan:
    """Plano imutável de formatos e pós-processamento."""

    mode: DownloadMode
    format_expression: str
    destination: Path
    output_extension: str | None
    output_container: str
    video_format_id: str | None = None
    audio_format_id: str | None = None
    profile: OutputProfile | None = None
    postprocessors: tuple[PostProcessorSpec, ...] = field(default_factory=tuple)
    requires_ffmpeg: bool = False
    transcode: bool = False
    messages: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.format_expression.strip():
            raise ValueError("format_expression não pode ser vazio")
        if self.output_extension is not None and not self.output_extension.strip().startswith("."):
            raise ValueError("output_extension deve começar com ponto")
        if self.mode is DownloadMode.VIDEO and not self.video_format_id:
            raise ValueError("plano de vídeo precisa de video_format_id")
        if self.mode is DownloadMode.MP3:
            if not self.audio_format_id:
                raise ValueError("plano MP3 precisa de audio_format_id")
            if self.output_extension.lower() != ".mp3":
                raise ValueError("plano MP3 deve produzir .mp3")
        if self.transcode and not self.requires_ffmpeg:
            raise ValueError("transcode requer FFmpeg")


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    """Evento de progresso sem dependência de widgets Qt."""

    stage: ProgressStage
    description: str
    percentage: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    item_id: str | None = None
    phase_complete: bool = False

    def __post_init__(self) -> None:
        if self.percentage is not None and not 0 <= self.percentage <= 100:
            raise ValueError("percentage deve estar entre 0 e 100")
        if self.downloaded_bytes is not None and self.downloaded_bytes < 0:
            raise ValueError("downloaded_bytes não pode ser negativo")
        if self.total_bytes is not None and self.total_bytes < 0:
            raise ValueError("total_bytes não pode ser negativo")


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Resultado físico da tarefa após a validação do arquivo final."""

    status: ResultStatus
    final_paths: tuple[Path, ...] = field(default_factory=tuple)
    error_message: str | None = None
    technical_detail: str | None = None

    @property
    def primary_path(self) -> Path | None:
        return self.final_paths[0] if self.final_paths else None
