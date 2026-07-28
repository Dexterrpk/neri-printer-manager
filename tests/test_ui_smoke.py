import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QPushButton,
    QScrollArea,
    QStackedWidget,
)

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
    assert isinstance(window.pages.widget(4), QScrollArea)
    assert isinstance(window.pages.widget(5), QScrollArea)

    window.resize(1000, 680)
    window.show()
    application.processEvents()
    window.sidebar.blockSignals(True)
    for index in range(window.pages.count()):
        window.pages.setCurrentIndex(index)
        application.processEvents()
        clipped = [
            button.text()
            for button in window.pages.currentWidget().findChildren(QPushButton)
            if button.isVisible() and button.width() < button.sizeHint().width()
        ]
        assert clipped == []
    window.close()
    application.processEvents()
