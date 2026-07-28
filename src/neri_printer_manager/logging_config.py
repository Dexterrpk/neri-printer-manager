"""Configuração central de logs da aplicação."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .security import redact_text


class _RedactingFilter(logging.Filter):
    """Higieniza qualquer mensagem antes de gravá-la no disco."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


def configure_logging() -> Path:
    """Ativa log rotativo no diretório de dados do usuário.

    O arquivo é limitado para evitar crescimento indefinido em computadores de
    atendimento. Cinco backups de 1 MiB são mantidos.
    """
    log_dir = Path.home() / ".local" / "state" / "neri-printer-manager"
    log_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    log_dir.chmod(0o700)
    log_file = log_dir / "application.log"
    log_file.touch(mode=0o600, exist_ok=True)
    log_file.chmod(0o600)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_RedactingFilter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(
        isinstance(item, RotatingFileHandler) and Path(item.baseFilename) == log_file
        for item in root.handlers
    ):
        root.addHandler(handler)
    else:
        handler.close()
    return log_file
