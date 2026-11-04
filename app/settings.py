"""Persistência mínima de preferências no perfil do usuário."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import DownloadMode


@dataclass(frozen=True, slots=True)
class AppSettings:
    destination: Path
    mode: DownloadMode = DownloadMode.VIDEO
    mp3_bitrate: int = 192
    window_width: int = 860
    window_height: int = 600
    language: str = "en-US"
    always_on_top: bool = False
    check_updates: bool = True
    playlist_thumbnail_limit: int = 25
    theme: str = "night"

    def __post_init__(self) -> None:
        if self.mp3_bitrate not in {128, 192, 320}:
            raise ValueError("mp3_bitrate inválido")
        if self.window_width < 480 or self.window_height < 360:
            raise ValueError("tamanho de janela inválido")
        if self.language not in {"pt-BR", "en-US"}:
            raise ValueError("idioma inválido")
        if not isinstance(self.always_on_top, bool):
            raise ValueError("always_on_top inválido")
        if not isinstance(self.check_updates, bool):
            raise ValueError("check_updates inválido")
        if not 0 <= self.playlist_thumbnail_limit <= 5000:
            raise ValueError("limite de thumbnails inválido")
        if self.theme not in {"night", "day"}:
            raise ValueError("tema inválido")


class SettingsStore:
    """Carrega/salva apenas preferências não sensíveis em JSON."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        default_destination: Path | str | None = None,
    ) -> None:
        self.path = Path(path) if path else _default_settings_path()
        self.default_destination = (
            Path(default_destination).expanduser()
            if default_destination is not None
            else _default_destination()
        )

    def load(self) -> AppSettings:
        defaults = AppSettings(self.default_destination)
        if not self.path.is_file():
            return defaults
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return defaults
            return AppSettings(
                destination=_existing_path_value(data.get("destination"), defaults.destination),
                mode=_mode_value(data.get("mode"), defaults.mode),
                mp3_bitrate=_bitrate_value(data.get("mp3_bitrate"), defaults.mp3_bitrate),
                window_width=_size_value(data.get("window_width"), defaults.window_width),
                window_height=_size_value(data.get("window_height"), defaults.window_height),
                language=_language_value(data.get("language"), defaults.language),
                always_on_top=_bool_value(data.get("always_on_top"), defaults.always_on_top),
                check_updates=_bool_value(data.get("check_updates"), defaults.check_updates),
                playlist_thumbnail_limit=_thumbnail_limit_value(
                    data.get("playlist_thumbnail_limit"), defaults.playlist_thumbnail_limit
                ),
                theme=_theme_value(data.get("theme"), defaults.theme),
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return defaults

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "destination": str(settings.destination),
            "mode": settings.mode.value,
            "mp3_bitrate": settings.mp3_bitrate,
            "window_width": settings.window_width,
            "window_height": settings.window_height,
            "language": settings.language,
            "always_on_top": settings.always_on_top,
            "check_updates": settings.check_updates,
            "playlist_thumbnail_limit": settings.playlist_thumbnail_limit,
            "theme": settings.theme,
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


def _default_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "DownloaderinoGlobal" / "settings.json"


def _default_destination() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def _path_value(value: Any, default: Path) -> Path:
    return Path(value).expanduser() if isinstance(value, str) and value.strip() else default


def _existing_path_value(value: Any, default: Path) -> Path:
    candidate = _path_value(value, default)
    return candidate if candidate.is_dir() else default


def _mode_value(value: Any, default: DownloadMode) -> DownloadMode:
    try:
        return DownloadMode(value)
    except (ValueError, TypeError):
        return default


def _bitrate_value(value: Any, default: int) -> int:
    return int(value) if isinstance(value, int) and value in {128, 192, 320} else default


def _size_value(value: Any, default: int) -> int:
    return int(value) if isinstance(value, int) and value > 0 else default


def _language_value(value: Any, default: str) -> str:
    return value if value in {"pt-BR", "en-US"} else default


def _bool_value(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _thumbnail_limit_value(value: Any, default: int) -> int:
    return int(value) if isinstance(value, int) and 0 <= value <= 5000 else default


def _theme_value(value: Any, default: str) -> str:
    return value if value in {"night", "day"} else default
