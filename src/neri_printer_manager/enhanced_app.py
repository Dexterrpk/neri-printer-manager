"""Interface aprimorada com descoberta detalhada e reparos explicáveis."""
from __future__ import annotations

import sys
from typing import Any

from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox

from .cups_filters import CupsFilterService
from .device_discovery import RichDiscoveryService
from .guided_app import GuidedWindow
from .host_display import HostDisplayResolver
from .logging_config import configure_logging
from .repair import RepairResult, RepairService


class EnhancedWindow(GuidedWindow):
    """Mantém todos os módulos existentes e melhora ferramentas e filtros."""

    def _tools(self):
        page, layout = self._page(
            "Ferramentas",
            "Descubra o nome e modelo da impressora, o computador que a publica, o IP e se ela já está instalada neste Mint.",
        )
        self.tools_status = QLabel("Clique em Descobrir impressoras.")
        self.tools_status.setObjectName("muted")
        self.tools_status.setWordWrap(True)
        layout.addWidget(self.tools_status)
        self.tools_table = self._table(
            [
                "Nome da impressora",
                "Modelo",
                "Computador / Host",
                "Endereço IP",
                "Protocolo",
                "Fila local",
            ]
        )
        layout.addWidget(self.tools_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Descobrir impressoras", self.discover_devices, True))
        row.addWidget(self._button("Exportar HTML", self.export_html))
        row.addWidget(self._button("Pacote de suporte ZIP", self.export_bundle))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _diagnostics(self):
        page, layout = self._page(
            "Correção e diagnóstico",
            "Analisa somente falhas atuais. Cada correção mostra o que será feito e confirma se o problema desapareceu.",
        )
        self.diag_summary = QLabel("Clique em Verificar tudo ou Analisar filtros atuais.")
        self.diag_summary.setObjectName("muted")
        self.diag_summary.setWordWrap(True)
        layout.addWidget(self.diag_summary)
        self.diag_table = self._table(["Problema", "Estado", "Origem / evidência", "Ação segura"])
        layout.addWidget(self.diag_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Verificar tudo", self.refresh_diagnostics, True))
        row.addWidget(self._button("Instalar dependências", self.repair_dependencies))
        row.addWidget(self._button("Analisar filtros atuais", self.refresh_filters))
        row.addWidget(self._button("Aplicar correção selecionada", self.repair_filter))
        row.addStretch()
        layout.addLayout(row)
        return page

    def discover_devices(self) -> None:
        self.tools_status.setText(
            "Consultando filas locais e rede. Resolvendo nomes por DNS reverso e NetBIOS..."
        )
        self._run(RichDiscoveryService().discover, self._show_discovered)

    def _show_discovered(self, items: list[Any]) -> None:
        resolver = HostDisplayResolver()
        rows = []
        for item in items:
            display_host = resolver.resolve(item.host, item.address)
            display_ip = item.address if item.address and item.address != "Local" else "Local"
            rows.append(
                (
                    item.name,
                    item.model,
                    display_host,
                    display_ip,
                    item.protocol,
                    item.installed_queue or "Não instalada",
                )
            )
        self._fill(self.tools_table, rows)
        installed = sum(1 for item in items if item.installed_queue)
        remote = len(items) - installed
        self.tools_status.setText(
            f"{len(items)} impressora(s) identificada(s): {installed} instalada(s) neste computador e {remote} disponível(is) na rede."
            if items
            else "Nenhuma impressora foi identificada. Verifique Avahi, CUPS e conectividade da rede."
        )

    def refresh_filters(self) -> None:
        self.diag_summary.setText("Analisando apenas erros recentes e a integridade atual dos filtros...")
        self._run(CupsFilterService().diagnose, self._show_filters)

    def _show_filters(self, items: list[Any]) -> None:
        self.filter_findings = items
        if not items:
            self._fill(self.diag_table, [])
            self.diag_summary.setText(
                "Nenhuma falha atual de filtro, backend, PPD ou Ghostscript foi encontrada."
            )
            return
        action_names = {
            "reinstall_filters": "Reinstalar componentes CUPS ausentes",
            "reinstall_ghostscript": "Reinstalar Ghostscript",
            "check_ppd": "Recriar fila ou escolher outro driver",
            "fix_permissions": "Corrigir somente permissões oficiais do CUPS",
            "restart_cups": "Reiniciar CUPS",
            "check_backend": "Verificar URI, rede ou credenciais",
            "clear_stale_jobs": "Limpar trabalhos travados",
        }
        self._fill(
            self.diag_table,
            [
                (
                    item.title,
                    item.severity.value,
                    f"{item.source}: {item.evidence}",
                    "; ".join(action_names.get(action.value, action.value) for action in item.actions)
                    or "Somente orientação; nenhuma alteração automática",
                )
                for item in items
            ],
        )
        self.diag_summary.setText(
            f"{len(items)} condição(ões) atual(is) encontrada(s). Selecione uma linha para corrigir somente aquele problema."
        )

    def repair_filter(self) -> None:
        row = self.diag_table.currentRow()
        if row < 0 or row >= len(self.filter_findings):
            QMessageBox.information(self, "Selecione", "Analise os filtros e escolha uma condição atual.")
            return
        finding = self.filter_findings[row]
        answer = QMessageBox.question(
            self,
            "Confirmar correção",
            f"Problema: {finding.title}\n\nEvidência: {finding.evidence}\n\nAplicar somente as ações indicadas para esta condição?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(lambda: RepairService().repair_filter_finding(finding), self._show_repair_results)

    def _show_repair_results(self, results: list[RepairResult]) -> None:
        text = "\n".join(f"• {item.action}: {item.status.value} — {item.message}" for item in results)
        QMessageBox.information(self, "Resultado da correção", text or "Nenhuma ação necessária.")
        self.refresh_filters()


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Neri Printer Manager")
    window = EnhancedWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
