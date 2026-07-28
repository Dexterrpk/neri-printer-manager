"""Interface principal, guiada e segura do Neri Printer Manager."""

from __future__ import annotations

import getpass
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .backup import BackupService
from .core import CupsService, JobService, Printer, PrintJob
from .device_discovery import DiscoveredPrinter, RichDiscoveryService
from .health import HealthAction, HealthCheck, PrinterHealthService
from .host_display import HostDisplayResolver
from .host_locator import HostPrinterLocator, LocatedPrinter
from .logging_config import configure_logging
from .repair import RepairResult, RepairService, RepairStatus
from .reports import ReportService
from .security import redact_text
from .sharing import SharingCheck, SharingService
from .smart_install import InstallOutcome, SmartPrinterInstaller
from .usb import UsbPrinter, UsbPrinterService

APP_STYLE = """
QMainWindow, QWidget {
    background: #f4f7fb;
    color: #172033;
    font-size: 14px;
}
QLabel { background: transparent; }
QListWidget#sidebar {
    background: #11213d;
    color: #eef4ff;
    border: 0;
    outline: 0;
    padding: 14px 10px;
}
QListWidget#sidebar::item {
    padding: 14px 12px;
    margin: 3px 0;
    border-radius: 9px;
}
QListWidget#sidebar::item:selected {
    background: #2376e5;
    color: white;
}
QFrame#card {
    background: white;
    border: 1px solid #dce5ef;
    border-radius: 14px;
}
QLabel#title {
    color: #12213d;
    font-size: 27px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #12213d;
    font-size: 18px;
    font-weight: 700;
}
QLabel#muted { color: #5f7085; }
QLabel#success { color: #147a4b; font-weight: 700; }
QLineEdit, QComboBox {
    background: white;
    border: 1px solid #bdcad8;
    border-radius: 9px;
    min-height: 24px;
    padding: 9px 11px;
}
QLineEdit:focus, QComboBox:focus { border: 2px solid #2376e5; }
QPushButton {
    background: #e7edf4;
    border: 0;
    border-radius: 9px;
    min-height: 24px;
    padding: 9px 15px;
    font-weight: 600;
}
QPushButton:hover { background: #d8e3ef; }
QPushButton#primary { background: #2376e5; color: white; }
QPushButton#primary:hover { background: #145fc2; }
QPushButton#danger { background: #ffe5e5; color: #9b2222; }
QTableWidget {
    background: white;
    border: 1px solid #dce5ef;
    border-radius: 10px;
    alternate-background-color: #f8fafc;
    gridline-color: #edf2f7;
}
QHeaderView::section {
    background: #eaf0f6;
    border: 0;
    padding: 9px;
    font-weight: 700;
}
QTabWidget::pane {
    background: white;
    border: 1px solid #dce5ef;
    border-radius: 10px;
    padding: 8px;
}
QTabBar::tab { padding: 9px 16px; margin: 2px; }
QTabBar::tab:selected { color: #145fc2; font-weight: 700; }
"""


class WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    """Executa operações de rede/sistema sem travar a interface."""

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.success.emit(self.function())
        except Exception as exc:  # noqa: BLE001 - worker boundary reports every task failure
            self.signals.error.emit(redact_text(exc))
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    """Janela única com instalação automática, gestão, reparo e suporte."""

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
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)
        self.setStyleSheet(APP_STYLE)

        self.pool = QThreadPool.globalInstance()
        self.cups = CupsService()
        self.jobs_service = JobService()
        self.sharing_service = SharingService()
        self.located: list[LocatedPrinter] = []
        self.printer_items: list[Printer] = []
        self.health_checks: list[HealthCheck] = []
        self.usb_items: list[UsbPrinter] = []
        self._tasks: set[Worker] = set()

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(245)
        for label in self.NAVIGATION:
            self.sidebar.addItem(QListWidgetItem(label))

        self.pages = QStackedWidget()
        for page in (
            self._home_page(),
            self._finder_page(),
            self._printers_page(),
            self._jobs_page(),
            self._health_page(),
            self._sharing_page(),
            self._tools_page(),
        ):
            self.pages.addWidget(page)

        self.sidebar.currentRowChanged.connect(self._navigate)
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
        layout.setSpacing(13)
        heading = QLabel(title)
        heading.setObjectName("title")
        description = QLabel(subtitle)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(description)
        return page, layout

    @staticmethod
    def _card(
        title: str | None = None, description: str | None = None
    ) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        if title:
            heading = QLabel(title)
            heading.setObjectName("sectionTitle")
            layout.addWidget(heading)
        if description:
            text = QLabel(description)
            text.setObjectName("muted")
            text.setWordWrap(True)
            layout.addWidget(text)
        return frame, layout

    @staticmethod
    def _button(
        text: str,
        callback: Callable[[], None],
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        elif danger:
            button.setObjectName("danger")
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        return table

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[object, ...]]) -> None:
        table.clearContents()
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                safe_value = redact_text(value)
                cell = QTableWidgetItem(safe_value)
                cell.setToolTip(safe_value)
                table.setItem(row_index, column_index, cell)

    def _home_page(self) -> QWidget:
        page, layout = self._page(
            "Impressoras funcionando, sem adivinhar configurações",
            "Informe um IP ou nome de computador. O programa identifica a origem, "
            "escolhe o protocolo e tenta o driver mais compatível.",
        )
        card, card_layout = self._card(
            "Localizar e instalar",
            "Funciona com impressora de rede/RJ45, outro Linux Mint e compartilhamento Windows.",
        )
        self.home_host = QLineEdit()
        self.home_host.setPlaceholderText("Ex.: 192.168.1.50, impressora.local ou PC-RECEPCAO")
        self.home_host.returnPressed.connect(self.search_from_home)
        search_row = QHBoxLayout()
        search_row.addWidget(self.home_host, 1)
        search_row.addWidget(
            self._button("Localizar automaticamente", self.search_from_home, primary=True)
        )
        card_layout.addLayout(search_row)
        layout.addWidget(card)

        shortcuts = QGridLayout()
        shortcuts.addWidget(
            self._button("Impressora USB", self.open_usb_tools, primary=True),
            0,
            0,
        )
        shortcuts.addWidget(
            self._button("Minhas impressoras", lambda: self.sidebar.setCurrentRow(2)),
            0,
            1,
        )
        shortcuts.addWidget(
            self._button("Diagnóstico automático", self.open_health_center),
            1,
            0,
        )
        shortcuts.addWidget(
            self._button("Compartilhar com Windows", self.open_sharing),
            1,
            1,
        )
        layout.addLayout(shortcuts)

        guide, guide_layout = self._card("Como o modo automático trabalha")
        steps = QLabel(
            "1. Localiza o equipamento por DNS, mDNS, NetBIOS ou IP.\n"
            "2. Prioriza IPP; se necessário, tenta JetDirect, LPD ou SMB.\n"
            "3. Confere o driver, cria a fila, ativa e envia uma página de teste."
        )
        steps.setWordWrap(True)
        guide_layout.addWidget(steps)
        layout.addWidget(guide)
        layout.addStretch()
        return page

    def _finder_page(self) -> QWidget:
        page, layout = self._page(
            "Encontrar impressora na rede",
            "Use IP, hostname, nome NetBIOS ou o computador que compartilha a fila.",
        )
        row = QHBoxLayout()
        self.find_host = QLineEdit()
        self.find_host.setPlaceholderText("Ex.: 10.3.45.22, MAQ211, \\SERVIDOR ou smb://SERVIDOR")
        self.find_host.returnPressed.connect(self.search)
        row.addWidget(self.find_host, 1)
        row.addWidget(self._button("Buscar", self.search, primary=True))
        layout.addLayout(row)

        auth_card, auth_layout = self._card(
            "Acesso Windows/SMB (opcional)",
            "Só preencha quando o computador remoto pedir autenticação. A senha "
            "é usada durante a busca/instalação e não é gravada.",
        )
        auth_row = QHBoxLayout()
        self.smb_user = QLineEdit()
        self.smb_user.setPlaceholderText("Usuário, DOMINIO\\usuario ou PC\\usuario")
        self.smb_password = QLineEdit()
        self.smb_password.setPlaceholderText("Senha")
        self.smb_password.setEchoMode(QLineEdit.EchoMode.Password)
        auth_row.addWidget(self.smb_user)
        auth_row.addWidget(self.smb_password)
        auth_layout.addLayout(auth_row)
        layout.addWidget(auth_card)

        self.find_status = QLabel("Aguardando pesquisa.")
        self.find_status.setObjectName("muted")
        self.find_status.setWordWrap(True)
        layout.addWidget(self.find_status)
        self.results = self._table(["Impressora/Fila", "Computador e IP", "Conexão", "Escolha"])
        layout.addWidget(self.results, 1)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Instalar selecionada", self.install_selected, primary=True))
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _printers_page(self) -> QWidget:
        page, layout = self._page(
            "Minhas impressoras",
            "Mostra somente filas configuradas neste computador. Filas publicadas "
            "automaticamente por outros Mints ficam na descoberta de rede.",
        )
        self.printer_status = QLabel("Carregando impressoras...")
        self.printer_status.setObjectName("muted")
        self.printer_status.setWordWrap(True)
        layout.addWidget(self.printer_status)
        self.printer_table = self._table(
            ["Nome", "Estado", "Ativa", "Aceitando", "Conexão", "Padrão"]
        )
        layout.addWidget(self.printer_table, 1)
        primary_actions = QHBoxLayout()
        primary_actions.addWidget(self._button("Atualizar", self.refresh_printers, primary=True))
        primary_actions.addWidget(self._button("Definir padrão", self.set_default_printer))
        primary_actions.addWidget(self._button("Página de teste", self.test_page))
        primary_actions.addStretch()
        layout.addLayout(primary_actions)
        queue_actions = QHBoxLayout()
        queue_actions.addWidget(self._button("Pausar", self.pause_printer))
        queue_actions.addWidget(self._button("Retomar", self.resume_printer))
        queue_actions.addWidget(self._button("Compartilhar", self.share_selected_printer))
        queue_actions.addWidget(self._button("Remover", self.remove_printer, danger=True))
        queue_actions.addStretch()
        layout.addLayout(queue_actions)
        return page

    def _jobs_page(self) -> QWidget:
        page, layout = self._page(
            "Fila de impressão",
            "Acompanhe os trabalhos pendentes e cancele somente o item selecionado.",
        )
        self.job_status = QLabel("Aguardando consulta.")
        self.job_status.setObjectName("muted")
        layout.addWidget(self.job_status)
        self.job_table = self._table(["Trabalho", "Usuário", "Tamanho", "Enviado em"])
        layout.addWidget(self.job_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Atualizar", self.refresh_jobs, primary=True))
        row.addWidget(self._button("Cancelar selecionado", self.cancel_job, danger=True))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _health_page(self) -> QWidget:
        page, layout = self._page(
            "Central de saúde e correção",
            "Verifica componentes, CUPS, filas, trabalhos, PolicyKit, Samba, filtros e "
            "drivers. Cada correção é confirmada e verificada.",
        )
        self.health_summary = QLabel("Clique em Fazer diagnóstico completo.")
        self.health_summary.setObjectName("muted")
        self.health_summary.setWordWrap(True)
        layout.addWidget(self.health_summary)
        self.health_table = self._table(
            ["Área", "Situação", "O que foi encontrado", "Solução recomendada"]
        )
        layout.addWidget(self.health_table, 1)
        diagnostic_actions = QHBoxLayout()
        diagnostic_actions.addWidget(
            self._button(
                "Fazer diagnóstico completo",
                self.refresh_health,
                primary=True,
            )
        )
        diagnostic_actions.addWidget(self._button("Ver detalhes", self.show_health_details))
        diagnostic_actions.addStretch()
        layout.addLayout(diagnostic_actions)
        repair_actions = QHBoxLayout()
        repair_actions.addWidget(self._button("Corrigir selecionado", self.repair_selected_health))
        repair_actions.addWidget(self._button("Corrigir automaticamente", self.repair_all_safe))
        repair_actions.addStretch()
        layout.addLayout(repair_actions)
        note = QLabel(
            "O modo automático não troca endereço, credencial ou driver específico. "
            "Essas decisões continuam sob seu controle."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        page.setMinimumHeight(720)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _sharing_page(self) -> QWidget:
        page, layout = self._page(
            "Compartilhamento Mint e Windows",
            "Compartilhe uma fila local pelo CUPS/Samba e prepare sua conta para "
            "autenticação a partir do Windows.",
        )
        self.sharing_status = QLabel("Clique em Verificar ambiente.")
        self.sharing_status.setObjectName("muted")
        layout.addWidget(self.sharing_status)
        self.sharing_table = self._table(["Componente", "Estado", "Resultado", "Orientação"])
        layout.addWidget(self.sharing_table, 1)

        queue_card, queue_layout = self._card(
            "Fila que será compartilhada",
            "O acesso remoto continua autenticado. Revise também o firewall da rede.",
        )
        queue_row = QHBoxLayout()
        self.sharing_queue = QComboBox()
        self.sharing_queue.setMinimumWidth(280)
        queue_row.addWidget(self.sharing_queue, 1)
        queue_row.addWidget(
            self._button("Compartilhar fila", self.share_queue_from_page, primary=True)
        )
        queue_row.addWidget(self._button("Parar compartilhamento", self.unshare_queue_from_page))
        queue_layout.addLayout(queue_row)
        layout.addWidget(queue_card)

        account_card, account_layout = self._card(
            "Senha de acesso pelo Windows",
            "Cria/atualiza a senha Samba da sua conta local. Ela pode ser diferente da "
            "senha do Linux e não fica armazenada no aplicativo.",
        )
        form = QFormLayout()
        self.samba_local_user = QLineEdit(getpass.getuser())
        self.samba_local_password = QLineEdit()
        self.samba_local_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.samba_local_password.setPlaceholderText("Mínimo de 8 caracteres")
        self.samba_local_confirmation = QLineEdit()
        self.samba_local_confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        self.samba_local_confirmation.setPlaceholderText("Repita a senha")
        form.addRow("Usuário local", self.samba_local_user)
        form.addRow("Nova senha Samba", self.samba_local_password)
        form.addRow("Confirmar senha", self.samba_local_confirmation)
        account_layout.addLayout(form)
        account_layout.addWidget(
            self._button(
                "Configurar acesso Windows",
                self.configure_samba_password,
                primary=True,
            )
        )
        layout.addWidget(account_card)

        row = QHBoxLayout()
        row.addWidget(self._button("Verificar ambiente", self.refresh_sharing, primary=True))
        row.addStretch()
        layout.addLayout(row)
        page.setMinimumHeight(720)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _tools_page(self) -> QWidget:
        page, layout = self._page(
            "Ferramentas técnicas",
            "Descoberta detalhada, USB, relatórios sem credenciais e backup completo.",
        )
        self.tools_tabs = QTabWidget()
        self.tools_tabs.addTab(self._network_tools_tab(), "Rede e dispositivos")
        self.tools_tabs.addTab(self._usb_tools_tab(), "USB")
        self.tools_tabs.addTab(self._reports_tools_tab(), "Relatórios e backup")
        layout.addWidget(self.tools_tabs, 1)
        return page

    def _network_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.discovery_status = QLabel("Clique em Descobrir impressoras.")
        self.discovery_status.setObjectName("muted")
        self.discovery_status.setWordWrap(True)
        layout.addWidget(self.discovery_status)
        self.discovery_table = self._table(
            ["Impressora", "Modelo", "Computador/Host", "IP", "Protocolo", "Fila local"]
        )
        layout.addWidget(self.discovery_table, 1)
        row = QHBoxLayout()
        row.addWidget(
            self._button(
                "Descobrir impressoras",
                self.discover_devices,
                primary=True,
            )
        )
        row.addStretch()
        layout.addLayout(row)
        return tab

    def _usb_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.usb_status = QLabel("Conecte e ligue a impressora; depois clique em Procurar USB.")
        self.usb_status.setObjectName("muted")
        layout.addWidget(self.usb_status)
        self.usb_table = self._table(
            ["Impressora USB", "Fabricante", "Modelo", "Driver recomendado"]
        )
        layout.addWidget(self.usb_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Procurar USB", self.discover_usb, primary=True))
        row.addWidget(self._button("Instalar USB selecionada", self.install_usb))
        row.addStretch()
        layout.addLayout(row)
        return tab

    def _reports_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        report_card, report_layout = self._card(
            "Relatório e pacote de suporte",
            "As URIs autenticadas e senhas são removidas antes da gravação.",
        )
        report_row = QHBoxLayout()
        report_row.addWidget(self._button("Exportar relatório HTML", self.export_html))
        report_row.addWidget(self._button("Criar pacote de suporte ZIP", self.export_bundle))
        report_layout.addLayout(report_row)
        layout.addWidget(report_card)

        backup_card, backup_layout = self._card(
            "Backup de configuração",
            "Inclui CUPS, PPDs e Samba quando presentes. O arquivo recebe SHA-256 e "
            "manifesto para conferência.",
        )
        backup_layout.addWidget(
            self._button("Criar backup completo", self.create_backup, primary=True)
        )
        layout.addWidget(backup_card)
        layout.addStretch()
        return tab

    def _navigate(self, index: int) -> None:
        if index < 0:
            return
        self.pages.setCurrentIndex(index)
        if index == 2:
            self.refresh_printers()
        elif index == 3:
            self.refresh_jobs()
        elif index == 4:
            self.refresh_health()
        elif index == 5:
            self.refresh_sharing()

    def _run(
        self,
        function: Callable[[], Any],
        callback: Callable[[Any], None],
        *,
        message: str = "Processando...",
    ) -> None:
        self.statusBar().showMessage(message)
        worker = Worker(function)
        self._tasks.add(worker)
        worker.signals.success.connect(callback)
        worker.signals.success.connect(self._operation_finished)
        worker.signals.error.connect(self._error)
        worker.signals.finished.connect(lambda worker=worker: self._tasks.discard(worker))
        self.pool.start(worker)

    def _operation_finished(self, _result: object) -> None:
        self.statusBar().showMessage("Concluído", 3000)

    def _error(self, message: str) -> None:
        safe_message = redact_text(message)
        self.statusBar().showMessage("Falha", 5000)
        if hasattr(self, "find_status"):
            self.find_status.setText(safe_message)
        QMessageBox.warning(self, "Não foi possível concluir", safe_message)

    def search_from_home(self) -> None:
        self.find_host.setText(self.home_host.text().strip())
        self.sidebar.setCurrentRow(1)
        self.search()

    def search(self) -> None:
        host = self.find_host.text().strip()
        username = self.smb_user.text().strip()
        password = self.smb_password.text()
        if not host:
            QMessageBox.information(
                self,
                "Informe o endereço",
                "Digite um IP ou nome de computador.",
            )
            return
        self.smb_password.clear()
        self.find_status.setText(
            "Resolvendo o nome e verificando IPP, JetDirect, LPD, CUPS e SMB..."
        )
        self.located.clear()
        self.results.setRowCount(0)
        self._run(
            lambda: HostPrinterLocator().locate(
                host,
                username=username,
                password=password,
            ),
            self._show_located,
            message="Procurando impressoras...",
        )

    def _show_located(self, items: list[LocatedPrinter]) -> None:
        self.located = items
        self._fill(
            self.results,
            [
                (
                    item.name,
                    f"{item.host} ({item.address})",
                    f"{item.protocol} — {item.connection}",
                    "Recomendado" if item.recommended else "Alternativa",
                )
                for item in items
            ],
        )
        if not items:
            self.find_status.setText("Nenhuma opção acessível foi encontrada.")
            return
        selected_index = next(
            (index for index, item in enumerate(items) if item.recommended),
            0,
        )
        self.results.selectRow(selected_index)
        selected = items[selected_index]
        self.find_status.setText(
            f"{len(items)} opção(ões) encontrada(s). Recomendação: "
            f"{selected.protocol}. {selected.explanation}"
        )

    @staticmethod
    def _suggest_queue_name(base: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-_.")[:80] or "Impressora-Rede"

    def install_selected(self) -> None:
        row = self.results.currentRow()
        if row < 0 or row >= len(self.located):
            QMessageBox.information(
                self,
                "Selecione",
                "Escolha uma impressora encontrada.",
            )
            return
        item = self.located[row]
        base = item.name if item.protocol == "SMB" else item.host
        suggested = self._suggest_queue_name(base)
        queue, accepted = QInputDialog.getText(
            self,
            "Nome da impressora",
            "Nome que aparecerá neste computador:",
            text=suggested,
        )
        if not accepted:
            return
        self.find_status.setText("Instalando, validando a fila e enviando uma página de teste...")
        self._run(
            lambda: SmartPrinterInstaller(self.cups).install(queue.strip(), item),
            self._installed,
            message="Instalando impressora...",
        )

    def _installed(self, outcome: InstallOutcome) -> None:
        self.smb_password.clear()
        self.located.clear()
        self.results.setRowCount(0)
        QMessageBox.information(
            self,
            "Impressora instalada",
            f"Fila: {outcome.queue}\n"
            f"Conexão: {outcome.uri}\n"
            f"Driver: {outcome.description}\n"
            f"Tentativas: {outcome.attempts}\n"
            f"Página de teste: {'enviada' if outcome.test_page_submitted else 'não enviada'}",
        )
        self.sidebar.setCurrentRow(2)
        self.refresh_printers()

    def refresh_printers(self) -> None:
        self.printer_status.setText("Consultando o CUPS...")

        def load() -> tuple[list[Printer], str | None]:
            return (
                self.cups.list_printers(include_automatic=True),
                self.cups.default_printer(),
            )

        self._run(load, self._show_printers, message="Atualizando impressoras...")

    def _show_printers(self, payload: tuple[list[Printer], str | None]) -> None:
        printers, default = payload
        self.printer_items = [printer for printer in printers if not printer.automatic]
        automatic_count = sum(printer.automatic for printer in printers)
        self._fill(
            self.printer_table,
            [
                (
                    item.name,
                    item.state,
                    "Sim" if item.enabled else "Não",
                    "Sim" if item.accepting else "Não",
                    item.device_uri or "",
                    "Sim" if item.name == default else "",
                )
                for item in self.printer_items
            ],
        )
        if self.printer_items:
            status = f"{len(self.printer_items)} fila(s) configurada(s) neste computador."
        else:
            status = "Nenhuma impressora configurada localmente."
        if automatic_count:
            status += (
                f" {automatic_count} fila(s) publicada(s) automaticamente foram "
                "mantidas apenas na descoberta de rede."
            )
        self.printer_status.setText(status)
        self._refresh_sharing_queue_combo()

    def _selected_printer(self) -> Printer | None:
        row = self.printer_table.currentRow()
        if row < 0 or row >= len(self.printer_items):
            QMessageBox.information(
                self,
                "Selecione uma impressora",
                "Escolha uma fila na lista.",
            )
            return None
        return self.printer_items[row]

    def set_default_printer(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        self._run(
            lambda: self.cups.set_default(printer.name),
            lambda _result: self.refresh_printers(),
            message="Definindo impressora padrão...",
        )

    def test_page(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        self._run(
            lambda: self.cups.print_test_page(printer.name),
            self._test_page_sent,
            message="Enviando página de teste...",
        )

    def _test_page_sent(self, _result: object) -> None:
        QMessageBox.information(
            self,
            "Página de teste",
            "O documento foi enviado para a fila. Confira a impressão física.",
        )

    def pause_printer(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        self._run(
            lambda: self.cups.pause(printer.name),
            lambda _result: self.refresh_printers(),
        )

    def resume_printer(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        self._run(
            lambda: self.cups.resume(printer.name),
            lambda _result: self.refresh_printers(),
        )

    def remove_printer(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        answer = QMessageBox.question(
            self,
            "Remover impressora",
            f"Remover somente a fila local '{printer.name}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: self.cups.remove_printer(printer.name),
            lambda _result: self.refresh_printers(),
            message="Removendo fila...",
        )

    def share_selected_printer(self) -> None:
        printer = self._selected_printer()
        if printer is None:
            return
        self.sidebar.setCurrentRow(5)
        index = self.sharing_queue.findText(printer.name)
        if index >= 0:
            self.sharing_queue.setCurrentIndex(index)

    def refresh_jobs(self) -> None:
        self.job_status.setText("Consultando trabalhos...")
        self._run(self.jobs_service.list_jobs, self._show_jobs)

    def _show_jobs(self, items: list[PrintJob]) -> None:
        self._fill(
            self.job_table,
            [(item.job_id, item.owner, item.size, item.submitted) for item in items],
        )
        self.job_status.setText(
            f"{len(items)} trabalho(s) pendente(s)." if items else "Nenhum trabalho pendente."
        )

    def cancel_job(self) -> None:
        row = self.job_table.currentRow()
        item = self.job_table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(
                self,
                "Selecione um trabalho",
                "Escolha um item da fila.",
            )
            return
        job_id = item.text()
        answer = QMessageBox.question(
            self,
            "Cancelar trabalho",
            f"Cancelar o trabalho {job_id}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: self.jobs_service.cancel(job_id),
            lambda _result: self.refresh_jobs(),
        )

    def open_health_center(self) -> None:
        self.sidebar.setCurrentRow(4)

    def refresh_health(self) -> None:
        self.health_summary.setText(
            "Verificando o ambiente completo sem interromper a interface..."
        )
        self.health_table.setRowCount(0)
        self._run(
            PrinterHealthService().run_all,
            self._show_health,
            message="Executando diagnóstico...",
        )

    def _show_health(self, items: list[HealthCheck]) -> None:
        self.health_checks = items
        names = {"ok": "OK", "warning": "ATENÇÃO", "error": "PROBLEMA"}
        self._fill(
            self.health_table,
            [
                (
                    item.category,
                    names.get(item.severity.value, item.severity.value),
                    f"{item.title}: {item.summary}",
                    item.action_label,
                )
                for item in items
            ],
        )
        errors = sum(item.severity.value == "error" for item in items)
        warnings = sum(item.severity.value == "warning" for item in items)
        ok = sum(item.severity.value == "ok" for item in items)
        if not errors and not warnings:
            summary = f"Ambiente saudável: {ok} verificações concluídas."
        else:
            summary = f"Diagnóstico: {ok} OK, {warnings} aviso(s) e {errors} problema(s)."
        self.health_summary.setText(summary)
        first_problem = next(
            (index for index, item in enumerate(items) if item.severity.value != "ok"),
            None,
        )
        if first_problem is not None:
            self.health_table.selectRow(first_problem)

    def _selected_health(self) -> HealthCheck | None:
        row = self.health_table.currentRow()
        if row < 0 or row >= len(self.health_checks):
            QMessageBox.information(
                self,
                "Selecione uma verificação",
                "Escolha uma linha do diagnóstico.",
            )
            return None
        return self.health_checks[row]

    def show_health_details(self) -> None:
        item = self._selected_health()
        if item is None:
            return
        QMessageBox.information(
            self,
            item.title,
            f"Área: {item.category}\n"
            f"Estado: {item.severity.value.upper()}\n\n"
            f"Resumo:\n{item.summary}\n\n"
            f"Detalhes técnicos:\n{item.details}\n\n"
            f"Solução:\n{item.action_label}",
        )

    def repair_selected_health(self) -> None:
        item = self._selected_health()
        if item is None:
            return
        if item.action is HealthAction.NONE:
            QMessageBox.information(
                self,
                "Orientação",
                f"{item.summary}\n\n{item.action_label}",
            )
            return
        answer = QMessageBox.question(
            self,
            "Confirmar correção",
            f"Problema: {item.title}\n\nAção proposta: {item.action_label}\n\nContinuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: RepairService().repair_health_check(item),
            self._show_repair_results,
            message="Aplicando e verificando correção...",
        )

    def repair_all_safe(self) -> None:
        candidates = [
            item
            for item in self.health_checks
            if item.safe_automatic and item.severity.value != "ok"
        ]
        if not candidates:
            QMessageBox.information(
                self,
                "Ambiente",
                "Nenhuma correção automática segura está pendente.",
            )
            return
        labels = "\n".join(f"• {item.title}: {item.action_label}" for item in candidates)
        answer = QMessageBox.question(
            self,
            "Corrigir problemas seguros",
            f"Serão aplicadas estas ações:\n\n{labels}\n\nContinuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: RepairService().repair_safe_checks(candidates),
            self._show_repair_results,
            message="Aplicando correções seguras...",
        )

    def _show_repair_results(self, results: list[RepairResult]) -> None:
        labels = {
            RepairStatus.SUCCESS: "RESOLVIDO",
            RepairStatus.FAILED: "NÃO RESOLVIDO",
            RepairStatus.SKIPPED: "ORIENTAÇÃO",
        }
        message = "\n".join(f"• {labels[result.status]} — {result.message}" for result in results)
        if any(result.status is RepairStatus.FAILED for result in results):
            QMessageBox.warning(self, "Resultado da correção", message)
        else:
            QMessageBox.information(self, "Resultado da correção", message)
        self.refresh_health()

    def open_sharing(self) -> None:
        self.sidebar.setCurrentRow(5)

    def refresh_sharing(self) -> None:
        self.sharing_status.setText("Verificando CUPS, Samba, conta e firewall...")
        self._run(
            self.sharing_service.audit,
            self._show_sharing,
            message="Verificando compartilhamento...",
        )
        if not self.printer_items:
            self.refresh_printers()

    def _show_sharing(self, items: list[SharingCheck]) -> None:
        labels = {
            "enabled": "OK",
            "disabled": "DESATIVADO",
            "misconfigured": "PROBLEMA",
            "unknown": "VERIFICAR",
        }
        self._fill(
            self.sharing_table,
            [
                (
                    item.component,
                    labels.get(item.state.value, item.state.value),
                    item.message,
                    item.remediation or "",
                )
                for item in items
            ],
        )
        self.sharing_status.setText(
            "Verificação concluída. Selecione uma fila abaixo para compartilhar."
        )

    def _refresh_sharing_queue_combo(self) -> None:
        selected = self.sharing_queue.currentText()
        self.sharing_queue.clear()
        self.sharing_queue.addItems([item.name for item in self.printer_items])
        index = self.sharing_queue.findText(selected)
        if index >= 0:
            self.sharing_queue.setCurrentIndex(index)

    def _sharing_queue_name(self) -> str | None:
        queue = self.sharing_queue.currentText().strip()
        if not queue:
            QMessageBox.information(
                self,
                "Nenhuma fila",
                "Instale ou selecione uma impressora local primeiro.",
            )
            return None
        return queue

    def share_queue_from_page(self) -> None:
        queue = self._sharing_queue_name()
        if queue is None:
            return
        answer = QMessageBox.question(
            self,
            "Compartilhar impressora",
            f"Compartilhar '{queue}' pelo CUPS e Samba?\n\n"
            "O acesso Samba continuará exigindo usuário e senha.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: self.sharing_service.enable_queue(queue),
            self._sharing_changed,
            message="Preparando compartilhamento...",
        )

    def unshare_queue_from_page(self) -> None:
        queue = self._sharing_queue_name()
        if queue is None:
            return
        answer = QMessageBox.question(
            self,
            "Parar compartilhamento",
            f"Desativar o compartilhamento da fila '{queue}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            lambda: self.sharing_service.disable_queue(queue),
            self._sharing_changed,
            message="Desativando compartilhamento...",
        )

    def _sharing_changed(self, message: str) -> None:
        QMessageBox.information(self, "Compartilhamento", message)
        self.refresh_sharing()

    def configure_samba_password(self) -> None:
        username = self.samba_local_user.text().strip()
        password = self.samba_local_password.text()
        confirmation = self.samba_local_confirmation.text()
        if password != confirmation:
            QMessageBox.information(
                self,
                "Senhas diferentes",
                "Digite a mesma senha nos dois campos.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Configurar acesso Windows",
            f"Criar ou atualizar a senha Samba da conta '{username}'?\n\n"
            "A senha será enviada somente ao helper local e não será armazenada.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.samba_local_password.clear()
        self.samba_local_confirmation.clear()
        self._run(
            lambda: self.sharing_service.configure_samba_password(
                username,
                password,
            ),
            self._samba_password_configured,
            message="Configurando conta Samba...",
        )

    def _samba_password_configured(self, message: str) -> None:
        QMessageBox.information(self, "Acesso Windows", message)
        self.refresh_sharing()

    def open_usb_tools(self) -> None:
        self.sidebar.setCurrentRow(6)
        self.tools_tabs.setCurrentIndex(1)
        self.discover_usb()

    @staticmethod
    def _discover_with_names() -> list[tuple[DiscoveredPrinter, str]]:
        items = RichDiscoveryService().discover()
        resolver = HostDisplayResolver()
        names = resolver.resolve_many((item.host, item.address) for item in items)
        return list(zip(items, names, strict=True))

    def discover_devices(self) -> None:
        self.discovery_status.setText(
            "Consultando filas locais, CUPS, IPP, Avahi e a rede local..."
        )
        self.discovery_table.setRowCount(0)
        self._run(
            self._discover_with_names,
            self._show_discovered,
            message="Descobrindo impressoras...",
        )

    def _show_discovered(self, resolved: list[tuple[DiscoveredPrinter, str]]) -> None:
        self._fill(
            self.discovery_table,
            [
                (
                    item.name or "Impressora sem nome",
                    item.model or "Modelo não informado",
                    display_host or "Não identificado",
                    item.address or "Não informado",
                    item.protocol or "Desconhecido",
                    item.installed_queue or "Não instalada",
                )
                for item, display_host in resolved
            ],
        )
        installed = sum(bool(item.installed_queue) for item, _name in resolved)
        remote = len(resolved) - installed
        self.discovery_status.setText(
            f"{len(resolved)} impressora(s): {installed} instalada(s) localmente e "
            f"{remote} disponível(is) na rede."
            if resolved
            else "Nenhuma impressora foi identificada."
        )

    def discover_usb(self) -> None:
        self.usb_status.setText("Procurando dispositivos USB e comparando os drivers instalados...")
        self.usb_table.setRowCount(0)
        self._run(
            UsbPrinterService().detect,
            self._show_usb,
            message="Procurando USB...",
        )

    def _show_usb(self, items: list[UsbPrinter]) -> None:
        self.usb_items = items
        self._fill(
            self.usb_table,
            [
                (
                    item.name,
                    item.manufacturer or "Não informado",
                    item.model or "Não informado",
                    item.driver_description,
                )
                for item in items
            ],
        )
        self.usb_status.setText(
            f"{len(items)} impressora(s) USB encontrada(s)."
            if items
            else "Nenhuma impressora USB foi detectada pelo CUPS."
        )
        if items:
            self.usb_table.selectRow(0)

    def install_usb(self) -> None:
        row = self.usb_table.currentRow()
        if row < 0 or row >= len(self.usb_items):
            QMessageBox.information(
                self,
                "Selecione",
                "Escolha uma impressora USB.",
            )
            return
        item = self.usb_items[row]
        suggested = self._suggest_queue_name(item.name or "Impressora-USB")
        queue, accepted = QInputDialog.getText(
            self,
            "Nome da impressora USB",
            "Nome que aparecerá neste computador:",
            text=suggested,
        )
        if not accepted:
            return
        self._run(
            lambda: UsbPrinterService().install(item, queue.strip()),
            self._usb_installed,
            message="Instalando USB...",
        )

    def _usb_installed(self, message: str) -> None:
        QMessageBox.information(self, "USB instalada", message)
        self.sidebar.setCurrentRow(2)
        self.refresh_printers()

    def export_html(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Salvar relatório",
            "relatorio-neri.html",
            "HTML (*.html)",
        )
        if not path:
            return
        self._run(
            lambda: ReportService().write_html(Path(path)),
            self._report_created,
            message="Gerando relatório...",
        )

    def _report_created(self, path: Path) -> None:
        QMessageBox.information(self, "Relatório criado", str(path))

    def export_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Pasta do pacote de suporte",
        )
        if not folder:
            return
        self._run(
            lambda: ReportService().create_support_bundle(Path(folder)),
            self._bundle_created,
            message="Criando pacote de suporte...",
        )

    def _bundle_created(self, path: Path) -> None:
        QMessageBox.information(self, "Pacote de suporte criado", str(path))

    def create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta do backup")
        if not folder:
            return
        self._run(
            lambda: BackupService().create(Path(folder)),
            self._backup_created,
            message="Criando backup completo...",
        )

    def _backup_created(self, info: object) -> None:
        archive = getattr(info, "archive", "")
        checksum = getattr(info, "sha256", "")
        QMessageBox.information(
            self,
            "Backup criado",
            f"Arquivo: {archive}\nSHA-256: {checksum}",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.smb_password.clear()
        self.samba_local_password.clear()
        self.samba_local_confirmation.clear()
        self.located.clear()
        super().closeEvent(event)


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("Neri Printer Manager")
    application.setOrganizationName("Neri InfoTech")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
