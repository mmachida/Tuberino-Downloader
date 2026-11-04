"""Adaptação isolada da API Python do yt-dlp para análise."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.models import ContentCollection, ContentItem, ContentSourceKind, VideoInfo
from app.services.dependencies import DependencyPaths, DependencyReport
from app.services.format_selector import normalize_formats
from app.services.url_validator import (
    UrlValidation,
    validate_instagram_video_url,
    validate_twitch_clip_url,
    validate_twitch_vod_url,
    validate_twitter_video_url,
    validate_youtube_playlist_url,
    validate_youtube_url,
)

_ANALYSIS_SOCKET_TIMEOUT_SECONDS = 15


class _QuietYtDlpLogger:
    """Impede que mensagens técnicas do extrator apareçam no console do app."""

    def debug(self, _message: str) -> None:
        return

    def info(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


class AnalysisErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    UNAVAILABLE = "unavailable"
    LIVE = "live"
    NO_FORMATS = "no_formats"
    EXTRACTION = "extraction"


@dataclass(frozen=True, slots=True)
class AnalysisError(Exception):
    """Erro técnico preservado com mensagem adequada para a UI."""

    code: AnalysisErrorCode
    user_message: str
    technical_detail: str | None = None

    def __str__(self) -> str:
        return self.user_message


class YtDlpService:
    """Executa somente a análise de um vídeo individual."""

    def __init__(self, *, logger: Any | None = None) -> None:
        self.logger = logger

    def analyze_video(
        self,
        url: str,
        deps: DependencyReport | DependencyPaths | None = None,
    ) -> VideoInfo:
        validation = validate_youtube_url(url)
        if not validation.valid or validation.normalized_url is None:
            raise AnalysisError(AnalysisErrorCode.INVALID_URL, validation.message)
        return self._analyze_single(validation, deps, "o vídeo")

    def analyze_twitch(
        self,
        url: str,
        source_kind: ContentSourceKind,
        deps: DependencyReport | DependencyPaths | None = None,
    ) -> VideoInfo:
        if source_kind is ContentSourceKind.TWITCH_VOD:
            validation = validate_twitch_vod_url(url)
        elif source_kind is ContentSourceKind.TWITCH_CLIP:
            validation = validate_twitch_clip_url(url)
        else:
            raise AnalysisError(
                AnalysisErrorCode.INVALID_URL,
                "O tipo de conteúdo da Twitch não é válido.",
            )
        if not validation.valid or validation.normalized_url is None:
            raise AnalysisError(AnalysisErrorCode.INVALID_URL, validation.message)
        return self._analyze_single(validation, deps, "o conteúdo da Twitch", twitch=True)

    def analyze_twitter(
        self,
        url: str,
        deps: DependencyReport | DependencyPaths | None = None,
    ) -> VideoInfo:
        validation = validate_twitter_video_url(url)
        if not validation.valid or validation.normalized_url is None:
            raise AnalysisError(AnalysisErrorCode.INVALID_URL, validation.message)
        return self._analyze_single(validation, deps, "o vídeo do Twitter/X", twitter=True)

    def analyze_instagram(
        self,
        url: str,
        deps: DependencyReport | DependencyPaths | None = None,
    ) -> VideoInfo:
        validation = validate_instagram_video_url(url)
        if not validation.valid or validation.normalized_url is None:
            raise AnalysisError(AnalysisErrorCode.INVALID_URL, validation.message)
        return self._analyze_single(validation, deps, "o vídeo do Instagram")

    def _analyze_single(
        self,
        validation: UrlValidation,
        deps: DependencyReport | DependencyPaths | None,
        subject: str,
        *,
        twitch: bool = False,
        twitter: bool = False,
    ) -> VideoInfo:

        options: dict[str, Any] = {
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": _ANALYSIS_SOCKET_TIMEOUT_SECONDS,
            "retries": 1,
            "extractor_retries": 1,
        }
        options.update(_dependency_options(deps))
        options["logger"] = self.logger or _QuietYtDlpLogger()

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(validation.normalized_url, download=False)
        except DownloadError as exc:
            raise self._map_download_error(exc) from exc
        except Exception as exc:
            detail = _sanitize_detail(str(exc))
            raise AnalysisError(
                AnalysisErrorCode.EXTRACTION,
                f"Não foi possível consultar {subject}. Verifique sua conexão.",
                detail,
            ) from exc

        return self._build_video_info(info, validation, twitch=twitch, twitter=twitter)

    def analyze_playlist(
        self,
        url: str,
        deps: DependencyReport | DependencyPaths | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ContentCollection:
        """Lista itens de uma playlist sem consultar formatos ou baixar mídia."""
        validation = validate_youtube_playlist_url(url)
        if not validation.valid or validation.normalized_url is None:
            raise AnalysisError(AnalysisErrorCode.INVALID_URL, validation.message)

        options: dict[str, Any] = {
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": _ANALYSIS_SOCKET_TIMEOUT_SECONDS,
            "retries": 1,
            "extractor_retries": 1,
        }
        options.update(_dependency_options(deps))
        options["logger"] = self.logger or _QuietYtDlpLogger()

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(validation.normalized_url, download=False)
        except DownloadError as exc:
            raise self._map_download_error(exc) from exc
        except Exception as exc:
            detail = _sanitize_detail(str(exc))
            raise AnalysisError(
                AnalysisErrorCode.EXTRACTION,
                "Não foi possível consultar a playlist. Verifique sua conexão.",
                detail,
            ) from exc

        if not isinstance(info, dict):
            raise AnalysisError(
                AnalysisErrorCode.EXTRACTION,
                "A resposta do YouTube não trouxe uma playlist válida.",
            )
        entries = info.get("entries")
        if entries is None:
            raise AnalysisError(
                AnalysisErrorCode.EXTRACTION,
                "A URL não retornou uma playlist do YouTube.",
            )
        if not isinstance(entries, list):
            entries = list(entries)

        items: list[ContentItem] = []
        total_entries = len(entries)
        if progress_callback is not None:
            progress_callback(0, total_entries)
        progress_step = max(1, total_entries // 100) if total_entries else 1
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                item = None
            else:
                item = _content_item_from_entry(entry)
            if item is not None:
                items.append(item)
            if progress_callback is not None and (
                index == total_entries or index % progress_step == 0
            ):
                progress_callback(index, total_entries)
        if not items:
            raise AnalysisError(
                AnalysisErrorCode.NO_FORMATS,
                "Nenhum vídeo disponível foi encontrado na playlist.",
            )

        title = _string_or_none(info.get("title")) or "Playlist do YouTube"
        return ContentCollection(
            source_kind=ContentSourceKind.PLAYLIST,
            source_url=validation.normalized_url,
            title=title,
            items=tuple(items),
        )

    def analyze_source(
        self,
        url: str,
        source_kind: ContentSourceKind,
        deps: DependencyReport | DependencyPaths | None = None,
    ) -> VideoInfo | ContentCollection:
        if source_kind is ContentSourceKind.PLAYLIST:
            return self.analyze_playlist(url, deps)
        if source_kind in {ContentSourceKind.TWITCH_VOD, ContentSourceKind.TWITCH_CLIP}:
            return self.analyze_twitch(url, source_kind, deps)
        if source_kind is ContentSourceKind.TWITTER_VIDEO:
            return self.analyze_twitter(url, deps)
        if source_kind is ContentSourceKind.INSTAGRAM_VIDEO:
            return self.analyze_instagram(url, deps)
        return self.analyze_video(url, deps)

    def _build_video_info(
        self,
        info: Any,
        validation: UrlValidation,
        *,
        twitch: bool = False,
        twitter: bool = False,
    ) -> VideoInfo:
        if not isinstance(info, dict):
            raise AnalysisError(
                AnalysisErrorCode.EXTRACTION,
                "A resposta do YouTube não trouxe metadados válidos.",
            )
        if info.get("entries") is not None:
            raise AnalysisError(
                AnalysisErrorCode.UNAVAILABLE,
                "A análise retornou uma playlist no modo de vídeo; selecione "
                "Playlist e analise novamente.",
            )

        live_status = _string_or_none(info.get("live_status"))
        if live_status in {"is_live", "is_upcoming"} or info.get("is_live") is True:
            raise AnalysisError(
                AnalysisErrorCode.LIVE,
                "Lives em andamento não são compatíveis nesta versão.",
                live_status,
            )

        raw_formats = info.get("formats")
        if not isinstance(raw_formats, list):
            raise AnalysisError(
                AnalysisErrorCode.NO_FORMATS,
                "Nenhum formato compatível foi disponibilizado para este vídeo.",
            )

        raw_format_items = (
            _normalize_twitch_format(item)
            if twitch and isinstance(item, dict)
            else _normalize_twitter_format(item)
            if twitter and isinstance(item, dict)
            else item
            for item in raw_formats
            if isinstance(item, dict)
        )
        formats = normalize_formats(raw_format_items)
        if not formats:
            raise AnalysisError(
                AnalysisErrorCode.NO_FORMATS,
                "Nenhum formato compatível foi disponibilizado para este vídeo.",
            )

        thumbnail = _string_or_none(info.get("thumbnail"))
        if thumbnail is None and isinstance(info.get("thumbnails"), list):
            for candidate in reversed(info["thumbnails"]):
                if isinstance(candidate, dict):
                    thumbnail = _string_or_none(candidate.get("url"))
                    if thumbnail:
                        break

        return VideoInfo(
            video_id=_string_or_none(info.get("id")) or validation.video_id or "video",
            webpage_url=_string_or_none(info.get("webpage_url")) or validation.normalized_url or "",
            title=_string_or_none(info.get("title")) or "Título indisponível",
            uploader=_string_or_none(info.get("uploader")) or _string_or_none(info.get("channel")),
            duration=_number_or_none(info.get("duration")),
            thumbnail=thumbnail,
            live_status=live_status,
            formats=formats,
        )

    @staticmethod
    def _map_download_error(exc: DownloadError) -> AnalysisError:
        detail = _sanitize_detail(str(exc))
        lower = detail.lower()
        if any(
            term in lower
            for term in (
                "private",
                "unavailable",
                "drm",
                "members-only",
                "you need to log in",
                "login to access",
                "cookies-from-browser",
                "authentication",
                "sign in",
            )
        ):
            return AnalysisError(
                AnalysisErrorCode.UNAVAILABLE,
                "Este conteúdo exige autenticação para ser acessado neste ambiente.",
                detail,
            )
        return AnalysisError(
            AnalysisErrorCode.EXTRACTION,
            "Não foi possível consultar o vídeo. Verifique sua conexão.",
            detail,
        )


def _dependency_options(deps: DependencyReport | DependencyPaths | None) -> dict[str, Any]:
    if isinstance(deps, DependencyReport):
        return deps.paths.as_yt_dlp_options()
    if isinstance(deps, DependencyPaths):
        return deps.as_yt_dlp_options()
    return {}


def _normalize_twitch_format(raw: dict[str, Any]) -> dict[str, Any]:
    """Completa codecs omitidos pelos formatos MP4 diretos dos clips da Twitch."""
    normalized = dict(raw)
    is_direct_mp4 = (
        _string_or_none(raw.get("ext")) == "mp4"
        and _string_or_none(raw.get("video_ext")) == "mp4"
        and _number_or_none(raw.get("height")) is not None
        and _string_or_none(raw.get("vcodec")) is None
        and _string_or_none(raw.get("acodec")) is None
    )
    if is_direct_mp4:
        normalized["vcodec"] = "h264"
        normalized["acodec"] = "aac"
    return normalized


def _normalize_twitter_format(raw: dict[str, Any]) -> dict[str, Any]:
    """Completa codecs omitidos nas faixas MP4/HLS retornadas pelo X."""
    normalized = dict(raw)
    is_audio_mp4 = (
        _string_or_none(raw.get("audio_ext")) == "mp4"
        and _string_or_none(raw.get("video_ext")) in {None, "none"}
        and _string_or_none(raw.get("acodec")) in {None, "none"}
    )
    if is_audio_mp4:
        normalized["acodec"] = "aac"
    return normalized


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _content_item_from_entry(entry: dict[str, Any]) -> ContentItem | None:
    video_id = _string_or_none(entry.get("id")) or _string_or_none(entry.get("url"))
    if video_id is None or not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return None
    webpage_url = _string_or_none(entry.get("webpage_url"))
    if webpage_url is None:
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"
    entry_title = _string_or_none(entry.get("title"))
    title = entry_title or f"Vídeo {video_id}"
    # Entradas sem título e sem os demais metadados são como o yt-dlp
    # representa vídeos removidos quando a playlist é analisada em modo flat.
    metadata_missing = (
        entry_title is None
        and _string_or_none(entry.get("uploader")) is None
        and _string_or_none(entry.get("channel")) is None
        and _string_or_none(entry.get("thumbnail")) is None
        and _number_or_none(entry.get("duration")) is None
    )
    available = not metadata_missing and _entry_is_available(entry, title)
    thumbnail = _string_or_none(entry.get("thumbnail"))
    if thumbnail is None and isinstance(entry.get("thumbnails"), list):
        for candidate in reversed(entry["thumbnails"]):
            if isinstance(candidate, dict):
                thumbnail = _string_or_none(candidate.get("url"))
                if thumbnail:
                    break
    if thumbnail is None and available:
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return ContentItem(
        video_id=video_id,
        webpage_url=webpage_url,
        title=title,
        uploader=_string_or_none(entry.get("uploader")) or _string_or_none(entry.get("channel")),
        duration=_number_or_none(entry.get("duration")),
        thumbnail=thumbnail,
        selected=available,
        available=available,
        availability_error="Não disponível" if not available else None,
    )


def _entry_is_available(entry: dict[str, Any], title: str) -> bool:
    if entry.get("is_unavailable") is True:
        return False
    availability = _string_or_none(entry.get("availability"))
    if availability is not None and availability.casefold() in {
        "private",
        "needs_auth",
        "subscriber_only",
        "premium_only",
        "unavailable",
    }:
        return False
    lower_title = title.casefold()
    return not any(
        marker in lower_title
        for marker in (
            "private video",
            "deleted video",
            "video unavailable",
            "this video is unavailable",
            "vídeo indisponível",
        )
    )


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
