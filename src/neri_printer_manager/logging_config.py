"""Configuração central de logs da aplicação."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> Path:
    """Ativa log rotativo no diretório de dados do usuário.

    O arquivo é limitado para evitar crescimento indefinido em computadores de
    atendimento. Cinco backups de 1 MiB são mantidos.
    """
    log_dir = Path.home() / ".local" / "state" / "neri-printer-manager"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "application.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(item, RotatingFileHandler) for item in root.handlers):
        root.addHandler(handler)
    return log_file
