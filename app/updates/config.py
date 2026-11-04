"""Configuração pública da distribuição e do updater."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

UPDATE_REPOSITORY_OWNER = "mmachida"
UPDATE_REPOSITORY_NAME = "Tuberino-Downloader"
UPDATE_PACKAGE_PREFIX = "tuberino-downloader"
UPDATE_CHECK_INTERVAL_HOURS = 24
APP_EXECUTABLE_NAME = "Tuberino Downloader.exe"
UPDATER_EXECUTABLE_NAME = "Tuberino Downloader Updater.exe"


def platform_package_id() -> str:
    """Retorna o identificador do pacote para o sistema e arquitetura atuais."""
    system = "windows" if sys.platform.startswith("win") else platform.system().lower()
    machine = platform.machine().lower()
    architecture = {
        "amd64": "x64",
        "x86_64": "x64",
        "x64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine or "unknown")
    return f"{UPDATE_PACKAGE_PREFIX}-{system}-{architecture}"


@dataclass(frozen=True, slots=True)
class UpdateConfig:
    """Configuração imutável usada pelo serviço e pelo helper."""

    owner: str = UPDATE_REPOSITORY_OWNER
    repository: str = UPDATE_REPOSITORY_NAME
    package_id: str = ""
    interval_hours: int = UPDATE_CHECK_INTERVAL_HOURS

    def __post_init__(self) -> None:
        if not self.package_id:
            object.__setattr__(self, "package_id", platform_package_id())
        if self.interval_hours <= 0:
            raise ValueError("interval_hours deve ser positivo")

    @property
    def configured(self) -> bool:
        return bool(self.owner.strip() and self.repository.strip())

    @property
    def api_url(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repository}/releases/latest"

    @property
    def releases_url(self) -> str:
        """URL da lista usada para escolher a maior versão publicada."""
        return f"https://api.github.com/repos/{self.owner}/{self.repository}/releases?per_page=100"

    @property
    def repository_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}"

    @property
    def package_name(self) -> str:
        return f"{self.package_id}.zip"

    @property
    def checksum_name(self) -> str:
        return f"{self.package_id}.sha256"
