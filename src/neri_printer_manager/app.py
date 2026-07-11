"""Interface gráfica principal do Neri Printer Manager.

Operações potencialmente lentas rodam em workers para manter a interface
responsiva durante consultas ao CUPS, leitura de logs e reparos.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .backup import BackupService
from .core import CupsService, DiagnosticService, DiscoveryService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .logging_config import configure_logging
from .repair import RepairService
from .sharing import SharingService
from .wizard import PrinterWizard


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
        except Exception as exc:
            self.signals.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Neri Printer Manager")
        self.resize(1180, 760)
        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()
        self.jobs_service = JobService()
        self.filter_findings: list[Any] = []

        tabs = QTabWidget()
        tabs.addTab(self._build_overview_tab(), "Visão geral")
        tabs.addTab(self._build_printers_tab(), "Impressoras")
        tabs.addTab(self._build_jobs_tab(), "Fila")
        tabs.addTab(self._build_discovery_tab(), "Descoberta")
        tabs.addTab(self._build_diagnostics_tab(), "Diagnóstico")
        tabs.addTab(self._build_dependencies_tab(), "Dependências")
        tabs.addTab(self._build_filters_tab(), "Filtros CUPS")
        tabs.addTab(self._build_sharing_tab(), "Compartilhamento")
        self.setCentralWidget(tabs)

        self.statusBar().showMessage("Pronto")
        self.refresh_all()

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    @staticmethod
    def _button(text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.overview_label = QLabel("Carregando status do ambiente...")
        self.overview_label.setWordWrap(True)
        layout.addWidget(self.overview_label)
        layout.addWidget(self._button("Atualizar tudo", self.refresh_all))
        layout.addStretch()
        return widget

    def _build_printers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.printers = self._table(["Fila", "Estado", "Ativa", "Aceitando", "URI"])
        layout.addWidget(self.printers)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Adicionar", self.open_printer_wizard))
        actions.addWidget(self._button("Atualizar", self.refresh_printers))
        actions.addWidget(self._button("Página de teste", self.print_test_page))
        actions.addWidget(self._button("Pausar", self.pause_printer))
        actions.addWidget(self._button("Retomar", self.resume_printer))
        actions.addWidget(self._button("Remover", self.remove_printer))
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _build_jobs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.jobs = self._table(["Trabalho", "Usuário", "Tamanho", "Enviado em"])
        layout.addWidget(self.jobs)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Atualizar", self.refresh_jobs))
        actions.addWidget(self._button("Cancelar trabalho", self.cancel_job))
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _build_discovery_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.devices = self._table(["Protocolo", "Descrição", "URI"])
        layout.addWidget(self.devices)
        layout.addWidget(self._button("Procurar impressoras", self.refresh_discovery))
        return widget

    def _build_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.diagnostics = self._table(["Item", "Resultado", "Mensagem", "Correção"])
        layout.addWidget(self.diagnostics)
        layout.addWidget(self._button("Executar diagnóstico", self.refresh_diagnostics))
        return widget

    def _build_dependencies_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.dependencies = self._table(["Pacote", "Obrigatório", "Estado", "Versão", "Motivo"])
        layout.addWidget(self.dependencies)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Verificar", self.refresh_dependencies))
        actions.addWidget(self._button("Instalar obrigatórias", self.repair_dependencies))
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _build_filters_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.filters = self._table(["Falha", "Gravidade", "Evidência", "Ações"])
        layout.addWidget(self.filters)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Analisar filtros", self.refresh_filters))
        actions.addWidget(self._button("Corrigir selecionada", self.repair_selected_filter))
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _build_sharing_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.sharing = self._table(["Componente", "Estado", "Mensagem", "Correção"])
        layout.addWidget(self.sharing)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Verificar compartilhamento", self.refresh_sharing))
        actions.addWidget(self._button("Criar backup", self.create_backup))
        actions.addStretch()
        layout.addLayout(actions)
        return widget

    def _run(self, function: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self.statusBar().showMessage("Processando...")
        worker = Worker(function)
        worker.signals.success.connect(callback)
        worker.signals.success.connect(lambda _: self.statusBar().showMessage("Concluído", 3000))
        worker.signals.error.connect(self._show_error)
        self.pool.start(worker)

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage("Falha", 5000)
        QMessageBox.critical(self, "Falha", message)

    def refresh_all(self) -> None:
        self.refresh_printers()
        self.refresh_jobs()
        self.refresh_diagnostics()
        self.refresh_dependencies()
        self.refresh_filters()
        self.refresh_sharing()

    def refresh_printers(self) -> None:
        self._run(self.cups.list_printers, self._show_printers)

    def refresh_jobs(self) -> None:
        self._run(self.jobs_service.list_jobs, self._show_jobs)

    def refresh_discovery(self) -> None:
        self._run(DiscoveryService().discover, self._show_devices)

    def refresh_diagnostics(self) -> None:
        self._run(DiagnosticService().run_all, self._show_diagnostics)

    def refresh_dependencies(self) -> None:
        self._run(DependencyService().audit, self._show_dependencies)

    def refresh_filters(self) -> None:
        self._run(CupsFilterService().diagnose, self._show_filters)

    def refresh_sharing(self) -> None:
        self._run(SharingService().audit, self._show_sharing)

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
        self._update_overview()

    def _show_jobs(self, items: list[Any]) -> None:
        self.jobs.setRowCount(len(items))
        for row, item in enumerate(items):
            for column, value in enumerate((item.job_id, item.owner, item.size, item.submitted)):
                self.jobs.setItem(row, column, QTableWidgetItem(str(value)))
        self._update_overview()

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
                self.diagnostics.setItem(row, column, QTableWidgetItem(str(value)))
        self._update_overview()

    def _show_dependencies(self, items: list[Any]) -> None:
        self.dependencies.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (
                item.requirement.name,
                "Sim" if item.requirement.required else "Não",
                item.state.value,
                item.version or "",
                item.requirement.reason,
            )
            for column, value in enumerate(values):
                self.dependencies.setItem(row, column, QTableWidgetItem(str(value)))
        self._update_overview()

    def _show_filters(self, items: list[Any]) -> None:
        self.filter_findings = items
        self.filters.setRowCount(len(items))
        for row, item in enumerate(items):
            actions = ", ".join(action.value for action in item.actions)
            values = (item.title, item.severity.value, item.evidence, actions)
            for column, value in enumerate(values):
                self.filters.setItem(row, column, QTableWidgetItem(str(value)))
        self._update_overview()

    def _show_sharing(self, items: list[Any]) -> None:
        self.sharing.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (item.component, item.state.value, item.message, item.remediation or "")
            for column, value in enumerate(values):
                self.sharing.setItem(row, column, QTableWidgetItem(str(value)))

    def _update_overview(self) -> None:
        self.overview_label.setText(
            f"Impressoras instaladas: {self.printers.rowCount()}\n"
            f"Trabalhos na fila: {self.jobs.rowCount()}\n"
            f"Diagnósticos exibidos: {self.diagnostics.rowCount()}\n"
            f"Dependências verificadas: {self.dependencies.rowCount()}\n"
            f"Falhas de filtros encontradas: {self.filters.rowCount()}"
        )

    def _selected_printer(self) -> str | None:
        row = self.printers.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleção", "Selecione uma impressora.")
            return None
        return self.printers.item(row, 0).text()

    def open_printer_wizard(self) -> None:
        wizard = PrinterWizard(self.cups, self)
        if wizard.exec():
            self.refresh_printers()

    def print_test_page(self) -> None:
        name = self._selected_printer()
        if name:
            self._run(
                lambda: self.cups.print_test_page(name),
                lambda _: QMessageBox.information(self, "Sucesso", "Página enviada."),
            )

    def pause_printer(self) -> None:
        name = self._selected_printer()
        if name:
            self._run(lambda: self.cups.pause(name), lambda _: self.refresh_printers())

    def resume_printer(self) -> None:
        name = self._selected_printer()
        if name:
            self._run(lambda: self.cups.resume(name), lambda _: self.refresh_printers())

    def remove_printer(self) -> None:
        name = self._selected_printer()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Remover impressora",
            f"Confirma a remoção da fila {name}?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run(lambda: self.cups.remove_printer(name), lambda _: self.refresh_printers())

    def cancel_job(self) -> None:
        row = self.jobs.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seleção", "Selecione um trabalho.")
            return
        job_id = self.jobs.item(row, 0).text()
        self._run(lambda: self.jobs_service.cancel(job_id), lambda _: self.refresh_jobs())

    def repair_dependencies(self) -> None:
        self._run(
            RepairService().install_missing_dependencies,
            lambda result: (
                QMessageBox.information(self, "Dependências", result.message),
                self.refresh_dependencies(),
            ),
        )

    def repair_selected_filter(self) -> None:
        row = self.filters.currentRow()
        if row < 0 or row >= len(self.filter_findings):
            QMessageBox.information(self, "Seleção", "Selecione uma falha de filtro.")
            return
        finding = self.filter_findings[row]
        self._run(
            lambda: RepairService().repair_filter_finding(finding),
            lambda _: self.refresh_filters(),
        )

    def create_backup(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta para backup")
        if not selected:
            return
        destination = Path(selected)
        self._run(
            lambda: BackupService().create(destination),
            lambda info: QMessageBox.information(
                self,
                "Backup concluído",
                f"Arquivo: {info.archive}\nSHA-256: {info.sha256}",
            ),
        )


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("Neri Printer Manager")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
