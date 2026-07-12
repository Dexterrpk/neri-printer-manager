"""Assistente amigável e automatizado para instalação de impressoras."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from .core import CupsService, DiscoveryService, validate_device_uri, validate_queue_name
from .protocols import ConnectionType, ProtocolAdvisor, ProtocolRecommendation


class PrinterWizard(QWizard):
    """Fluxo guiado: origem, detecção, recomendação e confirmação."""

    def __init__(self, cups: CupsService, parent=None) -> None:
        super().__init__(parent)
        self.cups = cups
        self.advisor = ProtocolAdvisor()
        self.recommendations: list[ProtocolRecommendation] = []
        self.selected_uri = ""

        self.setWindowTitle("Adicionar impressora")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.resize(760, 560)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.WizardButton.NextButton, "Continuar")
        self.setButtonText(QWizard.WizardButton.BackButton, "Voltar")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Instalar impressora")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cancelar")

        self.addPage(self._connection_page())
        self.addPage(self._details_page())
        self.addPage(self._recommendation_page())
        self.addPage(self._confirmation_page())
        self.currentIdChanged.connect(self._on_page_changed)

    def _connection_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Como a impressora está conectada?")
        page.setSubTitle("Escolha a opção mais parecida com o seu cenário. O programa decide o protocolo depois.")
        layout = QVBoxLayout(page)
        self.connection_group = QButtonGroup(page)
        options = (
            (ConnectionType.USB, "USB ou conectada neste computador", "Para cabo USB ou dispositivo detectado localmente."),
            (ConnectionType.NETWORK, "Impressora com IP ou cabo de rede", "Para impressora ligada ao roteador, switch ou RJ45 direto."),
            (ConnectionType.WINDOWS, "Compartilhada por um computador Windows", "Para filas do tipo \\SERVIDOR\\IMPRESSORA."),
            (ConnectionType.MANUAL, "Configuração avançada", "Para informar uma URI completa manualmente."),
        )
        for index, (value, title, description) in enumerate(options):
            radio = QRadioButton(title)
            radio.setProperty("connection_type", value.value)
            self.connection_group.addButton(radio)
            layout.addWidget(radio)
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setContentsMargins(28, 0, 0, 10)
            layout.addWidget(detail)
            if index == 1:
                radio.setChecked(True)
        layout.addStretch()
        return page

    def _details_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Onde está a impressora?")
        page.setSubTitle("Preencha apenas o necessário. Exemplos aparecem dentro dos campos.")
        form = QFormLayout(page)
        self.host = QLineEdit(); self.host.setPlaceholderText("Ex.: 192.168.1.50 ou impressora.local")
        self.share = QLineEdit(); self.share.setPlaceholderText("Ex.: HP_RECEPCAO")
        self.manual_uri = QLineEdit(); self.manual_uri.setPlaceholderText("Ex.: ipp://192.168.1.50/ipp/print")
        self.detected = QComboBox()
        self.detect_button = QPushButton("Procurar automaticamente")
        self.detect_button.clicked.connect(self._discover)
        detected_row = QHBoxLayout(); detected_row.addWidget(self.detected); detected_row.addWidget(self.detect_button)
        form.addRow("IP, host ou servidor", self.host)
        form.addRow("Nome do compartilhamento", self.share)
        form.addRow("URI manual", self.manual_uri)
        form.addRow("Detectadas", detected_row)
        return page

    def _recommendation_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Melhor forma de conectar")
        page.setSubTitle("A opção mais compatível aparece primeiro. Você pode escolher outra.")
        layout = QVBoxLayout(page)
        self.recommendation_list = QListWidget()
        self.recommendation_list.currentRowChanged.connect(self._recommendation_selected)
        layout.addWidget(self.recommendation_list)
        self.recommendation_help = QLabel()
        self.recommendation_help.setWordWrap(True)
        self.recommendation_help.setMinimumHeight(70)
        layout.addWidget(self.recommendation_help)
        return page

    def _confirmation_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Confirmar instalação")
        page.setSubTitle("Revise os dados. O programa usará impressão sem driver quando possível.")
        form = QFormLayout(page)
        self.queue_name = QLineEdit(); self.queue_name.setPlaceholderText("Ex.: RECEPCAO_HP")
        self.driver = QComboBox()
        self.driver.addItem("Automático / driverless (recomendado)", "everywhere")
        self.driver.addItem("Driver genérico PostScript", "drv:///sample.drv/generic.ppd")
        self.driver.addItem("Driver genérico PCL", "drv:///sample.drv/generpcl.ppd")
        self.summary = QLabel(); self.summary.setWordWrap(True); self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Nome que aparecerá no sistema", self.queue_name)
        form.addRow("Driver", self.driver)
        form.addRow("Resumo", self.summary)
        return page

    def _connection_type(self) -> ConnectionType:
        button = self.connection_group.checkedButton()
        value = button.property("connection_type") if button else ConnectionType.NETWORK.value
        return ConnectionType(value)

    def _discover(self) -> None:
        self.detect_button.setEnabled(False)
        self.detect_button.setText("Procurando...")
        try:
            devices = DiscoveryService().discover()
            self.detected.clear()
            for device in devices:
                self.detected.addItem(f"{device.protocol}: {device.uri}", device.uri)
            if not devices:
                self.detected.addItem("Nenhuma impressora encontrada automaticamente", "")
        except Exception as exc:
            QMessageBox.warning(self, "Descoberta", str(exc))
        finally:
            self.detect_button.setEnabled(True)
            self.detect_button.setText("Procurar automaticamente")

    def _prepare_recommendations(self) -> None:
        connection = self._connection_type()
        detected_uri = self.detected.currentData() if self.detected.count() else ""
        if detected_uri:
            self.recommendations = [
                ProtocolRecommendation("Detectada", detected_uri, "Impressora encontrada automaticamente", "A URI foi fornecida pelo CUPS e tende a ser a opção mais segura.", 110)
            ]
        elif connection is ConnectionType.NETWORK:
            host = self.host.text().strip()
            if not host:
                raise ValueError("Informe o IP ou nome da impressora.")
            self.recommendations = self.advisor.recommend_network(host)
        elif connection is ConnectionType.WINDOWS:
            server, share = self.host.text().strip(), self.share.text().strip()
            if not server or not share:
                raise ValueError("Informe o computador Windows e o nome do compartilhamento.")
            self.recommendations = [self.advisor.windows_share(server, share)]
        elif connection is ConnectionType.MANUAL:
            uri = validate_device_uri(self.manual_uri.text())
            self.recommendations = [ProtocolRecommendation("Manual", uri, "Configuração manual", "A URI será usada exatamente como informada.", 100)]
        else:
            self.recommendations = [ProtocolRecommendation("USB", "usb://", "Dispositivo USB", "Use a busca automática para selecionar o dispositivo USB detectado.", 50)]

        self.recommendation_list.clear()
        for rec in self.recommendations:
            item = QListWidgetItem(f"{rec.title}\n{rec.uri}")
            item.setData(Qt.ItemDataRole.UserRole, rec.uri)
            self.recommendation_list.addItem(item)
        if self.recommendations:
            self.recommendation_list.setCurrentRow(0)

    def _recommendation_selected(self, row: int) -> None:
        if 0 <= row < len(self.recommendations):
            rec = self.recommendations[row]
            self.selected_uri = rec.uri
            self.recommendation_help.setText(f"{rec.explanation}\nConfiança: {rec.confidence}%")

    def _on_page_changed(self, page_id: int) -> None:
        if page_id == 2:
            try:
                self._prepare_recommendations()
            except Exception as exc:
                QMessageBox.warning(self, "Dados incompletos", str(exc))
                self.back()
        elif page_id == 3:
            if not self.queue_name.text().strip():
                base = self.host.text().strip() or "IMPRESSORA"
                suggested = "".join(char if char.isalnum() else "_" for char in base.upper())[:40]
                self.queue_name.setText(suggested or "IMPRESSORA")
            self.summary.setText(f"Protocolo/URI: {self.selected_uri}\nModo: instalação automática\nDriver: {self.driver.currentText()}")

    def validateCurrentPage(self) -> bool:
        if self.currentId() == 1:
            connection = self._connection_type()
            if connection in (ConnectionType.NETWORK, ConnectionType.WINDOWS) and not self.host.text().strip() and not self.detected.currentData():
                QMessageBox.information(self, "Informação necessária", "Informe o IP/host ou use a busca automática.")
                return False
            if connection is ConnectionType.WINDOWS and not self.share.text().strip():
                QMessageBox.information(self, "Informação necessária", "Informe o nome do compartilhamento no Windows.")
                return False
            if connection is ConnectionType.MANUAL and not self.manual_uri.text().strip():
                QMessageBox.information(self, "Informação necessária", "Informe a URI completa.")
                return False
        return super().validateCurrentPage()

    def accept(self) -> None:
        try:
            name = validate_queue_name(self.queue_name.text())
            uri = validate_device_uri(self.selected_uri)
            model = str(self.driver.currentData() or "everywhere")
            self.cups.add_printer(name, uri, model)
        except Exception as exc:
            QMessageBox.critical(self, "Não foi possível instalar", f"{exc}\n\nRevise os dados ou tente outro protocolo.")
            return
        QMessageBox.information(self, "Impressora instalada", "A fila foi criada. Agora você pode imprimir uma página de teste.")
        super().accept()
