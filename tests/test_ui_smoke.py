import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTabWidget

from neri_printer_manager.app import MainWindow


def test_main_window_opens_with_all_modules() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_refresh=False)
    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert tabs.count() == 10
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Visão geral",
        "Impressoras",
        "Fila",
        "Descoberta",
        "Rede",
        "Diagnóstico",
        "Dependências",
        "Filtros CUPS",
        "Compartilhamento",
        "Relatórios",
    ]
    window.close()
    application.processEvents()
