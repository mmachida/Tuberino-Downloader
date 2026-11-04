"""Normalização pura dos formatos retornados pelo yt-dlp."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.models import (
    DownloadMode,
    DownloadPlan,
    FormatOption,
    OutputProfile,
    PlaylistQuality,
    PostProcessorSpec,
    StreamKind,
    VideoInfo,
)


class FormatPlanningError(ValueError):
    """A escolha do usuário não pode ser executada com os formatos analisados."""


def is_mp4_compatible_choice(video_info: VideoInfo, choice: FormatOption | str) -> bool:
    """Indica se uma qualidade pode ser baixada no perfil MP4 compatível."""
    try:
        selected = _resolve_choice(video_info, choice)
    except FormatPlanningError:
        return False
    if _is_mp4_compatible(selected):
        return True
    if selected.stream_kind is StreamKind.VIDEO_AUDIO:
        return False
    return _is_video_mp4_compatible(selected) and any(
        _is_aac_audio(option) for option in video_info.audio_options
    )


def normalize_formats(raw_formats: Iterable[dict[str, Any]]) -> tuple[FormatOption, ...]:
    """Converte formatos reais em opções enxutas, sem guardar URLs assinadas."""
    candidates: list[FormatOption] = []
    for raw in raw_formats:
        option = _to_option(raw)
        if option is not None:
            candidates.append(option)

    deduplicated: dict[tuple[Any, ...], FormatOption] = {}
    for option in candidates:
        key = _presentation_key(option)
        current = deduplicated.get(key)
        if current is None or _quality_key(option) > _quality_key(current):
            deduplicated[key] = option

    return tuple(sorted(deduplicated.values(), key=_sort_key, reverse=True))


def build_video_plan(
    video_info: VideoInfo,
    choice: FormatOption | str,
    profile: OutputProfile,
    destination: Path = Path("."),
) -> DownloadPlan:
    """Cria um plano determinístico para a qualidade exata escolhida."""
    selected = _resolve_choice(video_info, choice)
    if not selected.has_video:
        raise FormatPlanningError("A qualidade escolhida não contém vídeo.")

    compatible = _is_mp4_compatible(selected)
    if profile is OutputProfile.MP4_COMPATIBLE and not compatible:
        if selected.stream_kind is StreamKind.VIDEO_AUDIO:
            raise FormatPlanningError(
                "A qualidade escolhida não tem combinação MP4 compatível. "
                "Escolha Formato original ou Converter para MP4."
            )
        if not _is_video_mp4_compatible(selected):
            raise FormatPlanningError(
                "A qualidade escolhida não tem vídeo H.264 compatível com MP4. "
                "Escolha Formato original ou Converter para MP4."
            )
        audio = _choose_audio(video_info, prefer_mp4=True)
        if audio is None or not _is_aac_audio(audio):
            raise FormatPlanningError(
                "Não há áudio AAC/M4A compatível para esta qualidade no perfil MP4. "
                "Escolha Formato original ou Converter para MP4."
            )
        return _merged_plan(
            selected,
            audio,
            destination,
            extension=".mp4",
            container="mp4",
            profile=profile,
            messages=("Vídeo H.264 e áudio AAC serão mesclados sem recodificação.",),
        )

    if profile is OutputProfile.MP4_COMPATIBLE:
        if selected.stream_kind is StreamKind.VIDEO_AUDIO:
            return _single_stream_plan(
                selected,
                destination,
                extension=".mp4",
                container="mp4",
                profile=profile,
                messages=("Formato MP4 compatível selecionado.",),
            )
        audio = _choose_audio(video_info, prefer_mp4=True)
        if audio is None or not _is_aac_audio(audio):
            raise FormatPlanningError("A qualidade escolhida não tem áudio compatível disponível.")
        return _merged_plan(
            selected,
            audio,
            destination,
            extension=".mp4",
            container="mp4",
            profile=profile,
            messages=("Vídeo e áudio compatíveis serão mesclados sem recodificação.",),
        )

    if profile is OutputProfile.ORIGINAL:
        if selected.stream_kind is StreamKind.VIDEO_AUDIO:
            extension = _container_extension(selected.ext)
            return _single_stream_plan(
                selected,
                destination,
                extension=extension,
                container=extension.removeprefix("."),
                profile=profile,
                messages=("Codecs e contêiner originais serão preservados.",),
            )
        audio = _choose_audio(video_info, prefer_mp4=False)
        if audio is None:
            raise FormatPlanningError("Não há faixa de áudio disponível para esta qualidade.")
        extension = _original_merge_extension(selected, audio)
        return _merged_plan(
            selected,
            audio,
            destination,
            extension=extension,
            container=extension.removeprefix("."),
            profile=profile,
            messages=("O contêiner original compatível será preservado.",),
        )

    if profile is OutputProfile.CONVERT_MP4:
        if selected.stream_kind is StreamKind.VIDEO_AUDIO:
            expression = selected.format_id
            audio = None
        else:
            audio = _choose_audio(video_info, prefer_mp4=False)
            if audio is None:
                raise FormatPlanningError(
                    "Não há faixa de áudio disponível para converter esta qualidade."
                )
            expression = f"{selected.format_id}+{audio.format_id}"
        if compatible and selected.ext == "mp4":
            return DownloadPlan(
                mode=DownloadMode.VIDEO,
                format_expression=expression,
                destination=destination,
                output_extension=".mp4",
                output_container="mp4",
                video_format_id=selected.format_id,
                audio_format_id=audio.format_id if audio else None,
                profile=profile,
                requires_ffmpeg=audio is not None,
                messages=(
                    "A combinação já é compatível com MP4; nenhuma recodificação é necessária.",
                ),
            )
        return DownloadPlan(
            mode=DownloadMode.VIDEO,
            format_expression=expression,
            destination=destination,
            output_extension=".mp4",
            output_container="mp4",
            video_format_id=selected.format_id,
            audio_format_id=audio.format_id if audio else None,
            profile=profile,
            postprocessors=(
                PostProcessorSpec(
                    "FFmpegTranscode",
                    (("video_codec", "libx264"), ("audio_codec", "aac")),
                ),
            ),
            requires_ffmpeg=True,
            transcode=True,
            messages=(
                "A qualidade será mantida com conversão explícita para MP4; "
                "isso pode demorar e reduzir a qualidade.",
            ),
        )

    raise FormatPlanningError("Perfil de saída desconhecido.")


def build_audio_plan(
    video_info: VideoInfo,
    bitrate: int = 192,
    destination: Path = Path("."),
    *,
    ffmpeg_available: bool = True,
) -> DownloadPlan:
    """Cria um plano MP3 usando apenas a melhor faixa de áudio real."""
    if bitrate not in {128, 192, 320}:
        raise FormatPlanningError("O bitrate MP3 deve ser 128, 192 ou 320 kbps.")
    if not ffmpeg_available:
        raise FormatPlanningError("FFmpeg e FFprobe são necessários para converter mídia.")
    audio = _choose_audio(video_info, prefer_mp4=False)
    if audio is None:
        audio = max(
            (option for option in video_info.video_options if option.has_audio),
            key=lambda option: option.height or option.tbr or 0,
            default=None,
        )
    if audio is None:
        raise FormatPlanningError("Nenhuma faixa de áudio compatível foi disponibilizada.")
    return DownloadPlan(
        mode=DownloadMode.MP3,
        format_expression=audio.format_id,
        destination=destination,
        output_extension=".mp3",
        output_container="mp3",
        audio_format_id=audio.format_id,
        postprocessors=(
            PostProcessorSpec(
                "FFmpegExtractAudio",
                (("preferredcodec", "mp3"), ("preferredquality", str(bitrate))),
            ),
        ),
        requires_ffmpeg=True,
        messages=(
            f"Bitrate final de codificação: {bitrate} kbps; isso não melhora a qualidade da fonte.",
        ),
    )


def build_playlist_video_plan(
    quality: PlaylistQuality,
    profile: OutputProfile,
    destination: Path = Path("."),
) -> DownloadPlan:
    """Cria um plano que escolhe a qualidade individualmente em cada item."""
    if quality is PlaylistQuality.BEST:
        expression = "bestvideo+bestaudio/best"
        quality_label = "maior qualidade disponível"
    elif quality is PlaylistQuality.WORST:
        expression = "worstvideo+worstaudio/worst"
        quality_label = "menor qualidade disponível"
    else:
        raise FormatPlanningError("Escolha uma qualidade de playlist válida.")

    if profile is OutputProfile.ORIGINAL:
        return DownloadPlan(
            mode=DownloadMode.VIDEO,
            format_expression=expression,
            destination=destination,
            output_extension=None,
            output_container="original",
            video_format_id=quality.value + "video",
            audio_format_id=quality.value + "audio",
            profile=profile,
            requires_ffmpeg=True,
            messages=(f"Cada item usará a {quality_label} e preservará o contêiner resultante.",),
        )
    if profile is OutputProfile.CONVERT_MP4:
        return DownloadPlan(
            mode=DownloadMode.VIDEO,
            format_expression=expression,
            destination=destination,
            output_extension=".mp4",
            output_container="mp4",
            video_format_id=quality.value + "video",
            audio_format_id=quality.value + "audio",
            profile=profile,
            postprocessors=(PostProcessorSpec("FFmpegTranscode"),),
            requires_ffmpeg=True,
            transcode=True,
            messages=(
                f"Cada item usará a {quality_label} e será convertido explicitamente para MP4.",
            ),
        )
    raise FormatPlanningError("Playlists oferecem apenas Formato original ou Converter para MP4.")


def build_playlist_audio_plan(
    bitrate: int = 192,
    destination: Path = Path("."),
    *,
    ffmpeg_available: bool = True,
) -> DownloadPlan:
    """Cria um plano MP3 aplicado individualmente a todos os itens selecionados."""
    if bitrate not in {128, 192, 320}:
        raise FormatPlanningError("O bitrate MP3 deve ser 128, 192 ou 320 kbps.")
    if not ffmpeg_available:
        raise FormatPlanningError("FFmpeg e FFprobe são necessários para converter mídia.")
    return DownloadPlan(
        mode=DownloadMode.MP3,
        format_expression="bestaudio",
        destination=destination,
        output_extension=".mp3",
        output_container="mp3",
        audio_format_id="bestaudio",
        postprocessors=(
            PostProcessorSpec(
                "FFmpegExtractAudio",
                (("preferredcodec", "mp3"), ("preferredquality", str(bitrate))),
            ),
        ),
        requires_ffmpeg=True,
        messages=(f"Bitrate final de codificação aplicado a todos os itens: {bitrate} kbps.",),
    )


def _resolve_choice(video_info: VideoInfo, choice: FormatOption | str) -> FormatOption:
    if isinstance(choice, FormatOption):
        candidate = choice
    else:
        candidate = next(
            (option for option in video_info.video_options if option.format_id == choice),
            None,
        )
        if candidate is None:
            raise FormatPlanningError(
                "A qualidade escolhida não está mais disponível. Analise novamente."
            )
    if candidate.format_id not in {option.format_id for option in video_info.video_options}:
        raise FormatPlanningError(
            "A qualidade escolhida não está mais disponível. Analise novamente."
        )
    return candidate


def _choose_audio(video_info: VideoInfo, *, prefer_mp4: bool) -> FormatOption | None:
    options = list(video_info.audio_options)
    if prefer_mp4:
        compatible = [option for option in options if _is_aac_audio(option)]
        if compatible:
            options = compatible
    return max(options, key=lambda option: option.abr or option.tbr or 0, default=None)


def _is_aac_audio(option: FormatOption) -> bool:
    codec = (option.acodec or "").lower()
    return codec.startswith(("mp4a", "aac")) or option.ext in {"m4a", "mp4"}


def _is_mp4_compatible(option: FormatOption) -> bool:
    return _is_video_mp4_compatible(option) and (option.acodec or "").lower().startswith(
        ("mp4a", "aac")
    )


def _is_video_mp4_compatible(option: FormatOption) -> bool:
    return option.ext == "mp4" and (option.vcodec or "").lower().startswith(("avc", "h264"))


def _single_stream_plan(
    selected: FormatOption,
    destination: Path,
    *,
    extension: str,
    container: str,
    profile: OutputProfile,
    messages: tuple[str, ...],
) -> DownloadPlan:
    return DownloadPlan(
        mode=DownloadMode.VIDEO,
        format_expression=selected.format_id,
        destination=destination,
        output_extension=extension,
        output_container=container,
        video_format_id=selected.format_id,
        profile=profile,
        messages=messages,
    )


def _merged_plan(
    selected: FormatOption,
    audio: FormatOption,
    destination: Path,
    *,
    extension: str,
    container: str,
    profile: OutputProfile,
    messages: tuple[str, ...],
) -> DownloadPlan:
    return DownloadPlan(
        mode=DownloadMode.VIDEO,
        format_expression=f"{selected.format_id}+{audio.format_id}",
        destination=destination,
        output_extension=extension,
        output_container=container,
        video_format_id=selected.format_id,
        audio_format_id=audio.format_id,
        profile=profile,
        requires_ffmpeg=True,
        messages=messages,
    )


def _container_extension(ext: str | None) -> str:
    return f".{ext.lower()}" if ext else ".mkv"


def _original_merge_extension(video: FormatOption, audio: FormatOption) -> str:
    if video.ext == "webm" and audio.ext == "webm":
        return ".webm"
    if video.ext == "mp4" and _is_aac_audio(audio):
        return ".mp4"
    return ".mkv"


def _to_option(raw: dict[str, Any]) -> FormatOption | None:
    format_id = _string(raw.get("format_id"))
    url = _string(raw.get("url"))
    vcodec = _string(raw.get("vcodec"))
    acodec = _string(raw.get("acodec"))
    note = _string(raw.get("format_note"))
    ext = _string(raw.get("ext"))
    if not format_id or not url or _is_storyboard(raw, note, ext):
        return None

    has_video = bool(
        vcodec
        and vcodec != "none"
        and (_positive_int(raw.get("height")) or _positive_int(raw.get("width")))
    )
    has_audio = bool(acodec and acodec != "none")
    if not has_video and not has_audio:
        return None
    if has_video and has_audio:
        kind = StreamKind.VIDEO_AUDIO
    elif has_video:
        kind = StreamKind.VIDEO_ONLY
    else:
        kind = StreamKind.AUDIO_ONLY

    option = FormatOption(
        format_id=format_id,
        stream_kind=kind,
        ext=ext,
        width=_positive_int(raw.get("width")),
        height=_positive_int(raw.get("height")),
        fps=_positive_number(raw.get("fps")),
        vcodec=vcodec,
        acodec=acodec,
        protocol=_string(raw.get("protocol")),
        filesize=_nonnegative_int(raw.get("filesize")),
        filesize_approx=_nonnegative_int(raw.get("filesize_approx")),
        tbr=_positive_number(raw.get("tbr")),
        vbr=_positive_number(raw.get("vbr")),
        abr=_positive_number(raw.get("abr")),
        dynamic_range=_string(raw.get("dynamic_range")),
        format_note=note,
        label=_label(kind, raw),
    )
    return option


def _is_storyboard(raw: dict[str, Any], note: str | None, ext: str | None) -> bool:
    text = " ".join(
        str(raw.get(key, ""))
        for key in ("format_id", "format", "format_note", "protocol", "vcodec", "acodec")
    )
    return "storyboard" in text.lower() or (
        ext in {"mhtml", "jpg", "jpeg"} and not _string(raw.get("vcodec"))
    )


def _presentation_key(option: FormatOption) -> tuple[Any, ...]:
    if option.has_video:
        return (
            "video",
            option.width,
            option.height,
            option.fps,
            _codec_family(option.vcodec),
            option.dynamic_range,
            option.has_audio,
        )
    return ("audio", option.abr, _codec_family(option.acodec), option.ext)


def _quality_key(option: FormatOption) -> tuple[float, ...]:
    return (
        float(option.estimated_size or 0),
        float(option.tbr or option.vbr or option.abr or 0),
    )


def _sort_key(option: FormatOption) -> tuple[float, ...]:
    return (
        1.0 if option.has_video else 0.0,
        float(option.height or 0),
        float(option.width or 0),
        float(option.fps or 0),
        float(option.tbr or option.vbr or option.abr or 0),
    )


def _label(kind: StreamKind, raw: dict[str, Any]) -> str:
    if kind is StreamKind.AUDIO_ONLY:
        bitrate = _positive_number(raw.get("abr")) or _positive_number(raw.get("tbr"))
        codec = _codec_label(_string(raw.get("acodec")))
        parts = []
        if bitrate is not None:
            parts.append(f"{_number_text(bitrate)} kbps")
        if codec:
            parts.append(codec)
        return " • ".join(parts) or "Áudio disponível"

    height = _positive_int(raw.get("height"))
    fps = _positive_number(raw.get("fps"))
    codec = _codec_label(_string(raw.get("vcodec")))
    dynamic_range = _string(raw.get("dynamic_range"))
    parts = []
    if height:
        parts.append(f"{height}p")
    if fps:
        parts.append(f"{_number_text(fps)} fps")
    if codec:
        parts.append(codec)
    if dynamic_range and dynamic_range.lower() not in {"sdr", "none"}:
        parts.append(dynamic_range)
    return " • ".join(parts) or "Vídeo disponível"


def _codec_family(codec: str | None) -> str | None:
    if not codec:
        return None
    value = codec.lower()
    if value.startswith(("avc", "h264")):
        return "h264"
    if value.startswith("vp9"):
        return "vp9"
    if value.startswith(("av01", "av1")):
        return "av1"
    if value.startswith(("mp4a", "aac")):
        return "aac"
    if value.startswith("opus"):
        return "opus"
    return value


def _codec_label(codec: str | None) -> str | None:
    family = _codec_family(codec)
    return {"h264": "H.264", "vp9": "VP9", "av1": "AV1", "aac": "AAC", "opus": "Opus"}.get(
        family, codec
    )


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _positive_int(value: Any) -> int | None:
    return (
        int(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else None
    )


def _nonnegative_int(value: Any) -> int | None:
    return (
        int(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
        else None
    )


def _positive_number(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else None
    )


def _number_text(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"
