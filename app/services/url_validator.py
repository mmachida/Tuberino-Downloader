"""Validação offline de URLs individuais do YouTube."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit, urlunsplit


class UrlKind(StrEnum):
    WATCH = "watch"
    SHORTS = "shorts"
    LIVE = "live"
    PLAYLIST = "playlist"
    TWITCH_VOD = "twitch_vod"
    TWITCH_CLIP = "twitch_clip"
    TWITTER_VIDEO = "twitter_video"
    INSTAGRAM_VIDEO = "instagram_video"


@dataclass(frozen=True, slots=True)
class UrlValidation:
    """Resultado explicável da validação de uma URL fornecida pelo usuário."""

    valid: bool
    message: str
    normalized_url: str | None = None
    video_id: str | None = None
    kind: UrlKind | None = None
    has_playlist_parameter: bool = False
    playlist_id: str | None = None


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")


def validate_youtube_url(raw_url: str) -> UrlValidation:
    """Valida uma URL de vídeo YouTube sem consultar a rede."""
    value = raw_url.strip()
    if not value:
        return _invalid()

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return _invalid()

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return _invalid()
    if port not in (None, 443) or parsed.username is not None or parsed.password is not None:
        return _invalid()

    host = parsed.hostname.lower().rstrip(".")
    if not _is_allowed_host(host):
        return _invalid()

    query = parse_qs(parsed.query, keep_blank_values=True)
    has_list = "list" in query

    if host == "youtu.be":
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) != 1:
            return _invalid()
        video_id = segments[0]
        kind = UrlKind.WATCH
        canonical = urlunsplit(("https", "youtu.be", f"/{video_id}", "", ""))
    else:
        segments = [segment for segment in parsed.path.split("/") if segment]
        path = parsed.path.rstrip("/")
        if path == "/watch":
            values = query.get("v", [])
            if len(values) != 1 or not values[0]:
                if has_list:
                    return _playlist_only()
                return _invalid()
            video_id = values[0]
            kind = UrlKind.WATCH
            canonical = urlunsplit(("https", "www.youtube.com", "/watch", f"v={video_id}", ""))
        elif len(segments) == 2 and segments[0] in {"shorts", "live"}:
            video_id = segments[1]
            kind = UrlKind.SHORTS if segments[0] == "shorts" else UrlKind.LIVE
            canonical = urlunsplit(
                ("https", "www.youtube.com", f"/{segments[0]}/{video_id}", "", "")
            )
        elif segments and segments[0] == "playlist":
            return _playlist_only()
        else:
            return _invalid()

    if not _VIDEO_ID.fullmatch(video_id):
        return _invalid()
    return UrlValidation(
        True, "URL de vídeo do YouTube válida.", canonical, video_id, kind, has_list
    )


def is_valid_youtube_url(raw_url: str) -> bool:
    """Atalho para habilitar/desabilitar ações da interface."""
    return validate_youtube_url(raw_url).valid


def validate_youtube_playlist_url(raw_url: str) -> UrlValidation:
    """Valida uma URL que identifica uma playlist do YouTube."""
    value = raw_url.strip()
    if not value:
        return _invalid_playlist()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return _invalid_playlist()

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return _invalid_playlist()
    if port not in (None, 443) or parsed.username is not None or parsed.password is not None:
        return _invalid_playlist()
    host = parsed.hostname.lower().rstrip(".")
    if not _is_allowed_host(host) or host == "youtu.be":
        return _invalid_playlist()

    query = parse_qs(parsed.query, keep_blank_values=True)
    playlist_values = query.get("list", [])
    if len(playlist_values) != 1 or not _VIDEO_ID.fullmatch(playlist_values[0]):
        return _invalid_playlist()
    path = parsed.path.rstrip("/")
    if path not in {"/playlist", "/watch"}:
        return _invalid_playlist()
    playlist_id = playlist_values[0]
    canonical = urlunsplit(("https", "www.youtube.com", "/playlist", f"list={playlist_id}", ""))
    return UrlValidation(
        True,
        "URL de playlist do YouTube válida.",
        canonical,
        kind=UrlKind.PLAYLIST,
        has_playlist_parameter=True,
        playlist_id=playlist_id,
    )


def is_valid_youtube_playlist_url(raw_url: str) -> bool:
    return validate_youtube_playlist_url(raw_url).valid


def validate_twitch_vod_url(raw_url: str) -> UrlValidation:
    """Valida uma URL de VOD da Twitch sem consultar a rede."""
    return _validate_twitch_url(raw_url, UrlKind.TWITCH_VOD)


def validate_twitch_clip_url(raw_url: str) -> UrlValidation:
    """Valida uma URL de clip da Twitch sem consultar a rede."""
    return _validate_twitch_url(raw_url, UrlKind.TWITCH_CLIP)


def is_valid_twitch_vod_url(raw_url: str) -> bool:
    return validate_twitch_vod_url(raw_url).valid


def is_valid_twitch_clip_url(raw_url: str) -> bool:
    return validate_twitch_clip_url(raw_url).valid


def validate_twitter_video_url(raw_url: str) -> UrlValidation:
    """Valida uma URL pública de postagem com vídeo no Twitter/X."""
    value = raw_url.strip()
    invalid_message = "Cole um link válido de vídeo do Twitter/X."
    if not value:
        return UrlValidation(False, invalid_message)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return UrlValidation(False, invalid_message)

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return UrlValidation(False, invalid_message)
    if port not in (None, 443) or parsed.username is not None or parsed.password is not None:
        return UrlValidation(False, invalid_message)
    host = parsed.hostname.lower().rstrip(".")
    if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return UrlValidation(False, invalid_message)

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 3 or segments[1].casefold() != "status" or not segments[2].isdigit():
        return UrlValidation(False, invalid_message)

    status_id = segments[2]
    canonical = urlunsplit(("https", "x.com", f"/{segments[0]}/status/{status_id}", "", ""))
    return UrlValidation(
        True,
        "URL de vídeo do Twitter/X válida.",
        canonical,
        status_id,
        UrlKind.TWITTER_VIDEO,
    )


def is_valid_twitter_video_url(raw_url: str) -> bool:
    return validate_twitter_video_url(raw_url).valid


def validate_instagram_video_url(raw_url: str) -> UrlValidation:
    """Valida uma URL pública de publicação/reel de vídeo do Instagram."""
    value = raw_url.strip()
    invalid_message = "Cole um link válido de vídeo do Instagram."
    if not value:
        return UrlValidation(False, invalid_message)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return UrlValidation(False, invalid_message)

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return UrlValidation(False, invalid_message)
    if port not in (None, 443) or parsed.username is not None or parsed.password is not None:
        return UrlValidation(False, invalid_message)
    host = parsed.hostname.lower().rstrip(".")
    if host not in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        return UrlValidation(False, invalid_message)

    segments = [segment for segment in parsed.path.split("/") if segment]
    kind = segments[0].casefold()
    if kind in {"p", "reel", "reels", "tv"}:
        if len(segments) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]{3,}", segments[1]):
            return UrlValidation(False, invalid_message)
        shortcode = segments[1]
        canonical_path = f"/{kind}/{shortcode}"
    elif kind == "stories":
        if (
            len(segments) != 3
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,}", segments[1])
            or not re.fullmatch(r"[A-Za-z0-9_-]{3,}", segments[2])
        ):
            return UrlValidation(False, invalid_message)
        shortcode = segments[2]
        canonical_path = f"/stories/{segments[1]}/{shortcode}"
    else:
        return UrlValidation(False, invalid_message)

    canonical = urlunsplit(("https", "www.instagram.com", canonical_path, "", ""))
    return UrlValidation(
        True,
        "URL de vídeo do Instagram válida.",
        canonical,
        shortcode,
        UrlKind.INSTAGRAM_VIDEO,
    )


def is_valid_instagram_video_url(raw_url: str) -> bool:
    return validate_instagram_video_url(raw_url).valid


def validate_supported_video_url(raw_url: str) -> UrlValidation:
    """Valida uma URL de vídeo aceita pelos downloads individuais."""
    for validator in (
        validate_youtube_url,
        validate_twitch_vod_url,
        validate_twitch_clip_url,
        validate_twitter_video_url,
        validate_instagram_video_url,
    ):
        result = validator(raw_url)
        if result.valid:
            return result
    return UrlValidation(
        False,
        "Cole um link válido de vídeo do YouTube, Twitch, Twitter/X ou Instagram.",
    )


def _is_allowed_host(host: str) -> bool:
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _validate_twitch_url(raw_url: str, kind: UrlKind) -> UrlValidation:
    value = raw_url.strip()
    invalid_message = (
        "Cole um link válido de VOD da Twitch."
        if kind is UrlKind.TWITCH_VOD
        else "Cole um link válido de clip da Twitch."
    )
    if not value:
        return UrlValidation(False, invalid_message)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return UrlValidation(False, invalid_message)

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return UrlValidation(False, invalid_message)
    if port not in (None, 443) or parsed.username is not None or parsed.password is not None:
        return UrlValidation(False, invalid_message)
    if parsed.hostname.lower().rstrip(".") not in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
        return UrlValidation(False, invalid_message)

    segments = [segment for segment in parsed.path.split("/") if segment]
    if kind is UrlKind.TWITCH_VOD:
        if len(segments) != 2 or segments[0].casefold() != "videos" or not segments[1].isdigit():
            return UrlValidation(False, invalid_message)
        identifier = segments[1]
        canonical_path = f"/videos/{identifier}"
    else:
        if (
            len(segments) != 3
            or segments[1].casefold() != "clip"
            or not re.fullmatch(r"[A-Za-z0-9_-]{6,}", segments[2])
        ):
            return UrlValidation(False, invalid_message)
        identifier = segments[2]
        canonical_path = f"/{segments[0]}/clip/{identifier}"

    canonical = urlunsplit(("https", "www.twitch.tv", canonical_path, "", ""))
    message = (
        "URL de VOD da Twitch válida."
        if kind is UrlKind.TWITCH_VOD
        else "URL de clip da Twitch válida."
    )
    return UrlValidation(True, message, canonical, identifier, kind)


def _invalid() -> UrlValidation:
    return UrlValidation(False, "Cole um link válido de vídeo do YouTube.")


def _invalid_playlist() -> UrlValidation:
    return UrlValidation(False, "Cole um link válido de playlist do YouTube.")


def _playlist_only() -> UrlValidation:
    return UrlValidation(
        False,
        "No modo Vídeo, selecione uma URL de vídeo em vez de uma playlist.",
        has_playlist_parameter=True,
    )
