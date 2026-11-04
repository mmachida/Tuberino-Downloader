"""Registro de eventos genéricos do aplicativo, sem detalhes técnicos."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path


class AppLogger:
    """Acrescenta erros compreensíveis em um TXT local do projeto."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def error(self, message: str) -> None:
        clean_message = _generic_message(message)
        if not clean_message:
            clean_message = "Ocorreu um erro não especificado."
        line = f"{datetime.now():%d/%m/%Y - %H:%M} - {clean_message}\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError:
            pass


def _generic_message(message: str) -> str:
    text = " ".join(str(message).split())
    text = re.sub(r"https?://\S+", "[link omitido]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(token|cookie|authorization|signature)\s*[:=]\s*\S+", r"\1=[omitido]", text)
    return text[:300]
