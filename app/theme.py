"""Temas visuais do Tuberino Downloader."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_THEMES = ("night", "day")


@dataclass(frozen=True, slots=True)
class Theme:
    """Cores e estilos compartilhados pela janela e pelos widgets customizados."""

    name: str
    window: str
    panel: str
    field: str
    border: str
    text: str
    muted_text: str
    button: str
    button_hover: str
    button_pressed: str
    accent: str
    accent_hover: str
    tab: str
    tab_hover: str
    tab_selected: str
    row: str
    row_processing: str
    row_progress: str
    row_done: str
    row_done_progress: str
    row_failed: str
    row_failed_progress: str
    row_cancelled: str
    row_cancelled_progress: str
    thumbnail: str
    thumbnail_text: str
    error_text: str

    def application_stylesheet(self) -> str:
        """Retorna o stylesheet global aplicado à janela e aos diálogos."""
        is_day = self.name == "day"
        group_radius = "2px" if is_day else "4px"
        control_radius = "2px" if is_day else "3px"
        button_radius = "2px" if is_day else "4px"
        control_padding = "2px 5px" if is_day else "4px 6px"
        button_padding = "3px 10px" if is_day else "5px 12px"
        button_background = (
            "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #ffffff, stop: 1 #e4e7ea)"
            if is_day
            else self.button
        )
        button_hover_background = (
            "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #ffffff, stop: 1 #d5e4f2)"
            if is_day
            else self.button_hover
        )
        button_pressed_background = (
            "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #d5e4f2, stop: 1 #ffffff)"
            if is_day
            else self.button_pressed
        )
        button_border = "#aeb7c1" if is_day else self.border
        return f"""
            QWidget {{
                background-color: {self.window};
                color: {self.text};
                font-family: "Segoe UI";
                font-size: 9pt;
            }}
            QMainWindow, QDialog {{
                background-color: {self.window};
            }}
            QLabel, QCheckBox, QRadioButton {{
                background-color: transparent;
            }}
            QRadioButton::indicator {{
                width: 13px;
                height: 13px;
                border: 1px solid {self.border};
                border-radius: 7px;
                background-color: {self.field};
            }}
            QRadioButton::indicator:hover {{
                border: 1px solid {self.accent};
            }}
            QRadioButton::indicator:checked {{
                border: 1px solid {self.accent};
                background-color: {self.accent};
            }}
            QRadioButton::indicator:disabled {{
                border: 1px solid {self.muted_text};
                background-color: {self.panel};
            }}
            QGroupBox {{
                background-color: {self.panel};
                border: 1px solid {self.border};
                border-radius: {group_radius};
                margin-top: 8px;
                padding: 6px 5px 5px 5px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                background-color: {self.panel};
            }}
            QLineEdit, QComboBox, QSpinBox, QTextEdit {{
                background-color: {self.field};
                color: {self.text};
                border: 1px solid {self.border};
                border-radius: {control_radius};
                padding: {control_padding};
                selection-background-color: {self.accent};
                selection-color: #ffffff;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
                border: 1px solid {self.accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.field};
                color: {self.text};
                border: 1px solid {self.border};
                selection-background-color: {self.accent};
                selection-color: #ffffff;
            }}
            QComboBox QAbstractItemView::item:disabled {{
                color: {self.muted_text};
            }}
            QFrame#siteSeparator {{
                background-color: {self.border};
                border: none;
            }}
            QPushButton {{
                background: {button_background};
                color: {self.text};
                border: 1px solid {button_border};
                border-radius: {button_radius};
                padding: {button_padding};
            }}
            QPushButton:hover {{
                background: {button_hover_background};
            }}
            QPushButton:pressed {{
                background: {button_pressed_background};
            }}
            QPushButton:flat {{
                background: transparent;
                border: none;
            }}
            QPushButton:flat:hover {{
                background: {self.button_hover};
                border: none;
            }}
            QPushButton:disabled {{
                background-color: {self.panel};
                color: {self.muted_text};
                border-color: {button_border};
            }}
            QListWidget {{
                background-color: {self.panel};
                color: {self.text};
                border: 1px solid {self.border};
                border-radius: 4px;
            }}
            QToolTip {{
                background-color: {self.field};
                color: {self.text};
                border: 1px solid {self.border};
            }}
            QProgressBar {{
                background-color: {self.field};
                border: 1px solid {self.border};
                border-radius: 3px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {self.accent};
            }}
            QScrollBar:vertical {{
                background-color: {self.window};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {self.border};
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {self.muted_text};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """

    def tabs_stylesheet(self) -> str:
        """Retorna o estilo específico das abas de plataformas."""
        tab_padding = "5px 13px" if self.name == "day" else "6px 14px"
        return f"""
            QTabWidget {{
                background: {self.window};
            }}
            QTabWidget::pane {{
                border: none;
                background: {self.window};
            }}
            QTabBar {{
                background: {self.window};
                border-bottom: 1px solid {self.border};
            }}
            QTabBar::tab {{
                background: {self.tab};
                color: {self.text};
                border: 1px solid {self.border};
                border-bottom: 1px solid {self.border};
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                padding: {tab_padding};
                margin: 2px 2px 0 0;
            }}
            QTabBar::tab:hover {{
                background: {self.tab_hover};
                color: {self.text};
            }}
            QTabBar::tab:selected {{
                background: {self.tab_selected};
                color: {self.text};
                border: 1px solid {self.border};
                border-bottom: 1px solid {self.border};
            }}
        """

    def menu_stylesheet(self) -> str:
        """Retorna o estilo compacto da barra de menus."""
        return f"""
            QMenuBar {{
                background-color: {self.window};
                color: {self.text};
                padding: 2px;
                border-bottom: 1px solid {self.border};
            }}
            QMenuBar::item {{
                padding: 5px 10px;
            }}
            QMenuBar::item:selected, QMenuBar::item:pressed {{
                background-color: {self.button_hover};
            }}
            QMenu {{
                background-color: {self.panel};
                color: {self.text};
                border: 1px solid {self.border};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 22px 6px 10px;
            }}
            QMenu::item:selected {{
                background-color: {self.button_hover};
            }}
        """


_THEMES = {
    "night": Theme(
        name="night",
        window="#1f1f1f",
        panel="#242424",
        field="#2b2b2b",
        border="#4c4c4c",
        text="#f0f0f0",
        muted_text="#b8c0cc",
        button="#2d2d2d",
        button_hover="#3a3f47",
        button_pressed="#454b55",
        accent="#60a5fa",
        accent_hover="#93c5fd",
        tab="#292c31",
        tab_hover="#343942",
        tab_selected="#3d4c60",
        row="#1a1e24",
        row_processing="#203345",
        row_progress="#286ca6",
        row_done="#183b31",
        row_done_progress="#238b6c",
        row_failed="#4b2025",
        row_failed_progress="#c43d4c",
        row_cancelled="#4b3820",
        row_cancelled_progress="#b7791f",
        thumbnail="#20242a",
        thumbnail_text="#cbd5e1",
        error_text="#fecaca",
    ),
    "day": Theme(
        name="day",
        window="#f1f3f5",
        panel="#f3f3f3",
        field="#ffffff",
        border="#b9c1ca",
        text="#172b4d",
        muted_text="#526273",
        button="#f8f9fa",
        button_hover="#e4edf7",
        button_pressed="#d5e4f2",
        accent="#0a7bdc",
        accent_hover="#0868b7",
        tab="#e3e8ee",
        tab_hover="#d6e3f0",
        tab_selected="#cfe3f7",
        row="#ffffff",
        row_processing="#eaf3ff",
        row_progress="#dbeafe",
        row_done="#dcfce7",
        row_done_progress="#86efac",
        row_failed="#fee2e2",
        row_failed_progress="#fca5a5",
        row_cancelled="#fef3c7",
        row_cancelled_progress="#fcd34d",
        thumbnail="#e8edf3",
        thumbnail_text="#334155",
        error_text="#b42318",
    ),
}


def theme_for(name: str) -> Theme:
    """Retorna um tema válido, usando Night para valores antigos ou inválidos."""
    return _THEMES.get(name, _THEMES["night"])
