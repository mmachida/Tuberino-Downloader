"""Instalação transacional de um release, preservando dados do usuário."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import UpdateConfig
from .service import UpdateError, UpdateService


class InstallError(UpdateError):
    """Erro seguro da fase de substituição local."""


STATE_FILENAME = ".tuberino-update-state.json"
BACKUP_DIRECTORY = ".tuberino-update-backups"
CONFIRMATION_ENV = "TUBERINO_UPDATE_STATE"
ACTIVE_UPDATE_STATUSES = frozenset({"installing", "awaiting_confirmation"})
_REPLACE_RETRY_SECONDS = 30.0
_REPLACE_RETRY_DELAY_SECONDS = 0.25


@dataclass(slots=True)
class InstallTransaction:
    install_root: Path
    state_path: Path
    backup_dir: Path
    staging_dir: Path
    backed_up_files: tuple[str, ...]
    installed_files: tuple[str, ...]
    previous_state: dict[str, object] | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_json_write(path: Path, value: object) -> None:
    """Grava o estado de forma atômica para sobreviver a interrupções."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_state(path: Path) -> dict[str, object] | None:
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def default_install_root() -> Path:
    """Retorna a pasta que contém o executável ou a raiz do projeto."""

    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def check_install_prerequisites(archive_path: Path | str, install_root: Path | str) -> None:
    """Valida recursos antes de fechar a aplicação em execução."""

    archive = Path(archive_path).expanduser().resolve()
    root = Path(install_root).expanduser().resolve()
    if not archive.is_file():
        raise InstallError("O pacote de atualização não está disponível.")
    if not root.is_dir():
        raise InstallError("A pasta de instalação não existe.")
    try:
        required_space = max(archive.stat().st_size * 2, 16 * 1024 * 1024)
        if shutil.disk_usage(root).free < required_space:
            raise InstallError("Não há espaço livre suficiente para preparar a atualização.")
        descriptor, probe_name = tempfile.mkstemp(prefix=".tuberino-update-check-", dir=root)
        os.close(descriptor)
        Path(probe_name).unlink(missing_ok=True)
    except InstallError:
        raise
    except OSError as exc:
        raise InstallError("A pasta de instalação não permite preparar a atualização.") from exc


