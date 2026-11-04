"""Configuração comum para executar ferramentas externas sem janela no Windows."""

from __future__ import annotations

import os
import subprocess


def hidden_process_kwargs() -> dict[str, object]:
    """Retorna opções para iniciar um processo sem exibir uma janela de console."""

    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": startupinfo,
    }
