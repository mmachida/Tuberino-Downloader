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
    CONFIRMATION_ENV,
    InstallError,
    finalize_transaction,
    install_archive,
    read_state,
    rollback_transaction,
)

_DELEGATED_ENV = "TUBERINO_UPDATE_HELPER_CHILD"
_DELEGATED_ROOT_ENV = "TUBERINO_UPDATE_HELPER_ROOT"
_CONFIRMATION_TIMEOUT_SECONDS = 45.0


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

    transaction = None
    parent_exited = False
    try:
        _wait_for_process(args.parent_pid)
        parent_exited = True
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
            environment = os.environ.copy()
            environment[CONFIRMATION_ENV] = str(transaction.state_path)
            process = _start_hidden(command, Path(args.install_root), env=environment)
        except (OSError, ValueError):
            rollback_transaction(transaction)
            transaction = None
            _restart_application(args, parent_exited)
            return 4
        if not _wait_for_confirmation(transaction.state_path):
            _terminate_process(process)
            rollback_transaction(transaction)
            transaction = None
            _restart_application(args, parent_exited)
            return 3
        finalize_transaction(transaction)
        transaction = None
        return 0
    except (InstallError, OSError, ValueError):
        if transaction is not None:
            try:
                rollback_transaction(transaction)
            except OSError:
                pass
        _restart_application(args, parent_exited)
        _log_install_failure(Path(args.install_root))
        return 1
    finally:
        shutil.rmtree(Path(args.cleanup_root), ignore_errors=True)
        _schedule_delegated_cleanup()


def _wait_for_process(pid: int, timeout_seconds: float = 120.0) -> None:
    """Aguarda exatamente o processo pai, sem confundir outro processo com ele."""

    if pid <= 0:
        return
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return
        try:
            result = ctypes.windll.kernel32.WaitForSingleObject(
                handle,
                int(timeout_seconds * 1000),
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        if result == 0:
            return
        raise OSError("O aplicativo anterior não encerrou dentro do tempo esperado.")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_is_running(pid):
            return
        time.sleep(0.1)
    raise OSError("O aplicativo anterior não encerrou dentro do tempo esperado.")


def _wait_for_confirmation(
    state_path: Path,
    timeout_seconds: float = _CONFIRMATION_TIMEOUT_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = read_state(state_path)
        if state and state.get("status") == "confirmed":
            return True
        time.sleep(0.2)
    return False


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


def _start_hidden(
    command: list[str], cwd: Path, *, env: dict[str, str] | None = None
) -> subprocess.Popen:
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
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        close_fds=True,
        creationflags=flags,
        startupinfo=startupinfo,
    )


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def _restart_application(args: argparse.Namespace, parent_exited: bool) -> None:
    if not parent_exited:
        return
    try:
        _start_hidden(
            _launch_command(Path(args.install_root), args.launch_mode),
            Path(args.install_root),
        )
    except OSError:
        pass


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
