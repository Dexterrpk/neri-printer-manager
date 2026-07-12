"""Interface guiada e completa do Neri Printer Manager."""
from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from .backup import BackupService
from .core import CupsService, DiagnosticService, DiscoveryService, JobService
from .cups_filters import CupsFilterService
from .dependencies import DependencyService
from .host_locator import HostPrinterLocator, LocatedPrinter
from .logging_config import configure_logging
from .repair import RepairService
from .reports import ReportService
from .sharing import SharingService
from .smart_install import InstallOutcome, SmartPrinterInstaller

STYLE = """
QMainWindow,QWidget{background:#f5f7fa;color:#17202a;font-size:14px}
QListWidget#nav{background:#14213d;color:#fff;border:0;padding:12px}
QListWidget#nav::item{padding:14px 12px;margin:3px;border-radius:9px}
QListWidget#nav::item:selected{background:#2d7ff9}
QFrame#card{background:#fff;border:1px solid #dce3ea;border-radius:14px}
QLabel#title{font-size:28px;font-weight:700}
QLabel#muted{color:#607080}
QLineEdit{background:#fff;border:1px solid #c8d2dc;border-radius:10px;padding:12px}
QPushButton{background:#e8edf2;border:0;border-radius:9px;padding:11px 16px;font-weight:600}
QPushButton#primary{background:#2d7ff9;color:#fff}
QPushButton#danger{background:#ffe4e4;color:#9b1c1c}
QTableWidget{background:#fff;border:1px solid #dce3ea;border-radius:10px;gridline-color:#edf1f4}
QHeaderView::section{background:#edf2f6;border:0;padding:9px;font-weight:700}
"""


class Signals(QObject):
    success = Signal(object)
    error = Signal(str)
    finished = Signal()


class Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self) -> None:
        try:
            self.signals.success.emit(self.fn())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class GuidedWindow(QMainWindow):
    NAV = (
        "Início", "Encontrar na rede", "Minhas impressoras", "Fila",
        "Correção e diagnóstico", "Compartilhamento", "Ferramentas",
    )

    def __init__(self, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Neri Printer Manager")
        self.resize(1240, 800)
        self.setMinimumSize(1000, 660)
        self.setStyleSheet(STYLE)
        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()
        self.jobs_service = JobService()
        self.located: list[LocatedPrinter] = []
        self.filter_findings: list[Any] = []
        self._tasks: set[Task] = set()

        root = QWidget(); root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0); root_layout.setSpacing(0)
        self.nav = QListWidget(); self.nav.setObjectName("nav"); self.nav.setFixedWidth(245)
        for text in self.NAV: self.nav.addItem(QListWidgetItem(text))
        self.pages = QStackedWidget()
        for page in (
            self._home(), self._finder(), self._printers(), self._jobs(),
            self._diagnostics(), self._sharing(), self._tools(),
        ): self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self._navigate)
        root_layout.addWidget(self.nav); root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root); self.statusBar().showMessage("Pronto")
        self.nav.setCurrentRow(0)
        if auto_refresh:
            self.refresh_printers(); self.refresh_jobs()

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget(); layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(14)
        heading = QLabel(title); heading.setObjectName("title")
        text = QLabel(subtitle); text.setObjectName("muted"); text.setWordWrap(True)
        layout.addWidget(heading); layout.addWidget(text)
        return page, layout

    @staticmethod
    def _card() -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(); frame.setObjectName("card")
        layout = QVBoxLayout(frame); layout.setContentsMargins(20, 18, 20, 18)
        return frame, layout

    @staticmethod
    def _button(text: str, callback: Callable[[], None], primary: bool = False, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary: button.setObjectName("primary")
        if danger: button.setObjectName("danger")
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def _home(self) -> QWidget:
        page, layout = self._page(
            "Gerencie impressoras sem complicação",
            "Localize por nome ou IP, instale, teste e corrija problemas em um só lugar.",
        )
        card, card_layout = self._card()
        self.home_input = QLineEdit(); self.home_input.setPlaceholderText("Ex.: MAQ211, \\SERVIDOR ou 192.168.1.65")
        self.home_input.returnPressed.connect(self.search_from_home)
        row = QHBoxLayout(); row.addWidget(self.home_input, 1); row.addWidget(self._button("Localizar", self.search_from_home, True))
        card_layout.addWidget(QLabel("Nome da máquina ou IP")); card_layout.addLayout(row)
        layout.addWidget(card)
        shortcuts = QHBoxLayout()
        for title, callback in (("Minhas impressoras", lambda: self.nav.setCurrentRow(2)), ("Corrigir problemas", lambda: self.nav.setCurrentRow(4)), ("Ferramentas", lambda: self.nav.setCurrentRow(6))):
            shortcuts.addWidget(self._button(title, callback, True))
        layout.addLayout(shortcuts); layout.addStretch(); return page

    def _finder(self) -> QWidget:
        page, layout = self._page("Encontrar impressora na rede", "Informe credenciais somente quando o computador remoto exigir login.")
        row = QHBoxLayout(); self.find_input = QLineEdit(); self.find_input.setPlaceholderText("Nome, IP, \\NOME ou smb://NOME")
        self.find_input.returnPressed.connect(self.search); row.addWidget(self.find_input, 1); row.addWidget(self._button("Buscar", self.search, True)); layout.addLayout(row)
        card, auth = self._card(); auth.addWidget(QLabel("Acesso remoto (opcional)"))
        auth_row = QHBoxLayout(); self.smb_user = QLineEdit(); self.smb_user.setPlaceholderText("Usuário")
        self.smb_password = QLineEdit(); self.smb_password.setPlaceholderText("Senha"); self.smb_password.setEchoMode(QLineEdit.EchoMode.Password)
        auth_row.addWidget(self.smb_user); auth_row.addWidget(self.smb_password); auth.addLayout(auth_row); layout.addWidget(card)
        self.find_status = QLabel("Aguardando pesquisa."); self.find_status.setObjectName("muted"); self.find_status.setWordWrap(True); layout.addWidget(self.find_status)
        self.results = self._table(["Impressora", "Computador/IP", "Conexão", "Prioridade"]); layout.addWidget(self.results, 1)
        actions = QHBoxLayout(); actions.addWidget(self._button("Instalar selecionada", self.install_selected, True)); actions.addStretch(); layout.addLayout(actions)
        return page

    def _printers(self) -> QWidget:
        page, layout = self._page("Minhas impressoras", "Filas configuradas no CUPS deste computador.")
        self.printer_status = QLabel("Carregando impressoras..."); self.printer_status.setObjectName("muted"); layout.addWidget(self.printer_status)
        self.printer_table = self._table(["Nome", "Estado", "Ativa", "Aceitando", "Endereço"]); layout.addWidget(self.printer_table, 1)
        row = QHBoxLayout()
        for text, callback, primary, danger in (
            ("Atualizar", self.refresh_printers, True, False),
            ("Página de teste", self.test_page, False, False),
            ("Pausar", self.pause_printer, False, False),
            ("Retomar", self.resume_printer, False, False),
            ("Remover", self.remove_printer, False, True),
        ): row.addWidget(self._button(text, callback, primary, danger))
        row.addStretch(); layout.addLayout(row); return page

    def _jobs(self) -> QWidget:
        page, layout = self._page("Fila de impressão", "Trabalhos aguardando no CUPS.")
        self.job_table = self._table(["Trabalho", "Usuário", "Tamanho", "Enviado em"]); layout.addWidget(self.job_table, 1)
        row = QHBoxLayout(); row.addWidget(self._button("Atualizar", self.refresh_jobs, True)); row.addWidget(self._button("Cancelar selecionado", self.cancel_job)); row.addStretch(); layout.addLayout(row)
        return page

    def _diagnostics(self) -> QWidget:
        page, layout = self._page("Correção e diagnóstico", "Verifique CUPS, dependências e filtros e aplique correções seguras.")
        self.diag_summary = QLabel("Clique em Verificar tudo."); self.diag_summary.setObjectName("muted"); layout.addWidget(self.diag_summary)
        self.diag_table = self._table(["Item", "Estado", "Mensagem", "Correção"]); layout.addWidget(self.diag_table, 1)
        row = QHBoxLayout(); row.addWidget(self._button("Verificar tudo", self.refresh_diagnostics, True)); row.addWidget(self._button("Instalar dependências", self.repair_dependencies)); row.addWidget(self._button("Analisar filtros", self.refresh_filters)); row.addWidget(self._button("Corrigir filtro selecionado", self.repair_filter)); row.addStretch(); layout.addLayout(row)
        return page

    def _sharing(self) -> QWidget:
        page, layout = self._page("Compartilhamento", "Verifique se o computador está preparado para compartilhar impressoras.")
        self.sharing_table = self._table(["Componente", "Estado", "Mensagem", "Correção"]); layout.addWidget(self.sharing_table, 1)
        row = QHBoxLayout(); row.addWidget(self._button("Verificar", self.refresh_sharing, True)); row.addWidget(self._button("Criar backup", self.create_backup)); row.addStretch(); layout.addLayout(row)
        return page

    def _tools(self) -> QWidget:
        page, layout = self._page("Ferramentas", "Descoberta, relatórios e pacote de suporte.")
        self.tools_table = self._table(["Tipo", "Descrição", "Endereço"]); layout.addWidget(self.tools_table, 1)
        row = QHBoxLayout(); row.addWidget(self._button("Descobrir dispositivos", self.discover_devices, True)); row.addWidget(self._button("Exportar HTML", self.export_html)); row.addWidget(self._button("Pacote de suporte ZIP", self.export_bundle)); row.addStretch(); layout.addLayout(row)
        return page

    def _navigate(self, index: int) -> None:
        if index < 0: return
        self.pages.setCurrentIndex(index)
        if index == 2: self.refresh_printers()
        elif index == 3: self.refresh_jobs()
        elif index == 4: self.refresh_diagnostics()
        elif index == 5: self.refresh_sharing()

    def _run(self, fn: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self.statusBar().showMessage("Processando...")
        task = Task(fn); self._tasks.add(task)
        task.signals.success.connect(callback)
        task.signals.success.connect(lambda _: self.statusBar().showMessage("Concluído", 3000))
        task.signals.error.connect(self._error)
        task.signals.finished.connect(lambda task=task: self._tasks.discard(task))
        self.pool.start(task)

    def _error(self, message: str) -> None:
        self.statusBar().showMessage("Falha", 5000)
        if hasattr(self, "find_status"): self.find_status.setText(message)
        QMessageBox.warning(self, "Não foi possível concluir", message)

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[Any, ...]]) -> None:
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values): table.setItem(row, column, QTableWidgetItem(str(value)))

    def search_from_home(self) -> None:
        self.find_input.setText(self.home_input.text().strip()); self.nav.setCurrentRow(1); self.search()

    def search(self) -> None:
        value = self.find_input.text().strip()
        if not value: QMessageBox.information(self, "Informe o endereço", "Digite um nome de máquina ou IP."); return
        self.find_status.setText("Resolvendo nome e procurando impressoras..."); self.results.setRowCount(0)
        self._run(lambda: HostPrinterLocator().locate(value, username=self.smb_user.text().strip(), password=self.smb_password.text()), self._show_results)

    def _show_results(self, items: list[LocatedPrinter]) -> None:
        self.located = items
        self._fill(self.results, [(i.name, f"{i.host} ({i.address})", f"{i.protocol} — {i.connection}", "Recomendado" if i.recommended else "Alternativa") for i in items])
        if items:
            first = next((i for i in items if i.recommended), items[0]); self.results.selectRow(items.index(first))
            self.find_status.setText(f"{len(items)} opção(ões) encontrada(s) em {first.address}. Recomendação: {first.protocol}.")

    def install_selected(self) -> None:
        row = self.results.currentRow()
        if row < 0 or row >= len(self.located): QMessageBox.information(self, "Selecione", "Escolha uma impressora encontrada."); return
        item = self.located[row]; base = item.name if item.protocol == "SMB" else item.host
        queue = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-") or "Impressora-Rede"
        self.find_status.setText("Instalando impressora. Não feche o programa...")
        self._run(lambda: SmartPrinterInstaller(self.cups).install(queue, item), self._installed)

    def _installed(self, outcome: InstallOutcome) -> None:
        self.smb_password.clear()
        QMessageBox.information(self, "Impressora instalada", f"Fila: {outcome.queue}\nConexão: {outcome.uri}\nDriver: {outcome.description}")
        self.nav.setCurrentRow(2); self.refresh_printers()

    def refresh_printers(self) -> None:
        self.printer_status.setText("Consultando o CUPS..."); self._run(self.cups.list_printers, self._show_printers)

    def _show_printers(self, items: list[Any]) -> None:
        self._fill(self.printer_table, [(i.name, i.state, "Sim" if i.enabled else "Não", "Sim" if i.accepting else "Não", i.device_uri or "") for i in items])
        self.printer_status.setText(f"{len(items)} impressora(s) instalada(s)." if items else "Nenhuma impressora instalada no CUPS.")

    def _selected_printer(self) -> str | None:
        row = self.printer_table.currentRow()
        if row < 0: QMessageBox.information(self, "Selecione", "Escolha uma impressora."); return None
        return self.printer_table.item(row, 0).text()

    def test_page(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.print_test_page(name), lambda _: QMessageBox.information(self, "Página de teste", "Documento enviado para a fila."))

    def pause_printer(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.pause(name), lambda _: self.refresh_printers())

    def resume_printer(self) -> None:
        name = self._selected_printer()
        if name: self._run(lambda: self.cups.resume(name), lambda _: self.refresh_printers())

    def remove_printer(self) -> None:
        name = self._selected_printer()
        if name and QMessageBox.question(self, "Remover impressora", f"Remover a fila {name}?") == QMessageBox.StandardButton.Yes:
            self._run(lambda: self.cups.remove_printer(name), lambda _: self.refresh_printers())

    def refresh_jobs(self) -> None:
        self._run(self.jobs_service.list_jobs, lambda items: self._fill(self.job_table, [(i.job_id, i.owner, i.size, i.submitted) for i in items]))

    def cancel_job(self) -> None:
        row = self.job_table.currentRow()
        if row < 0: QMessageBox.information(self, "Selecione", "Escolha um trabalho."); return
        job_id = self.job_table.item(row, 0).text(); self._run(lambda: self.jobs_service.cancel(job_id), lambda _: self.refresh_jobs())

    def refresh_diagnostics(self) -> None:
        self._run(DiagnosticService().run_all, self._show_diagnostics)

    def _show_diagnostics(self, items: list[Any]) -> None:
        self._fill(self.diag_table, [(i.title, i.severity.value, i.message, i.remediation or "") for i in items])
        errors = sum(1 for i in items if i.severity.value == "error")
        self.diag_summary.setText("Ambiente saudável." if errors == 0 else f"Foram encontrados {errors} problema(s).")

    def repair_dependencies(self) -> None:
        self._run(RepairService().install_missing_dependencies, lambda result: (QMessageBox.information(self, "Dependências", result.message), self.refresh_diagnostics()))

    def refresh_filters(self) -> None:
        self._run(CupsFilterService().diagnose, self._show_filters)

    def _show_filters(self, items: list[Any]) -> None:
        self.filter_findings = items
        self._fill(self.diag_table, [(i.title, i.severity.value, i.evidence, ", ".join(a.value for a in i.actions)) for i in items])
        self.diag_summary.setText(f"{len(items)} resultado(s) na análise de filtros.")

    def repair_filter(self) -> None:
        row = self.diag_table.currentRow()
        if row < 0 or row >= len(self.filter_findings): QMessageBox.information(self, "Selecione", "Analise os filtros e escolha um resultado."); return
        finding = self.filter_findings[row]; self._run(lambda: RepairService().repair_filter_finding(finding), lambda _: self.refresh_filters())

    def refresh_sharing(self) -> None:
        self._run(SharingService().audit, lambda items: self._fill(self.sharing_table, [(i.component, i.state.value, i.message, i.remediation or "") for i in items]))

    def create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta do backup")
        if folder: self._run(lambda: BackupService().create(Path(folder)), lambda info: QMessageBox.information(self, "Backup criado", f"{info.archive}\nSHA-256: {info.sha256}"))

    def discover_devices(self) -> None:
        self._run(DiscoveryService().discover, lambda items: self._fill(self.tools_table, [(i.protocol, i.description, i.uri) for i in items]))

    def export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", "relatorio-neri.html", "HTML (*.html)")
        if path: self._run(lambda: ReportService().write_html(Path(path)), lambda result: QMessageBox.information(self, "Relatório", str(result)))

    def export_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta do pacote de suporte")
        if folder: self._run(lambda: ReportService().create_support_bundle(Path(folder)), lambda result: QMessageBox.information(self, "Pacote de suporte", str(result)))


def main() -> int:
    configure_logging(); app = QApplication(sys.argv); app.setApplicationName("Neri Printer Manager")
    window = GuidedWindow(); window.show(); return app.exec()


if __name__ == "__main__": raise SystemExit(main())
