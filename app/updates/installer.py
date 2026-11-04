"""Instalação transacional de um release, preservando dados do usuário."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import UpdateConfig
from .service import UpdateError, UpdateService


class InstallError(UpdateError):
    """Erro seguro da fase de substituição local."""


@dataclass(slots=True)
class InstallTransaction:
    install_root: Path
    backup_dir: Path
    staging_dir: Path
    backed_up_files: tuple[str, ...]
    installed_files: tuple[str, ...]


def install_archive(
    archive_path: Path | str,
    checksum_path: Path | str,
    install_root: Path | str,
    config: UpdateConfig,
    *,
    expected_version: str,
) -> InstallTransaction:
    """Valida e instala somente os arquivos listados pelo manifesto."""
    root = Path(install_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = Path(archive_path).resolve()
    checksum = Path(checksum_path).resolve()
    service = UpdateService(config, expected_version)
    try:
        service.verify_checksum(archive, checksum)
        manifest = service.validate_archive(archive, expected_version)
        files = tuple(str(item) for item in manifest["files"])
        staging_dir = Path(tempfile.mkdtemp(prefix="tuberino-install-"))
        backup_dir = Path(tempfile.mkdtemp(prefix="tuberino-backup-"))
        backed_up: list[str] = []
        installed: list[str] = []
        try:
            _extract_files(archive, staging_dir, files)
            for relative in files:
                target = _safe_target(root, relative)
                staged = _safe_target(staging_dir, relative)
                if not staged.is_file():
                    raise InstallError(f"O pacote não contém o arquivo {relative}.")
                if target.exists():
                    if target.is_symlink():
                        raise InstallError(f"O destino contém um link simbólico: {relative}.")
                    backup_target = _safe_target(backup_dir, relative)
                    backup_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup_target)
                    backed_up.append(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary_target = target.with_name(f".{target.name}.{uuid.uuid4().hex}.update")
                try:
                    shutil.copy2(staged, temporary_target)
                    os.replace(temporary_target, target)
                finally:
                    temporary_target.unlink(missing_ok=True)
                installed.append(relative)
        except Exception:
            _rollback_files(root, backup_dir, backed_up, installed)
            raise
        return InstallTransaction(root, backup_dir, staging_dir, tuple(backed_up), tuple(installed))
    except InstallError:
        raise
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise InstallError(f"Não foi possível instalar a atualização: {exc}") from exc


def rollback_transaction(transaction: InstallTransaction) -> None:
    """Restaura os arquivos anteriores após falha ao iniciar o novo app."""
    _rollback_files(
        transaction.install_root,
        transaction.backup_dir,
        transaction.backed_up_files,
        transaction.installed_files,
    )
    _cleanup_transaction(transaction)


def finalize_transaction(transaction: InstallTransaction) -> None:
    """Remove somente os backups temporários após o novo app ser iniciado."""
    _cleanup_transaction(transaction)


def _extract_files(archive_path: Path, staging_dir: Path, files: tuple[str, ...]) -> None:
    requested = set(files)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.replace("\\", "/") not in requested:
                continue
            target = _safe_target(staging_dir, info.filename.replace("\\", "/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, 64 * 1024)


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    if target != root and root not in target.parents:
        raise InstallError("O pacote aponta para fora da pasta de instalação.")
    return target


def _rollback_files(
    root: Path,
    backup_dir: Path,
    backed_up: list[str] | tuple[str, ...],
    installed: list[str] | tuple[str, ...],
) -> None:
    for relative in reversed(installed):
        target = _safe_target(root, relative)
        target.unlink(missing_ok=True)
    for relative in backed_up:
        backup = _safe_target(backup_dir, relative)
        target = _safe_target(root, relative)
        if backup.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)


def _cleanup_transaction(transaction: InstallTransaction) -> None:
    shutil.rmtree(transaction.backup_dir, ignore_errors=True)
    shutil.rmtree(transaction.staging_dir, ignore_errors=True)
