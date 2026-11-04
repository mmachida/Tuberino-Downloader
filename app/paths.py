"""Caminhos do aplicativo e dos recursos empacotados."""

from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """Retorna a pasta gravável ao lado do executável ou a raiz do projeto."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Retorna a pasta de recursos, incluindo a extração temporária do one-file."""

    if getattr(sys, "frozen", False):
        extracted_root = getattr(sys, "_MEIPASS", None)
        if extracted_root:
            return Path(extracted_root)
        return application_root()
    return application_root()
