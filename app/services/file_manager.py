"""Políticas de destino, nomes e arquivos da tarefa."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FileManagerError(ValueError):
    """Erro seguro de destino ou nome de arquivo."""


class CollisionPolicy(StrEnum):
    UNIQUE = "unique"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class OutputReservation:
    """Nome reservado antes de iniciar a transferência."""

    directory: Path
    stem: str
    template: str


def default_download_directory() -> Path:
    """Retorna Downloads quando existe, ou a pasta do usuário como fallback."""
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def validate_destination(
    directory: Path | str,
    *,
    create: bool = False,
    required_bytes: int | None = None,
) -> Path:
    """Valida uma pasta acessível sem criar nada salvo sem pedido explícito."""
    path = Path(directory).expanduser().resolve()
    if path.exists() and not path.is_dir():
        raise FileManagerError("O destino escolhido não é uma pasta.")
    if not path.exists():
        if not create:
            raise FileManagerError("A pasta de destino não existe.")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileManagerError("Não foi possível criar a pasta de destino.") from exc
    if not os.access(path, os.W_OK):
        raise FileManagerError("Não foi possível gravar na pasta escolhida.")
    if required_bytes is not None and required_bytes < 0:
        raise FileManagerError("O tamanho estimado não pode ser negativo.")
    if required_bytes is not None:
        try:
            free_bytes = shutil.disk_usage(path).free
        except OSError as exc:
            raise FileManagerError("Não foi possível verificar o espaço disponível.") from exc
        if free_bytes < required_bytes:
            raise FileManagerError("Não há espaço livre suficiente na pasta escolhida.")
    return path


def safe_stem(title: str, video_id: str, *, max_length: int = 160) -> str:
    """Gera uma base de nome aceitável pelo Windows, preservando Unicode."""
    clean_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    clean_title = clean_title or "video"
    suffix = f" [{_clean_id(video_id)}]"
    available = max(1, max_length - len(suffix))
    stem = f"{clean_title[:available].rstrip(' .')}{suffix}"
    if stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    return stem[:max_length].rstrip(" .")


def reserve_output(
    directory: Path | str,
    title: str,
    video_id: str,
    *,
    policy: CollisionPolicy = CollisionPolicy.UNIQUE,
) -> OutputReservation:
    """Reserva uma base que não coincide com arquivos anteriores."""
    path = validate_destination(directory)
    base = safe_stem(title, video_id)
    candidate = base
    counter = 1
    while _stem_exists(path, candidate):
        if policy is CollisionPolicy.ERROR:
            raise FileManagerError("Já existe um arquivo com esse nome no destino.")
        candidate = f"{base} ({counter})"
        counter += 1
    return OutputReservation(path, candidate, str(path / f"{candidate}.%(ext)s"))


def cleanup_task_temporaries(
    paths: list[Path] | tuple[Path, ...], directory: Path | str
) -> tuple[Path, ...]:
    """Remove somente temporários registrados dentro do destino informado."""
    root = Path(directory).resolve()
    removed: list[Path] = []
    for candidate in paths:
        path = Path(candidate).resolve()
        if root not in path.parents or path.suffix.lower() not in {".part", ".ytdl", ".tmp"}:
            continue
        if path.is_file():
            path.unlink()
            removed.append(path)
    return tuple(removed)


def _stem_exists(directory: Path, stem: str) -> bool:
    return any(item.is_file() and item.stem == stem for item in directory.iterdir())


def _clean_id(video_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", video_id).strip(" .")
    return clean or "video"


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
