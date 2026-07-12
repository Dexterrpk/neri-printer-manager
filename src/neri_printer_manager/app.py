"""Interface moderna e guiada do Neri Printer Manager."""
from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
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
from .wizard import PrinterWizard


APP_STYLE = """
QMainWindow, QWidget { background: #f4f6f8; color: #17202a; font-size: 14px; }
QListWidget#sidebar { background: #17202a; color: #eef3f7; border: 0; padding: 12px; }
QListWidget#sidebar::item { padding: 13px 12px; margin: 3px 0; border-radius: 8px; }
QListWidget#sidebar::item:selected { background: #2d7ff9; color: white; }
QFrame#card { background: white; border: 1px solid #dfe5eb; border-radius: 14px; }
QLabel#title { font-size: 27px; font-weight: 700; color: #17202a; }
QLabel#subtitle { color: #5d6d7e; font-size: 14px; }
QLineEdit { background: white; border: 1px solid #c8d2dc; border-radius: 9px; padding: 11px; }
QLineEdit:focus { border: 2px solid #2d7ff9; }
QPushButton { background: #e9eef3; border: 0; border-radius: 9px; padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: #dce5ed; }
QPushButton#primary { background: #2d7ff9; color: white; }
QPushButton#primary:hover { background: #1768d7; }
QPushButton#danger { background: #ffe7e7; color: #a61b1b; }
QTableWidget { background: white; border: 1px solid #dfe5eb; border-radius: 10px; gridline-color: #edf1f4; }
QHeaderView::section { background: #eef2f5; border: 0; padding: 9px; font-weight: 700; }
"""


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
    NAVIGATION = (
        "Início",
        "Encontrar na rede",
        "Minhas impressoras",
        "Fila de impressão",
        "Corrigir problemas",
        "Compartilhamento",
        "Ferramentas técnicas",
    )

    def __init__(self, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Neri Printer Manager")
        self.resize(1180, 760)
        self.setMinimumSize(980, 650)
        self.setStyleSheet(APP_STYLE)
        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()
        self.jobs_service = JobService()
        self.located: list[LocatedPrinter] = []
        self.filter_findings: list[Any] = []

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(245)
        for name in self.NAVIGATION:
            self.sidebar.addItem(QListWidgetItem(name))
        self.sidebar.currentRowChanged.connect(self._navigate)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._home_page())
        self.pages.addWidget(self._find_page())
        self.pages.addWidget(self._printers_page())
        self.pages.addWidget(self._jobs_page())
        self.pages.addWidget(self._repair_page())
        self.pages.addWidget(self._sharing_page())
        self.pages.addWidget(self._tools_page())

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Pronto")
        self.sidebar.setCurrentRow(0)
        if auto_refresh:
            self.refresh_printers()
            self.refresh_jobs()

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("title")
        description = QLabel(subtitle)
        description.setObjectName("subtitle")
        description.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(description)
        return page, layout

    @staticmethod
    def _card() -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        return frame, layout

    @staticmethod
    def _button(text: str, callback: Callable[[], None], *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def _home_page(self) -> QWidget:
        page, layout = self._page(
            "Gerencie impressoras sem complicação",
            "Informe um IP ou nome de computador, deixe o programa localizar a impressora e escolher a melhor conexão.",
        )
        search_card, search_layout = self._card()
        search_title = QLabel("Localizar impressora ou computador")
        search_title.setStyleSheet("font-size:18px;font-weight:700")
        self.home_host = QLineEdit()
        self.home_host.setPlaceholderText("Ex.: 192.168.1.50 ou PC-RECEPCAO")
        self.home_host.returnPressed.connect(self.search_from_home)
        row = QHBoxLayout()
        row.addWidget(self.home_host, 1)
        row.addWidget(self._button("Buscar", self.search_from_home, primary=True))
        search_layout.addWidget(search_title)
        search_layout.addWidget(QLabel("O programa testa IPP, JetDirect, LPD e impressoras compartilhadas automaticamente."))
        search_layout.addLayout(row)
        layout.addWidget(search_card)

        actions = QHBoxLayout()
        for title, description, callback in (
            ("Instalar USB", "Procure impressoras conectadas diretamente ao computador.", self.open_wizard),
            ("Corrigir tudo", "Verifique CUPS, dependências e filtros de impressão.", self.run_quick_repair),
            ("Minhas impressoras", "Visualize, teste, pause ou remova filas instaladas.", lambda: self.sidebar.setCurrentRow(2)),
        ):
            card, card_layout = self._card()
            heading = QLabel(title)
            heading.setStyleSheet("font-size:17px;font-weight:700")
            text = QLabel(description)
            text.setWordWrap(True)
            card_layout.addWidget(heading)
            card_layout.addWidget(text)
            card_layout.addStretch()
            card_layout.addWidget(self._button("Abrir", callback, primary=True))
            actions.addWidget(card, 1)
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _find_page(self) -> QWidget:
        page, layout = self._page(
            "Encontrar impressora na rede",
            "Digite somente o IP ou nome do equipamento. Protocolos e endereços técnicos são montados automaticamente.",
        )
        top = QHBoxLayout()
        self.find_host = QLineEdit()
        self.find_host.setPlaceholderText("192.168.1.50 ou SERVIDOR-IMPRESSAO")
        self.find_host.returnPressed.connect(self.search_host)
        top.addWidget(self.find_host, 1)
        top.addWidget(self._button("Localizar", self.search_host, primary=True))
        layout.addLayout(top)
        self.find_status = QLabel("Aguardando pesquisa.")
        self.find_status.setObjectName("subtitle")
        layout.addWidget(self.find_status)
        self.results = self._table(["Impressora", "Origem", "Conexão encontrada", "Recomendação"])
        layout.addWidget(self.results, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Instalar selecionada", self.install_selected, primary=True))
        buttons.addWidget(self._button("Opções avançadas", self.open_wizard))
        buttons.addStretch()
        layout.addLayout(buttons)
        return page

    def _printers_page(self) -> QWidget:
        page, layout = self._page("Minhas impressoras", "Gerencie as impressoras já configuradas neste computador.")
        self.printers = self._table(["Nome", "Estado", "Ativa", "Aceitando", "Endereço"])
        layout.addWidget(self.printers, 1)
        row = QHBoxLayout()
        for text, callback, primary in (
            ("Adicionar", self.open_wizard, True),
            ("Atualizar", self.refresh_printers, False),
            ("Página de teste", self.test_page, False),
            ("Pausar", self.pause_printer, False),
            ("Retomar", self.resume_printer, False),
            ("Remover", self.remove_printer, False),
        ):
            row.addWidget(self._button(text, callback, primary=primary))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _jobs_page(self) -> QWidget:
        page, layout = self._page("Fila de impressão", "Veja documentos aguardando e cancele trabalhos travados.")
        self.jobs = self._table(["Trabalho", "Usuário", "Tamanho", "Enviado em"])
        layout.addWidget(self.jobs, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Atualizar", self.refresh_jobs))
        row.addWidget(self._button("Cancelar selecionado", self.cancel_job))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _repair_page(self) -> QWidget:
        page, layout = self._page("Corrigir problemas", "Execute verificações automáticas e veja correções em linguagem simples.")
        card, card_layout = self._card()
        self.repair_summary = QLabel("Clique em Verificar agora para analisar o ambiente.")
        self.repair_summary.setWordWrap(True)
        card_layout.addWidget(self.repair_summary)
        card_layout.addWidget(self._button("Verificar agora", self.run_diagnostics, primary=True))
        layout.addWidget(card)
        self.diagnostics = self._table(["Item", "Resultado", "Explicação", "O que fazer"])
        layout.addWidget(self.diagnostics, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Instalar dependências ausentes", self.repair_dependencies, primary=True))
        row.addWidget(self._button("Analisar filtros CUPS", self.refresh_filters))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _sharing_page(self) -> QWidget:
        page, layout = self._page("Compartilhamento", "Verifique se o computador está preparado para compartilhar com Linux ou Windows.")
        self.sharing = self._table(["Componente", "Estado", "Descrição", "Recomendação"])
        layout.addWidget(self.sharing, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Verificar", self.refresh_sharing, primary=True))
        row.addWidget(self._button("Criar backup", self.create_backup))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _tools_page(self) -> QWidget:
        page, layout = self._page("Ferramentas técnicas", "Relatórios e opções avançadas para suporte.")
        for title, description, callback in (
            ("Descobrir dispositivos", "Consulta os backends do CUPS e lista URIs detectadas.", self.discover_devices),
            ("Exportar relatório HTML", "Gera um relatório legível com sistema, filas e diagnósticos.", self.export_html),
            ("Criar pacote de suporte", "Reúne relatório e logs disponíveis em um arquivo ZIP.", self.export_bundle),
        ):
            card, card_layout = self._card()
            heading = QLabel(title)
            heading.setStyleSheet("font-size:17px;font-weight:700")
            card_layout.addWidget(heading)
            card_layout.addWidget(QLabel(description))
            card_layout.addWidget(self._button("Executar", callback, primary=True))
            layout.addWidget(card)
        layout.addStretch()
        return page

    def _navigate(self, index: int) -> None:
        if index >= 0:
            self.pages.setCurrentIndex(index)
        if index == 2:
            self.refresh_printers()
        elif index == 3:
            self.refresh_jobs()
        elif index == 5:
            self.refresh_sharing()

    def _run(self, function: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self.statusBar().showMessage("Processando...")
        worker = Worker(function)
        worker.signals.success.connect(callback)
        worker.signals.success.connect(lambda _: self.statusBar().showMessage("Concluído", 3000))
        worker.signals.error.connect(self._error)
        self.pool.start(worker)

    def _error(self, message: str) -> None:
        self.statusBar().showMessage("Falha", 5000)
        QMessageBox.critical(self, "Não foi possível concluir", message)

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[Any, ...]]) -> None:
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))

    def search_from_home(self) -> None:
        self.find_host.setText(self.home_host.text().strip())
        self.sidebar.setCurrentRow(1)
        self.search_host()

    def search_host(self) -> None:
        host = self.find_host.text().strip()
        if not host:
            QMessageBox.information(self, "Informe o endereço", "Digite um IP ou nome de computador.")
            return
        self.find_status.setText("Procurando impressoras e compartilhamentos...")
        self.results.setRowCount(0)
        self._run(lambda: HostPrinterLocator().locate(host), self._show_located)

    def _show_located(self, items: list[LocatedPrinter]) -> None:
        self.located = items
        self._fill(
            self.results,
            [
                (
                    item.name,
                    f"{item.host} ({item.address})",
                    f"{item.connection} — {item.protocol}",
                    "Recomendado" if item.recommended else "Alternativa",
                )
                for item in items
            ],
        )
        if items:
            recommended = next((item for item in items if item.recommended), items[0])
            self.find_status.setText(
                f"Encontradas {len(items)} opção(ões). Recomendação: {recommended.protocol}. {recommended.explanation}"
            )
            self.results.selectRow(0)
        else:
            self.find_status.setText(
                "Nenhuma impressora foi encontrada. Verifique se o endereço está correto, se o equipamento está ligado e se o firewall permite acesso."
            )

    def install_selected(self) -> None:
        row = self.results.currentRow()
        if row < 0 or row >= len(self.located):
            QMessageBox.information(self, "Selecione uma impressora", "Escolha um resultado antes de instalar.")
            return
        item = self.located[row]
        base = item.name if item.protocol == "SMB" else item.host
        queue = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-") or "Impressora-Rede"
        self._run(
            lambda: self.cups.add_printer(queue, item.uri, "everywhere"),
            lambda _: self._installed(queue, item),
        )

    def _installed(self, queue: str, item: LocatedPrinter) -> None:
        QMessageBox.information(
            self,
            "Impressora instalada",
            f"Fila: {queue}\nConexão: {item.protocol}\nEndereço: {item.uri}",
        )
        self.refresh_printers()
        self.sidebar.setCurrentRow(2)

    def refresh_printers(self) -> None:
        self._run(self.cups.list_printers, self._show_printers)

    def _show_printers(self, items: list[Any]) -> None:
        self._fill(
            self.printers,
            [(i.name, i.state, "Sim" if i.enabled else "Não", "Sim" if i.accepting else "Não", i.device_uri or "") for i in items],
        )

    def refresh_jobs(self) -> None:
        self._run(self.jobs_service.list_jobs, lambda items: self._fill(self.jobs, [(i.job_id, i.owner, i.size, i.submitted) for i in items]))

    def open_wizard(self) -> None:
        wizard = PrinterWizard(self.cups, self)
        if wizard.exec():
            self.refresh_printers()

    def _selected_printer(self) -> str | None:
        row = self.printers.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecione uma impressora", "Escolha uma impressora na lista.")
            return None
        return self.printers.item(row, 0).text()

    def test_page(self) -> None:
        name = self._selected_printer()
        if name:
            self._run(lambda: self.cups.print_test_page(name), lambda _: QMessageBox.information(self, "Página enviada", "A página de teste foi enviada para a fila."))

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
        if name and QMessageBox.question(self, "Remover impressora", f"Deseja remover a fila {name}?") == QMessageBox.StandardButton.Yes:
            self._run(lambda: self.cups.remove_printer(name), lambda _: self.refresh_printers())

    def cancel_job(self) -> None:
        row = self.jobs.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecione um trabalho", "Escolha um item da fila.")
            return
        job_id = self.jobs.item(row, 0).text()
        self._run(lambda: self.jobs_service.cancel(job_id), lambda _: self.refresh_jobs())

    def run_diagnostics(self) -> None:
        self._run(DiagnosticService().run_all, self._show_diagnostics)

    def _show_diagnostics(self, items: list[Any]) -> None:
        self._fill(self.diagnostics, [(i.title, i.severity.value, i.message, i.remediation or "") for i in items])
        errors = sum(1 for item in items if item.severity.value == "error")
        self.repair_summary.setText("Nenhum problema crítico encontrado." if errors == 0 else f"Foram encontrados {errors} problema(s) que precisam de atenção.")

    def run_quick_repair(self) -> None:
        self.sidebar.setCurrentRow(4)
        self.run_diagnostics()

    def repair_dependencies(self) -> None:
        self._run(
            RepairService().install_missing_dependencies,
            lambda result: QMessageBox.information(self, "Dependências", result.message),
        )

    def refresh_filters(self) -> None:
        self._run(CupsFilterService().diagnose, self._show_filters)

    def _show_filters(self, items: list[Any]) -> None:
        self.filter_findings = items
        if not items:
            QMessageBox.information(self, "Filtros CUPS", "Nenhuma falha conhecida foi encontrada nos filtros.")
            return
        text = "\n\n".join(f"• {item.title}\n  {item.evidence}" for item in items[:8])
        QMessageBox.warning(self, "Problemas de filtros encontrados", text)

    def refresh_sharing(self) -> None:
        self._run(
            SharingService().audit,
            lambda items: self._fill(self.sharing, [(i.component, i.state.value, i.message, i.remediation or "") for i in items]),
        )

    def create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta para backup")
        if folder:
            self._run(
                lambda: BackupService().create(Path(folder)),
                lambda info: QMessageBox.information(self, "Backup concluído", f"{info.archive}\nSHA-256: {info.sha256}"),
            )

    def discover_devices(self) -> None:
        self._run(DiscoveryService().discover, self._show_devices)

    def _show_devices(self, items: list[Any]) -> None:
        if not items:
            QMessageBox.information(self, "Descoberta", "Nenhum dispositivo foi localizado pelo CUPS.")
            return
        QMessageBox.information(self, "Dispositivos encontrados", "\n".join(f"{i.protocol}: {i.uri}" for i in items[:20]))

    def export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", "relatorio-neri.html", "HTML (*.html)")
        if path:
            self._run(lambda: ReportService().write_html(Path(path)), lambda result: QMessageBox.information(self, "Relatório criado", str(result)))

    def export_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta")
        if folder:
            self._run(lambda: ReportService().create_support_bundle(Path(folder)), lambda result: QMessageBox.information(self, "Pacote criado", str(result)))


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("Neri Printer Manager")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
