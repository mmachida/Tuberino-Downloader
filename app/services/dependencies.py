"""Detecção segura das ferramentas usadas pelo aplicativo."""

from __future__ import annotations

import importlib.metadata
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.services.process_utils import hidden_process_kwargs


class DependencyStatus(StrEnum):
    """Estado resumido de uma dependência."""

    READY = "ready"
    MISSING = "missing"
    INVALID = "invalid"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DependencyInfo:
    """Diagnóstico estruturado de uma dependência."""

    key: str
    label: str
    path: Path | None
    version: str | None
    status: DependencyStatus
    recommendation: str

    @property
    def ready(self) -> bool:
        return self.status is DependencyStatus.READY


@dataclass(frozen=True, slots=True)
class DependencyPaths:
    """Caminhos normalizados para repassar ao yt-dlp."""

    ffmpeg_location: Path | None
    js_runtimes: dict[str, dict[str, str]]

    def as_yt_dlp_options(self) -> dict[str, Any]:
        """Retorna apenas opções disponíveis para a API Python do yt-dlp."""
        options: dict[str, Any] = {}
        if self.ffmpeg_location is not None:
            options["ffmpeg_location"] = str(self.ffmpeg_location)
        if self.js_runtimes:
            options["js_runtimes"] = self.js_runtimes
        return options


@dataclass(frozen=True, slots=True)
class DependencyReport:
    """Resultado completo de uma verificação, sem texto não estruturado."""

    items: tuple[DependencyInfo, ...]
    paths: DependencyPaths

    def by_key(self, key: str) -> DependencyInfo:
        for item in self.items:
            if item.key == key:
                return item
        raise KeyError(key)

    @property
    def ffmpeg_ready(self) -> bool:
        return self.by_key("ffmpeg").ready and self.by_key("ffprobe").ready

    @property
    def javascript_ready(self) -> bool:
        return self.by_key("deno").ready and self.by_key("yt-dlp-ejs").ready


@dataclass(frozen=True, slots=True)
class _VersionProbe:
    success: bool
    output: str
    error: str | None = None


