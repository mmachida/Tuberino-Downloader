"""Processo auxiliar silencioso que troca arquivos após o app fechar."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from app.updates.config import APP_EXECUTABLE_NAME, UpdateConfig
from app.updates.installer import (
    InstallError,
    finalize_transaction,
    install_archive,
    rollback_transaction,
)

_DELEGATED_ENV = "TUBERINO_UPDATE_HELPER_CHILD"
_DELEGATED_ROOT_ENV = "TUBERINO_UPDATE_HELPER_ROOT"


def main(argv: list[str] | None = None) -> int:
    if _delegate_frozen_helper():
        return 0
    parser = argparse.ArgumentParser(description="Tuberino Downloader update helper")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--checksum", required=True)
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--version", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--launch-mode", choices=("source", "frozen"), required=True)
    parser.add_argument("--cleanup-root", required=True)
    args = parser.parse_args(argv)

    try:
        _wait_for_process(args.parent_pid)
        config = UpdateConfig(package_id=args.package_id)
        transaction = install_archive(
            args.archive,
            args.checksum,
            args.install_root,
            config,
            expected_version=args.version,
        )
        try:
            command = _launch_command(Path(args.install_root), args.launch_mode)
            _start_hidden(command, Path(args.install_root))
        except (OSError, ValueError):
            rollback_transaction(transaction)
            return 4
        finalize_transaction(transaction)
        return 0
    except (InstallError, OSError, ValueError):
        _log_install_failure(Path(args.install_root))
        return 1
    finally:
        shutil.rmtree(Path(args.cleanup_root), ignore_errors=True)
        _schedule_delegated_cleanup()


def _wait_for_process(pid: int, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_is_running(pid):
            return
        time.sleep(0.25)
    raise OSError("O aplicativo anterior não encerrou dentro do tempo esperado.")


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _launch_command(install_root: Path, mode: str) -> list[str]:
    if mode == "frozen":
        return [str(install_root / APP_EXECUTABLE_NAME)]
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if python.name.casefold() == "python.exe" and pythonw.is_file() else python
    return [str(executable), "-m", "app"]


def _start_hidden(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> None:
    flags = 0
    startupinfo = None
    if os.name == "nt":
        flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        close_fds=True,
        creationflags=flags,
        startupinfo=startupinfo,
    )


def _delegate_frozen_helper() -> bool:
    """Executa uma cópia temporária quando o próprio helper está congelado."""
    if not getattr(sys, "frozen", False) or os.environ.get(_DELEGATED_ENV) == "1":
        return False
    source = Path(sys.executable).resolve()
    temporary_root = Path(tempfile.mkdtemp(prefix="tuberino-updater-"))
    delegated = temporary_root / source.name
    try:
        shutil.copy2(source, delegated)
        environment = os.environ.copy()
        environment[_DELEGATED_ENV] = "1"
        environment[_DELEGATED_ROOT_ENV] = str(temporary_root)
        _start_hidden([str(delegated), *sys.argv[1:]], Path.cwd(), env=environment)
    except OSError:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    return True


def _schedule_delegated_cleanup() -> None:
    temporary_root = os.environ.get(_DELEGATED_ROOT_ENV)
    if not temporary_root:
        return
    try:
        shutil.rmtree(temporary_root, ignore_errors=True)
    except OSError:
        pass


def _log_install_failure(install_root: Path) -> None:
    """Registra somente uma mensagem genérica quando a instalação falha."""

    try:
        log_path = install_root / "logs" / "log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now():%d/%m/%Y - %H:%M} - A atualização não pôde ser instalada.\n"
            )
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
