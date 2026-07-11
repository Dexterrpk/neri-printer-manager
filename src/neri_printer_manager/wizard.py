"""Assistente gráfico para instalação de impressoras."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QWizard,
    QWizardPage,
)

from .core import CupsService, validate_device_uri, validate_queue_name


class PrinterWizard(QWizard):
    """Coleta os dados essenciais e cria a fila via CUPS."""

    def __init__(self, cups: CupsService, parent=None) -> None:
        super().__init__(parent)
        self.cups = cups
        self.setWindowTitle("Adicionar impressora")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        page = QWizardPage()
        page.setTitle("Configuração da impressora")
        form = QFormLayout(page)

        self.name = QLineEdit()
        self.protocol = QComboBox()
        self.protocol.addItems(["IPP", "JetDirect", "LPD", "SMB", "URI manual"])
        self.address = QLineEdit()
        self.queue = QLineEdit()
        self.model = QLineEdit("everywhere")

        form.addRow("Nome da fila", self.name)
        form.addRow("Protocolo", self.protocol)
        form.addRow("Endereço/host", self.address)
        form.addRow("Fila/caminho", self.queue)
        form.addRow("Modelo CUPS", self.model)
        self.addPage(page)

    def _build_uri(self) -> str:
        protocol = self.protocol.currentText()
        host = self.address.text().strip()
        path = self.queue.text().strip().lstrip("/")
        if protocol == "IPP":
            return f"ipp://{host}/{path or 'ipp/print'}"
        if protocol == "JetDirect":
            return f"socket://{host}:9100"
        if protocol == "LPD":
            return f"lpd://{host}/{path or 'lp'}"
        if protocol == "SMB":
            return f"smb://{host}/{path}"
        return self.address.text().strip()

    def accept(self) -> None:
        try:
            name = validate_queue_name(self.name.text())
            uri = validate_device_uri(self._build_uri())
            model = self.model.text().strip() or "everywhere"
            self.cups.add_printer(name, uri, model)
        except Exception as exc:
            QMessageBox.critical(self, "Falha ao instalar", str(exc))
            return
        QMessageBox.information(self, "Sucesso", "Impressora instalada com sucesso.")
        super().accept()
