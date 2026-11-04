"""Diálogo de preferências do aplicativo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.i18n import Translator
from app.paths import resource_root
from app.settings import AppSettings
from app.theme import theme_for
from app.ui_controls import StyledCheckBox, StyledComboBox


class SettingsDialog(QDialog):
    """Edita preferências gerais sem iniciar tarefas de rede."""

    settings_changed = Signal(str, str, bool, bool, int)

    def __init__(self, settings: AppSettings, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._translator = Translator(settings.language)
        self._theme = theme_for(settings.theme)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(500, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.configuration_group = QGroupBox()
        form = QGridLayout(self.configuration_group)
        form.setContentsMargins(12, 20, 12, 10)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(7)
        form.setColumnMinimumWidth(0, 178)
        form.setColumnMinimumWidth(1, 260)

        self.language_combo = StyledComboBox()
        self.language_combo.setFixedWidth(260)
        icon_dir = resource_root() / "icon"
        self.language_combo.addItem(QIcon(str(icon_dir / "flag_br.svg")), "", "pt-BR")
        self.language_combo.addItem(QIcon(str(icon_dir / "flag_us.svg")), "", "en-US")
        language_index = self.language_combo.findData(settings.language)
        self.language_combo.setCurrentIndex(max(0, language_index))
        self.language_label = QLabel()
        self.language_label.setFixedWidth(178)
        form.addWidget(self.language_label, 0, 0)
        form.addWidget(self.language_combo, 0, 1)

        self.theme_combo = StyledComboBox()
        self.theme_combo.setFixedWidth(260)
        self.theme_combo.addItem("", "night")
        self.theme_combo.addItem("", "day")
        theme_index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, theme_index))
        self.theme_label = QLabel()
        self.theme_label.setFixedWidth(178)
        form.addWidget(self.theme_label, 1, 0)
        form.addWidget(self.theme_combo, 1, 1)

        self.always_on_top_check = StyledCheckBox(self._theme)
        self.always_on_top_check.setChecked(settings.always_on_top)
        form.addWidget(self.always_on_top_check, 2, 0, 1, 2)

        self.check_updates_check = StyledCheckBox(self._theme)
        self.check_updates_check.setChecked(settings.check_updates)
        form.addWidget(self.check_updates_check, 3, 0, 1, 2)

        self.thumbnail_limit_spin = QSpinBox()
        self.thumbnail_limit_spin.setFixedWidth(260)
        self.thumbnail_limit_spin.setRange(0, 5000)
        self.thumbnail_limit_spin.setValue(settings.playlist_thumbnail_limit)
        self.thumbnail_limit_label = QLabel()
        self.thumbnail_limit_label.setFixedWidth(178)
        form.addWidget(self.thumbnail_limit_label, 4, 0)
        form.addWidget(self.thumbnail_limit_spin, 4, 1)

        layout.addWidget(self.configuration_group)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        self.default_button = QPushButton()
        self.default_button.setFixedWidth(72)
        button_row.addWidget(self.default_button)
        button_row.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons = buttons
        for button in (
            buttons.button(QDialogButtonBox.StandardButton.Ok),
            buttons.button(QDialogButtonBox.StandardButton.Cancel),
        ):
            button.setFixedWidth(72)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)
        self.default_button.clicked.connect(self._restore_defaults)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.always_on_top_check.toggled.connect(lambda _checked: self._emit_settings_changed())
        self.check_updates_check.toggled.connect(lambda _checked: self._emit_settings_changed())
        self.thumbnail_limit_spin.valueChanged.connect(lambda _value: self._emit_settings_changed())
        self._retranslate_ui()

    def _on_language_changed(self, _index: int) -> None:
        self._translator = Translator(str(self.language_combo.currentData()))
        self._retranslate_ui()
        self._emit_settings_changed()

    def _on_theme_changed(self, _index: int) -> None:
        self._theme = theme_for(str(self.theme_combo.currentData()))
        self.always_on_top_check.set_theme(self._theme)
        self.check_updates_check.set_theme(self._theme)
        self._emit_settings_changed()

    def _emit_settings_changed(self) -> None:
        self.settings_changed.emit(*self.values())
        self.raise_()
        self.activateWindow()

    def _restore_defaults(self) -> None:
        self.language_combo.blockSignals(True)
        self.theme_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(self.language_combo.findData("en-US"))
        self.theme_combo.setCurrentIndex(self.theme_combo.findData("night"))
        self.language_combo.blockSignals(False)
        self.theme_combo.blockSignals(False)

        self.always_on_top_check.setChecked(False)
        self.check_updates_check.setChecked(True)
        self.thumbnail_limit_spin.setValue(25)
        self._translator = Translator("en-US")
        self._theme = theme_for("night")
        self.always_on_top_check.set_theme(self._theme)
        self.check_updates_check.set_theme(self._theme)
        self._retranslate_ui()
        self._emit_settings_changed()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._translator.text("settings_title"))
        self.configuration_group.setTitle(self._translator.text("configuration"))
        self.language_label.setText(self._translator.text("language"))
        self.language_combo.setItemText(0, self._translator.text("language_pt"))
        self.language_combo.setItemText(1, self._translator.text("language_en"))
        self.language_combo.setToolTip(self._translator.text("language_future"))
        self.theme_label.setText(self._translator.text("theme"))
        self.theme_combo.setItemText(0, self._translator.text("theme_night"))
        self.theme_combo.setItemText(1, self._translator.text("theme_day"))
        self.always_on_top_check.setText(self._translator.text("always_on_top"))
        self.check_updates_check.setText(self._translator.text("check_updates_startup"))
        self.check_updates_check.setToolTip(self._translator.text("updater_future"))
        self.thumbnail_limit_label.setText(self._translator.text("thumbnail_limit"))
        self.thumbnail_limit_spin.setSuffix(self._translator.text("videos_suffix"))
        self.thumbnail_limit_spin.setToolTip(self._translator.text("thumbnail_limit_tooltip"))
        self.default_button.setText(self._translator.text("default"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self._translator.text("ok"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self._translator.text("cancel")
        )

    def values(self) -> tuple[str, str, bool, bool, int]:
        """Retorna idioma, tema, always-on-top, atualização e limite de miniaturas."""
        return (
            str(self.language_combo.currentData()),
            str(self.theme_combo.currentData()),
            self.always_on_top_check.isChecked(),
            self.check_updates_check.isChecked(),
            self.thumbnail_limit_spin.value(),
        )