def install_archive(
    archive_path: Path | str,
    checksum_path: Path | str,
    install_root: Path | str,
    config: UpdateConfig,
    *,
    expected_version: str,
) -> InstallTransaction:
    """Valida e instala um pacote, deixando rollback persistente até confirmar o startup."""

    root = Path(install_root).expanduser().resolve()
    archive = Path(archive_path).expanduser().resolve()
    checksum = Path(checksum_path).expanduser().resolve()
    state_path = root / STATE_FILENAME
    staging_dir: Path | None = None
    backup_dir: Path | None = None
    backed_up: list[str] = []
    installed: list[str] = []
    previous_state: dict[str, object] | None = None

    try:
        check_install_prerequisites(archive, root)
        service = UpdateService(config, expected_version)
        service.verify_checksum(archive, checksum)
        manifest = service.validate_archive(archive, expected_version)
        files = tuple(str(item) for item in manifest["files"])
        staging_dir = Path(tempfile.mkdtemp(prefix=".tuberino-update-", dir=root))
        previous_state = read_state(state_path)
        if previous_state and previous_state.get("status") in ACTIVE_UPDATE_STATUSES:
            raise InstallError("Já existe uma atualização em andamento.")

        transaction_id = uuid.uuid4().hex
        backup_dir = root / BACKUP_DIRECTORY / transaction_id
        backup_dir.mkdir(parents=True, exist_ok=False)
        _extract_files(archive, staging_dir, files)

        _write_installing_state(
            state_path,
            expected_version,
            config.package_id,
            root,
            backup_dir,
            backed_up,
            files,
            previous_state,
        )
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
                _write_installing_state(
                    state_path,
                    expected_version,
                    config.package_id,
                    root,
                    backup_dir,
                    backed_up,
                    files,
                    previous_state,
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary_target = target.with_name(f".{target.name}.{uuid.uuid4().hex}.update")
            try:
                shutil.copy2(staged, temporary_target)
                _replace_with_retry(temporary_target, target)
            finally:
                temporary_target.unlink(missing_ok=True)
            installed.append(relative)

        managed_files = {relative: _sha256(_safe_target(root, relative)) for relative in files}
        atomic_json_write(
            state_path,
            {
                "status": "awaiting_confirmation",
                "version": expected_version,
                "package_id": config.package_id,
                "install_root": str(root),
                "backup_dir": str(backup_dir),
                "managed_files": managed_files,
                "previous_state": previous_state,
                "backed_up_files": backed_up,
                "installed_files": list(files),
                "created_at": utc_now(),
            },
        )
        return InstallTransaction(
            root,
            state_path,
            backup_dir,
            staging_dir,
            tuple(backed_up),
            tuple(files),
            previous_state,
        )
    except InstallError:
        _rollback_partial_install(
            root,
            state_path,
            backup_dir,
            backed_up,
            tuple(installed),
            previous_state,
        )
        raise
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        _rollback_partial_install(
            root,
            state_path,
            backup_dir,
            backed_up,
            tuple(installed),
            previous_state,
        )
        raise InstallError(f"Não foi possível instalar a atualização: {exc}") from exc
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


def finalize_transaction(transaction: InstallTransaction) -> None:
    """Confirma o pacote e remove o rollback somente após o novo app iniciar."""

    state = read_state(transaction.state_path) or {}
    state["status"] = "confirmed"
    state.pop("backup_dir", None)
    state.pop("previous_state", None)
    state.pop("backed_up_files", None)
    state.pop("installed_files", None)
    state["confirmed_at"] = utc_now()
    atomic_json_write(transaction.state_path, state)
    _cleanup_transaction(transaction)


def rollback_transaction(transaction: InstallTransaction) -> None:
    """Restaura os arquivos anteriores e deixa a instalação pronta para abrir."""

    state = read_state(transaction.state_path)
    backed_up = _state_list(state, "backed_up_files") or list(transaction.backed_up_files)
    installed = _state_list(state, "installed_files") or list(transaction.installed_files)
    _rollback_files(transaction.install_root, transaction.backup_dir, backed_up, installed)
    _write_rolled_back_state(
        transaction.state_path,
        transaction.install_root,
        state,
        transaction.previous_state,
    )
    _cleanup_transaction(transaction)


def recover_pending_install(state_path: Path | None = None) -> bool:
    """Recupera uma instalação interrompida antes do próximo startup normal."""

    path = Path(state_path or (default_install_root() / STATE_FILENAME))
    state = read_state(path)
    if not state or state.get("status") != "installing":
        return False
    root = Path(str(state.get("install_root", path.parent))).resolve()
    backup_value = state.get("backup_dir")
    if not isinstance(backup_value, str):
        return False
    backup_dir = Path(backup_value).resolve()
    if not _is_inside(root, path.resolve()) or not _is_inside(root / BACKUP_DIRECTORY, backup_dir):
        return False
    previous_state = state.get("previous_state")
    previous = previous_state if isinstance(previous_state, dict) else None
    _rollback_files(
        root,
        backup_dir,
        _state_list(state, "backed_up_files"),
        _state_list(state, "installed_files"),
    )
    shutil.rmtree(backup_dir, ignore_errors=True)
    _write_rolled_back_state(path, root, state, previous)
    _remove_empty_backup_parent(root / BACKUP_DIRECTORY)
    return True


def confirm_pending_startup(state_path: Path | None = None) -> bool:
    """Confirma o novo executável iniciado pelo helper e remove o backup."""

    environment_path = os.environ.get(CONFIRMATION_ENV)
    path = Path(state_path or environment_path or (default_install_root() / STATE_FILENAME))
    state = read_state(path)
    if not state or state.get("status") != "awaiting_confirmation":
        return False
    root = Path(str(state.get("install_root", path.parent))).resolve()
    if not _is_inside(root, path.resolve()):
        return False
    backup_value = state.get("backup_dir")
    if isinstance(backup_value, str):
        backup_dir = Path(backup_value).resolve()
        if _is_inside(root / BACKUP_DIRECTORY, backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
    state["status"] = "confirmed"
    state.pop("backup_dir", None)
    state.pop("previous_state", None)
    state.pop("backed_up_files", None)
    state.pop("installed_files", None)
    state["confirmed_at"] = utc_now()
    atomic_json_write(path, state)
    _remove_empty_backup_parent(root / BACKUP_DIRECTORY)
    return True


def _extract_files(archive_path: Path, staging_dir: Path, files: tuple[str, ...]) -> None:
    requested = set(files)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            relative = info.filename.replace("\\", "/")
            if info.is_dir() or relative not in requested:
                continue
            target = _safe_target(staging_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, 64 * 1024)


def _write_installing_state(
    state_path: Path,
    version: str,
    package_id: str,
    root: Path,
    backup_dir: Path,
    backed_up: list[str],
    installed: tuple[str, ...],
    previous_state: dict[str, object] | None,
) -> None:
    atomic_json_write(
        state_path,
        {
            "status": "installing",
            "version": version,
            "package_id": package_id,
            "install_root": str(root),
            "backup_dir": str(backup_dir),
            "previous_state": previous_state,
            "backed_up_files": list(backed_up),
            "installed_files": list(installed),
            "created_at": utc_now(),
        },
    )


def _rollback_partial_install(
    root: Path,
    state_path: Path,
    backup_dir: Path | None,
    backed_up: list[str],
    installed: tuple[str, ...],
    previous_state: dict[str, object] | None,
) -> None:
    if backup_dir is None:
        return
    try:
        _rollback_files(root, backup_dir, backed_up, list(installed))
        _write_rolled_back_state(state_path, root, read_state(state_path), previous_state)
    except OSError:
        pass


def _rollback_files(
    root: Path,
    backup_dir: Path,
    backed_up: list[str],
    installed: list[str],
) -> None:
    for relative in installed:
        target = _safe_target(root, relative)
        if relative not in backed_up:
            target.unlink(missing_ok=True)
    for relative in backed_up:
        backup = _safe_target(backup_dir, relative)
        target = _safe_target(root, relative)
        if backup.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_with_retry(backup, target)


def _write_rolled_back_state(
    state_path: Path,
    root: Path,
    state: dict[str, object] | None,
    previous_state: dict[str, object] | None,
) -> None:
    repaired = dict(previous_state or {})
    current = state or {}
    repaired.update(
        {
            "status": "rolled_back",
            "version": str(current.get("version") or repaired.get("version") or "0.0.0"),
            "package_id": str(current.get("package_id") or repaired.get("package_id") or ""),
            "install_root": str(root),
            "rolled_back_at": utc_now(),
        }
    )
    atomic_json_write(state_path, repaired)


def _state_list(state: dict[str, object] | None, key: str) -> list[str]:
    value = state.get(key) if state else None
    return [str(item) for item in value] if isinstance(value, list) else []


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    if target != root and root not in target.parents:
        raise InstallError("O pacote aponta para fora da pasta de instalação.")
    return target


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replace_with_retry(source: Path, target: Path) -> None:
    """Substitui um arquivo, aguardando o desbloqueio do processo anterior."""

    deadline = time.monotonic() + _REPLACE_RETRY_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)


def _cleanup_transaction(transaction: InstallTransaction) -> None:
    shutil.rmtree(transaction.backup_dir, ignore_errors=True)
    shutil.rmtree(transaction.staging_dir, ignore_errors=True)
    _remove_empty_backup_parent(transaction.install_root / BACKUP_DIRECTORY)


def _remove_empty_backup_parent(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
