"""Serviços de atualização por GitHub Releases."""

from .config import UpdateConfig
from .service import PreparedUpdate, ReleaseInfo, UpdateError, UpdateService

__all__ = [
    "PreparedUpdate",
    "ReleaseInfo",
    "UpdateConfig",
    "UpdateError",
    "UpdateService",
]
