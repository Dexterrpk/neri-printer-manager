"""Tema visual leve e legível para o aplicativo."""

APP_STYLESHEET = """
QMainWindow, QWidget {
    font-size: 14px;
}
QTabWidget::pane {
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 6px;
}
QTabBar::tab {
    min-width: 115px;
    padding: 10px 14px;
    margin: 2px;
    border-radius: 6px;
}
QTabBar::tab:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QPushButton {
    min-height: 34px;
    padding: 4px 14px;
    border-radius: 7px;
}
QPushButton:hover {
    background: palette(midlight);
}
QLineEdit, QComboBox, QListWidget, QTableWidget {
    min-height: 32px;
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 4px;
}
QHeaderView::section {
    padding: 8px;
    font-weight: 600;
}
QWizard QLabel {
    line-height: 1.4;
}
QRadioButton {
    min-height: 28px;
    font-weight: 600;
}
"""
