import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget, QStackedWidget

from neri_printer_manager.app import MainWindow


def test_main_window_opens_with_guided_navigation() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow(auto_refresh=False)
    assert isinstance(window.sidebar, QListWidget)
    assert isinstance(window.pages, QStackedWidget)
    assert window.sidebar.count() == 7
    assert window.pages.count() == 7
    assert [window.sidebar.item(index).text() for index in range(window.sidebar.count())] == [
        "Início",
        "Encontrar na rede",
        "Minhas impressoras",
        "Fila de impressão",
        "Corrigir problemas",
        "Compartilhamento",
        "Ferramentas técnicas",
    ]
    assert window.home_host.placeholderText()
    assert window.find_host.placeholderText()
    window.close()
    application.processEvents()
