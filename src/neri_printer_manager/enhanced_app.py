"""Interface aprimorada com descoberta detalhada e reparos explicáveis."""
from __future__ import annotations

import sys
from typing import Any

from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox

from .device_discovery import RichDiscoveryService
from .guided_app import GuidedWindow
from .health import HealthAction, HealthCheck, PrinterHealthService
from .host_display import HostDisplayResolver
from .logging_config import configure_logging
from .repair import RepairResult, RepairService, RepairStatus


class EnhancedWindow(GuidedWindow):
    """Mantém todos os módulos existentes e melhora ferramentas e diagnóstico."""

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
            "Central de saúde e correção",
            "O programa verifica serviços, dependências, filas, trabalhos, permissões, filtros e drivers. Selecione um problema para ver a causa e aplicar uma solução verificável.",
        )
        self.health_checks: list[HealthCheck] = []
        self.diag_summary = QLabel("Clique em Fazer diagnóstico completo.")
        self.diag_summary.setObjectName("muted")
        self.diag_summary.setWordWrap(True)
        layout.addWidget(self.diag_summary)
        self.diag_table = self._table(["Área", "Situação", "O que foi encontrado", "Solução recomendada"])
        layout.addWidget(self.diag_table, 1)
        row = QHBoxLayout()
        row.addWidget(self._button("Fazer diagnóstico completo", self.refresh_diagnostics, True))
        row.addWidget(self._button("Ver detalhes", self.show_health_details))
        row.addWidget(self._button("Corrigir selecionado", self.repair_selected_health))
        row.addWidget(self._button("Corrigir automaticamente", self.repair_all_safe))
        row.addStretch()
        layout.addLayout(row)
        note = QLabel(
            "Correções automáticas são limitadas a ações seguras: instalar componentes obrigatórios, ativar serviços, reiniciar o CUPS e corrigir filtros confirmados. Filas, credenciais e drivers específicos exigem sua confirmação."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    @staticmethod
    def _discover_with_display_names() -> list[tuple[Any, str]]:
        """Executa descoberta e resolução de nomes integralmente fora da thread da UI."""
        items = RichDiscoveryService().discover()
        resolver = HostDisplayResolver()
        try:
            names = resolver.resolve_many((item.host, item.address) for item in items)
        except Exception:
            names = [
                item.host if item.host and item.host != item.address else "Não identificado"
                for item in items
            ]
        return list(zip(items, names, strict=True))

    def discover_devices(self) -> None:
        self.tools_status.setText(
            "Consultando filas locais e rede. A resolução de nomes possui timeout seguro."
        )
        self.tools_table.setRowCount(0)
        self._run(self._discover_with_display_names, self._show_discovered)

    def _show_discovered(self, resolved: list[tuple[Any, str]]) -> None:
        rows = []
        for item, display_host in resolved:
            display_ip = item.address if item.address and item.address != "Local" else "Local"
            rows.append(
                (
                    item.name or "Impressora sem nome",
                    item.model or "Modelo não informado",
                    display_host or "Não identificado",
                    display_ip,
                    item.protocol or "Desconhecido",
                    item.installed_queue or "Não instalada",
                )
            )
        self._fill(self.tools_table, rows)
        installed = sum(1 for item, _ in resolved if item.installed_queue)
        remote = len(resolved) - installed
        self.tools_status.setText(
            f"{len(resolved)} impressora(s) identificada(s): {installed} instalada(s) neste computador e {remote} disponível(is) na rede."
            if resolved
            else "Nenhuma impressora foi identificada. Verifique CUPS, Avahi e conectividade da rede."
        )

    def refresh_diagnostics(self) -> None:
        self.diag_summary.setText("Verificando o ambiente completo sem interromper a interface...")
        self.diag_table.setRowCount(0)
        self._run(PrinterHealthService().run_all, self._show_health)

    def _show_health(self, items: list[HealthCheck]) -> None:
        self.health_checks = items
        status_names = {"ok": "OK", "warning": "ATENÇÃO", "error": "PROBLEMA"}
        self._fill(
            self.diag_table,
            [
                (
                    item.category,
                    status_names.get(item.severity.value, item.severity.value),
                    f"{item.title}: {item.summary}",
                    item.action_label,
                )
                for item in items
            ],
        )
        errors = sum(item.severity.value == "error" for item in items)
        warnings = sum(item.severity.value == "warning" for item in items)
        ok = sum(item.severity.value == "ok" for item in items)
        if errors == 0 and warnings == 0:
            text = f"Ambiente saudável: {ok} verificações concluídas sem problemas."
        else:
            text = f"Diagnóstico concluído: {ok} OK, {warnings} aviso(s) e {errors} problema(s). Selecione uma linha para corrigir ou entender a causa."
        self.diag_summary.setText(text)
        first_problem = next((index for index, item in enumerate(items) if item.severity.value != "ok"), None)
        if first_problem is not None:
            self.diag_table.selectRow(first_problem)

    def _selected_health(self) -> HealthCheck | None:
        row = self.diag_table.currentRow()
        if row < 0 or row >= len(self.health_checks):
            QMessageBox.information(self, "Selecione uma verificação", "Escolha uma linha do diagnóstico.")
            return None
        return self.health_checks[row]

    def show_health_details(self) -> None:
        item = self._selected_health()
        if item is None:
            return
        QMessageBox.information(
            self,
            item.title,
            f"Área: {item.category}\nEstado: {item.severity.value.upper()}\n\nResumo:\n{item.summary}\n\nDetalhes técnicos:\n{item.details}\n\nSolução:\n{item.action_label}",
        )

    def repair_selected_health(self) -> None:
        item = self._selected_health()
        if item is None:
            return
        if item.action is HealthAction.NONE:
            QMessageBox.information(self, "Nenhuma correção necessária", item.summary)
            return
        answer = QMessageBox.question(
            self,
            "Confirmar correção",
            f"Problema: {item.title}\n\nO programa encontrou:\n{item.summary}\n\nAção proposta:\n{item.action_label}\n\nContinuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.diag_summary.setText(f"Aplicando correção: {item.action_label}...")
        self._run(lambda: RepairService().repair_health_check(item), self._show_repair_results)

    def repair_all_safe(self) -> None:
        candidates = [item for item in self.health_checks if item.safe_automatic and item.severity.value != "ok"]
        if not candidates:
            QMessageBox.information(self, "Ambiente", "Nenhuma correção automática segura está pendente.")
            return
        labels = "\n".join(f"• {item.title}: {item.action_label}" for item in candidates)
        answer = QMessageBox.question(
            self,
            "Corrigir problemas seguros",
            f"Serão aplicadas somente estas correções seguras:\n\n{labels}\n\nProblemas de credencial, endereço ou escolha manual de driver não serão alterados. Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.diag_summary.setText("Aplicando correções seguras e verificando o resultado...")
        self._run(lambda: RepairService().repair_safe_checks(candidates), self._show_repair_results)

    # Compatibilidade com chamadas da interface anterior.
    def refresh_filters(self) -> None:
        self.refresh_diagnostics()

    def repair_filter(self) -> None:
        self.repair_selected_health()

    def _show_repair_results(self, results: list[RepairResult]) -> None:
        status_names = {
            RepairStatus.SUCCESS: "RESOLVIDO",
            RepairStatus.FAILED: "NÃO RESOLVIDO",
            RepairStatus.SKIPPED: "ORIENTAÇÃO",
        }
        text = "\n".join(
            f"• {status_names.get(item.status, item.status.value)} — {item.message}"
            for item in results
        )
        failures = any(item.status is RepairStatus.FAILED for item in results)
        if failures:
            QMessageBox.warning(self, "Resultado da correção", text or "A correção não foi concluída.")
        else:
            QMessageBox.information(self, "Resultado da correção", text or "Nenhuma ação necessária.")
        self.refresh_diagnostics()


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Neri Printer Manager")
    window = EnhancedWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
