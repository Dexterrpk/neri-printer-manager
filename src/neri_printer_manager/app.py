"""Interface gráfica principal.

Chamadas ao sistema rodam em workers para não congelar a janela durante
varreduras de rede ou consultas ao CUPS.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import CupsService, DiagnosticService, DiscoveryService


class WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.success.emit(self.function())
        except Exception as exc:  # A fronteira da UI converte qualquer falha em mensagem.
            self.signals.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Neri Printer Manager")
        self.resize(1050, 680)
        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()

        tabs = QTabWidget()
        tabs.addTab(self._build_printers_tab(), "Impressoras")
        tabs.addTab(self._build_discovery_tab(), "Descoberta")
        tabs.addTab(self._build_diagnostics_tab(), "Diagnóstico")
        self.setCentralWidget(tabs)
        self.refresh_printers()

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    def _build_printers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.printers = self._table(["Fila", "Estado", "Ativa", "Aceitando", "URI"])
        layout.addWidget(self.printers)
        actions = QHBoxLayout()
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh_printers)
        test = QPushButton("Página de teste")
        test.clicked.connect(self.print_test_page)
        actions.addWidget(refresh)
        actions.addWidget(test)
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _build_discovery_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.devices = self._table(["Protocolo", "Descrição", "URI"])
        layout.addWidget(self.devices)
        discover = QPushButton("Procurar impressoras")
        discover.clicked.connect(self.refresh_discovery)
        layout.addWidget(discover)
        return widget

    def _build_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.diagnostics = self._table(["Item", "Resultado", "Mensagem", "Correção"])
        layout.addWidget(self.diagnostics)
        run = QPushButton("Executar diagnóstico")
        run.clicked.connect(self.refresh_diagnostics)
        layout.addWidget(run)
        return widget

    def _run(self, function: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        worker = Worker(function)
        worker.signals.success.connect(callback)
        worker.signals.error.connect(
            lambda message: QMessageBox.critical(self, "Falha", message)
        )
        self.pool.start(worker)

    def refresh_printers(self) -> None:
        self._run(self.cups.list_printers, self._show_printers)

    def refresh_discovery(self) -> None:
        self._run(DiscoveryService().discover, self._show_devices)

    def refresh_diagnostics(self) -> None:
        self._run(DiagnosticService().run_all, self._show_diagnostics)

    def _show_printers(self, items: list[Any]) -> None:
        self.printers.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (
                item.name,
                item.state,
                "Sim" if item.enabled else "Não",
                "Sim" if item.accepting else "Não",
                item.device_uri or "",
            )
            for column, value in enumerate(values):
                self.printers.setItem(row, column, QTableWidgetItem(str(value)))

    def _show_devices(self, items: list[Any]) -> None:
        self.devices.setRowCount(len(items))
        for row, item in enumerate(items):
            for column, value in enumerate((item.protocol, item.description, item.uri)):
                self.devices.setItem(row, column, QTableWidgetItem(value))

    def _show_diagnostics(self, items: list[Any]) -> None:
        self.diagnostics.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (item.title, item.severity.value, item.message, item.remediation or "")
            for column, value in enumerate(values):
                self.diagnostics.setItem(row, column, QTableWidgetItem(value))

    def print_test_page(self) -> None:
        row = self.printers.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleção", "Selecione uma impressora.")
            return
        name = self.printers.item(row, 0).text()
        self._run(
            lambda: self.cups.print_test_page(name),
            lambda _: QMessageBox.information(self, "Sucesso", "Página enviada."),
        )


def main() -> int:
    application = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
