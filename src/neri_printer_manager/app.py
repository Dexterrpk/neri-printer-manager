"""Interface gráfica completa do Neri Printer Manager."""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .backup import BackupService
from .core import CupsService, DiagnosticService, DiscoveryService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .logging_config import configure_logging
from .network import NetworkService
from .repair import RepairService
from .reports import ReportService
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
    def __init__(self, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Neri Printer Manager")
        self.resize(1240, 820)
        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()
        self.jobs_service = JobService()
        self.filter_findings: list[Any] = []

        tabs = QTabWidget()
        for title, builder in (
            ("Visão geral", self._overview_tab),
            ("Impressoras", self._printers_tab),
            ("Fila", self._jobs_tab),
            ("Descoberta", self._discovery_tab),
            ("Rede", self._network_tab),
            ("Diagnóstico", self._diagnostics_tab),
            ("Dependências", self._dependencies_tab),
            ("Filtros CUPS", self._filters_tab),
            ("Compartilhamento", self._sharing_tab),
            ("Relatórios", self._reports_tab),
        ):
            tabs.addTab(builder(), title)
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Pronto")
        if auto_refresh:
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

    def _overview_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.overview = QLabel("Carregando..."); self.overview.setWordWrap(True)
        layout.addWidget(self.overview); layout.addWidget(self._button("Atualizar tudo", self.refresh_all)); layout.addStretch()
        return tab

    def _printers_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.printers = self._table(["Fila", "Estado", "Ativa", "Aceitando", "URI"])
        layout.addWidget(self.printers); actions = QHBoxLayout()
        for text, callback in (
            ("Adicionar", self.open_wizard), ("Atualizar", self.refresh_printers),
            ("Página de teste", self.test_page), ("Pausar", self.pause_printer),
            ("Retomar", self.resume_printer), ("Remover", self.remove_printer),
        ): actions.addWidget(self._button(text, callback))
        actions.addStretch(); layout.addLayout(actions); return tab

    def _jobs_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.jobs = self._table(["Trabalho", "Usuário", "Tamanho", "Enviado em"]); layout.addWidget(self.jobs)
        actions = QHBoxLayout(); actions.addWidget(self._button("Atualizar", self.refresh_jobs)); actions.addWidget(self._button("Cancelar", self.cancel_job)); actions.addStretch(); layout.addLayout(actions)
        return tab

    def _discovery_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.devices = self._table(["Protocolo", "Descrição", "URI"]); layout.addWidget(self.devices)
        layout.addWidget(self._button("Procurar impressoras", self.refresh_discovery)); return tab

    def _network_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab); top = QHBoxLayout()
        self.network_host = QLineEdit(); self.network_host.setPlaceholderText("IP ou hostname")
        top.addWidget(self.network_host); top.addWidget(self._button("Testar portas", self.scan_network)); layout.addLayout(top)
        self.network = self._table(["Host", "Porta", "Serviço", "Estado", "Mensagem"]); layout.addWidget(self.network)
        return tab

    def _diagnostics_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.diagnostics = self._table(["Item", "Resultado", "Mensagem", "Correção"]); layout.addWidget(self.diagnostics)
        layout.addWidget(self._button("Executar diagnóstico", self.refresh_diagnostics)); return tab

    def _dependencies_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.dependencies = self._table(["Pacote", "Obrigatório", "Estado", "Versão", "Motivo"]); layout.addWidget(self.dependencies)
        actions = QHBoxLayout(); actions.addWidget(self._button("Verificar", self.refresh_dependencies)); actions.addWidget(self._button("Instalar obrigatórias", self.repair_dependencies)); actions.addStretch(); layout.addLayout(actions)
        return tab

    def _filters_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.filters = self._table(["Falha", "Gravidade", "Evidência", "Ações"]); layout.addWidget(self.filters)
        actions = QHBoxLayout(); actions.addWidget(self._button("Analisar", self.refresh_filters)); actions.addWidget(self._button("Corrigir selecionada", self.repair_filter)); actions.addStretch(); layout.addLayout(actions)
        return tab

    def _sharing_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self.sharing = self._table(["Componente", "Estado", "Mensagem", "Correção"]); layout.addWidget(self.sharing)
        actions = QHBoxLayout(); actions.addWidget(self._button("Verificar", self.refresh_sharing)); actions.addWidget(self._button("Criar backup", self.create_backup)); actions.addStretch(); layout.addLayout(actions)
        return tab

    def _reports_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        label = QLabel("Relatórios técnicos e pacote ZIP para suporte."); label.setWordWrap(True); layout.addWidget(label)
        layout.addWidget(self._button("Exportar JSON", self.export_json))
        layout.addWidget(self._button("Exportar HTML", self.export_html))
        layout.addWidget(self._button("Criar pacote de suporte ZIP", self.export_bundle)); layout.addStretch(); return tab

    def _run(self, function: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self.statusBar().showMessage("Processando...")
        worker = Worker(function); worker.signals.success.connect(callback)
        worker.signals.success.connect(lambda _: self.statusBar().showMessage("Concluído", 3000))
        worker.signals.error.connect(self._error); self.pool.start(worker)

    def _error(self, message: str) -> None:
        self.statusBar().showMessage("Falha", 5000); QMessageBox.critical(self, "Falha", message)

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[Any, ...]]) -> None:
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values): table.setItem(row, column, QTableWidgetItem(str(value)))

    def refresh_all(self) -> None:
        for action in (self.refresh_printers, self.refresh_jobs, self.refresh_diagnostics, self.refresh_dependencies, self.refresh_filters, self.refresh_sharing): action()

    def refresh_printers(self) -> None: self._run(self.cups.list_printers, self._show_printers)
    def refresh_jobs(self) -> None: self._run(self.jobs_service.list_jobs, self._show_jobs)
    def refresh_discovery(self) -> None: self._run(DiscoveryService().discover, self._show_devices)
    def refresh_diagnostics(self) -> None: self._run(DiagnosticService().run_all, self._show_diagnostics)
    def refresh_dependencies(self) -> None: self._run(DependencyService().audit, self._show_dependencies)
    def refresh_filters(self) -> None: self._run(CupsFilterService().diagnose, self._show_filters)
    def refresh_sharing(self) -> None: self._run(SharingService().audit, self._show_sharing)

    def _show_printers(self, items: list[Any]) -> None:
        self._fill(self.printers, [(i.name, i.state, "Sim" if i.enabled else "Não", "Sim" if i.accepting else "Não", i.device_uri or "") for i in items]); self._summary()
    def _show_jobs(self, items: list[Any]) -> None:
        self._fill(self.jobs, [(i.job_id, i.owner, i.size, i.submitted) for i in items]); self._summary()
    def _show_devices(self, items: list[Any]) -> None: self._fill(self.devices, [(i.protocol, i.description, i.uri) for i in items])
    def _show_diagnostics(self, items: list[Any]) -> None:
        self._fill(self.diagnostics, [(i.title, i.severity.value, i.message, i.remediation or "") for i in items]); self._summary()
    def _show_dependencies(self, items: list[Any]) -> None:
        self._fill(self.dependencies, [(i.requirement.name, "Sim" if i.requirement.required else "Não", i.state.value, i.version or "", i.requirement.reason) for i in items]); self._summary()
    def _show_filters(self, items: list[Any]) -> None:
        self.filter_findings = items; self._fill(self.filters, [(i.title, i.severity.value, i.evidence, ", ".join(a.value for a in i.actions)) for i in items]); self._summary()
    def _show_sharing(self, items: list[Any]) -> None: self._fill(self.sharing, [(i.component, i.state.value, i.message, i.remediation or "") for i in items])
    def _show_network(self, items: list[Any]) -> None: self._fill(self.network, [(i.host, i.port, i.service, i.state.value, i.message) for i in items])

    def _summary(self) -> None:
        self.overview.setText(f"Impressoras: {self.printers.rowCount()}\nFila: {self.jobs.rowCount()}\nDiagnósticos: {self.diagnostics.rowCount()}\nDependências: {self.dependencies.rowCount()}\nFalhas de filtro: {self.filters.rowCount()}")

    def _selected_printer(self) -> str | None:
        row = self.printers.currentRow()
        if row < 0: QMessageBox.information(self, "Seleção", "Selecione uma impressora."); return None
        return self.printers.item(row, 0).text()

    def open_wizard(self) -> None:
        wizard = PrinterWizard(self.cups, self)
        if wizard.exec(): self.refresh_printers()
    def test_page(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.print_test_page(name), lambda _: QMessageBox.information(self, "Sucesso", "Página enviada."))
    def pause_printer(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.pause(name), lambda _: self.refresh_printers())
    def resume_printer(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.resume(name), lambda _: self.refresh_printers())
    def remove_printer(self) -> None:
        name = self._selected_printer()
        if name and QMessageBox.question(self, "Remover", f"Remover {name}?") == QMessageBox.StandardButton.Yes: self._run(lambda: self.cups.remove_printer(name), lambda _: self.refresh_printers())
    def cancel_job(self) -> None:
        row = self.jobs.currentRow()
        if row < 0: QMessageBox.information(self, "Seleção", "Selecione um trabalho."); return
        job_id = self.jobs.item(row, 0).text(); self._run(lambda: self.jobs_service.cancel(job_id), lambda _: self.refresh_jobs())
    def scan_network(self) -> None:
        host = self.network_host.text().strip()
        if not host: QMessageBox.information(self, "Rede", "Informe um IP ou hostname."); return
        self._run(lambda: NetworkService().scan_printer_ports(host), self._show_network)
    def repair_dependencies(self) -> None:
        self._run(RepairService().install_missing_dependencies, lambda result: (QMessageBox.information(self, "Dependências", result.message), self.refresh_dependencies()))
    def repair_filter(self) -> None:
        row = self.filters.currentRow()
        if row < 0 or row >= len(self.filter_findings): QMessageBox.information(self, "Seleção", "Selecione uma falha."); return
        finding = self.filter_findings[row]; self._run(lambda: RepairService().repair_filter_finding(finding), lambda _: self.refresh_filters())
    def create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta do backup")
        if folder: self._run(lambda: BackupService().create(Path(folder)), lambda info: QMessageBox.information(self, "Backup", f"{info.archive}\nSHA-256: {info.sha256}"))
    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salvar JSON", "relatorio-neri.json", "JSON (*.json)")
        if path: self._run(lambda: ReportService().write_json(Path(path)), lambda result: QMessageBox.information(self, "Relatório", str(result)))
    def export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salvar HTML", "relatorio-neri.html", "HTML (*.html)")
        if path: self._run(lambda: ReportService().write_html(Path(path)), lambda result: QMessageBox.information(self, "Relatório", str(result)))
    def export_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta do pacote de suporte")
        if folder: self._run(lambda: ReportService().create_support_bundle(Path(folder)), lambda result: QMessageBox.information(self, "Pacote de suporte", str(result)))


def main() -> int:
    configure_logging(); application = QApplication(sys.argv); application.setApplicationName("Neri Printer Manager")
    window = MainWindow(); window.show(); return application.exec()


if __name__ == "__main__": raise SystemExit(main())