class DependencyChecker:
    """Resolve e valida FFmpeg, FFprobe, Deno e pacotes Python relacionados.

    A ordem de resolução é caminho explícito, `vendor/` do projeto e `PATH`.
    Nenhum método desta classe faz download ou instala dependências.
    """

    MIN_DENO_VERSION = (2, 3, 0)

    def __init__(
        self,
        project_root: Path | str,
        *,
        ffmpeg_path: Path | str | None = None,
        ffprobe_path: Path | str | None = None,
        deno_path: Path | str | None = None,
        vendor_root: Path | str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self._vendor_root_override = (
            Path(vendor_root).expanduser().resolve() if vendor_root else None
        )
        self.timeout_seconds = timeout_seconds
        self._explicit_paths = {
            "ffmpeg": Path(ffmpeg_path).expanduser() if ffmpeg_path else None,
            "ffprobe": Path(ffprobe_path).expanduser() if ffprobe_path else None,
            "deno": Path(deno_path).expanduser() if deno_path else None,
        }

    @property
    def vendor_root(self) -> Path:
        return self._vendor_root_override or self.project_root / "vendor"

    def check(self) -> DependencyReport:
        """Executa uma verificação curta e retorna diagnóstico acionável."""
        ffmpeg = self._check_binary(
            key="ffmpeg",
            label="FFmpeg",
            explicit=self._explicit_paths["ffmpeg"],
            vendor_path=self.vendor_root / "ffmpeg" / "bin" / "ffmpeg.exe",
            path_name="ffmpeg.exe",
            argument="-version",
            kind="ffmpeg",
        )
        ffprobe = self._check_binary(
            key="ffprobe",
            label="FFprobe",
            explicit=self._explicit_paths["ffprobe"],
            vendor_path=self.vendor_root / "ffmpeg" / "bin" / "ffprobe.exe",
            path_name="ffprobe.exe",
            argument="-version",
            kind="ffprobe",
        )
        deno = self._check_binary(
            key="deno",
            label="Deno",
            explicit=self._explicit_paths["deno"],
            vendor_path=self.vendor_root / "deno" / "deno.exe",
            path_name="deno.exe",
            argument="--version",
            kind="deno",
        )
        yt_dlp = self._check_package("yt-dlp", "yt-dlp")
        ejs = self._check_package("yt-dlp-ejs", "yt-dlp-ejs")

        ffmpeg_location: Path | None = None
        if ffmpeg.ready and ffprobe.ready and ffmpeg.path is not None:
            ffmpeg_location = ffmpeg.path.parent

        runtimes: dict[str, dict[str, str]] = {}
        if deno.ready and deno.path is not None:
            runtimes["deno"] = {"path": str(deno.path)}

        return DependencyReport(
            items=(ffmpeg, ffprobe, deno, yt_dlp, ejs),
            paths=DependencyPaths(ffmpeg_location=ffmpeg_location, js_runtimes=runtimes),
        )

    def _check_binary(
        self,
        *,
        key: str,
        label: str,
        explicit: Path | None,
        vendor_path: Path,
        path_name: str,
        argument: str,
        kind: str,
    ) -> DependencyInfo:
        path = self._resolve_binary(explicit, vendor_path, path_name)
        if path is None:
            return DependencyInfo(
                key=key,
                label=label,
                path=None,
                version=None,
                status=DependencyStatus.MISSING,
                recommendation=f"Instale {label} ou execute scripts/setup_tools.ps1.",
            )
        if not path.is_file():
            return DependencyInfo(
                key=key,
                label=label,
                path=path,
                version=None,
                status=DependencyStatus.INVALID,
                recommendation=f"O caminho configurado para {label} não é um executável válido.",
            )

        probe = self._probe_version(path, argument)
        if not probe.success:
            status = DependencyStatus.ERROR
            recommendation = probe.error or f"Não foi possível executar {label}."
            return DependencyInfo(key, label, path, None, status, recommendation)

        version = self._version_text(probe.output)
        if kind == "deno":
            parsed = self._parse_semver(probe.output)
            if parsed is None or parsed < self.MIN_DENO_VERSION:
                return DependencyInfo(
                    key,
                    label,
                    path,
                    version,
                    DependencyStatus.INVALID,
                    "Atualize o Deno para uma versão compatível (mínimo 2.3.0).",
                )

        return DependencyInfo(
            key=key,
            label=label,
            path=path,
            version=version,
            status=DependencyStatus.READY,
            recommendation="Dependência pronta.",
        )

    def _resolve_binary(
        self, explicit: Path | None, vendor_path: Path, path_name: str
    ) -> Path | None:
        if explicit is not None:
            return explicit.expanduser().resolve()
        if vendor_path.is_file():
            return vendor_path.resolve()
        located = shutil.which(path_name)
        return Path(located).resolve() if located else None

    def _probe_version(self, path: Path, argument: str) -> _VersionProbe:
        try:
            result = subprocess.run(
                [str(path), argument],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self.timeout_seconds,
                **hidden_process_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return _VersionProbe(False, "", "A verificação excedeu o tempo limite.")
        except OSError as exc:
            return _VersionProbe(False, "", f"Falha ao executar a dependência: {exc}")
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            return _VersionProbe(False, output, "O executável retornou erro ao informar a versão.")
        return _VersionProbe(True, output)

    def _check_package(self, key: str, distribution_name: str) -> DependencyInfo:
        try:
            distribution = importlib.metadata.distribution(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            return DependencyInfo(
                key=key,
                label=distribution_name,
                path=None,
                version=None,
                status=DependencyStatus.MISSING,
                recommendation=f"Instale ou atualize o pacote Python {distribution_name}.",
            )

        location = Path(distribution.locate_file(".")).resolve()
        return DependencyInfo(
            key=key,
            label=distribution_name,
            path=location,
            version=distribution.version,
            status=DependencyStatus.READY,
            recommendation="Pacote Python encontrado.",
        )

    @staticmethod
    def _version_text(output: str) -> str | None:
        first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
        return first_line or None

    @staticmethod
    def _parse_semver(output: str) -> tuple[int, int, int] | None:
        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
        return tuple(int(group) for group in match.groups()) if match else None
