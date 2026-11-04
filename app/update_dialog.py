"""Diálogo de consulta e preparação de atualizações."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.i18n import Translator
from app.updates.service import ReleaseInfo


class UpdateDialog(QDialog):
    """Exibe changelog e progresso sem executar rede na thread da UI."""

    download_requested = Signal()

    def __init__(self, translator: Translator, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._current_version = current_version
        self.setFixedSize(530, 412)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        self.updates_group = QGroupBox()
        group_layout = QGridLayout(self.updates_group)
        group_layout.setContentsMargins(9, 20, 9, 9)
        group_layout.setHorizontalSpacing(12)
        group_layout.setVerticalSpacing(8)
        group_layout.setColumnMinimumWidth(0, 82)

        self.current_name_label = QLabel()
        self.current_value_label = QLabel()
        self.status_name_label = QLabel()
        self.status_value_label = QLabel()
        self.latest_name_label = QLabel()
        self.latest_value_label = QLabel()
        self.status_value_label.setWordWrap(True)
        self.latest_value_label.setWordWrap(True)

        group_layout.addWidget(self.current_name_label, 0, 0)
        group_layout.addWidget(self.current_value_label, 0, 1)
        group_layout.addWidget(self.status_name_label, 1, 0)
        group_layout.addWidget(self.status_value_label, 1, 1)
        group_layout.addWidget(self.latest_name_label, 2, 0)
        group_layout.addWidget(self.latest_value_label, 2, 1)

        self.notes_title = QLabel()
        self.notes_edit = QTextEdit()
        self.notes_edit.setReadOnly(True)
        group_layout.addWidget(self.notes_title, 3, 0, 1, 2)
        group_layout.addWidget(self.notes_edit, 4, 0, 1, 2)
        group_layout.setRowStretch(4, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        group_layout.addWidget(self.progress, 5, 0, 1, 2)
        layout.addWidget(self.updates_group, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch()
        self.download_button = QPushButton()
        self.download_button.setVisible(False)
        self.download_button.clicked.connect(self.download_requested.emit)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self._retranslate_ui()
        self.show_checking()

    def set_translator(self, translator: Translator) -> None:
        self._translator = translator
        self._retranslate_ui()

    def show_checking(self) -> None:
        self._set_optional_details_visible(False)
        self.status_value_label.setText(self._translator.text("update_checking"))
        self.progress.setVisible(False)
        self.download_button.setEnabled(False)

    def show_no_update(self) -> None:
        self._set_optional_details_visible(False)
        self.status_value_label.setText(self._translator.text("update_no_update"))
        self.progress.setVisible(False)
        self.download_button.setEnabled(False)

    def show_error(self, detail: str) -> None:
        self._set_optional_details_visible(False)
        message = self._translator.text("update_failed")
        detail = detail.strip()
        self.status_value_label.setText(f"{message}\n{detail}" if detail else message)
        self.progress.setVisible(False)
        self.download_button.setEnabled(False)

    def show_release(self, release: ReleaseInfo) -> None:
        self._set_optional_details_visible(True)
        self.status_value_label.setText(self._translator.text("update_available"))
        self.latest_value_label.setText(release.version_text)
        self.notes_edit.setPlainText(release.notes)
        self.progress.setVisible(False)
        self.download_button.setVisible(True)
        self.download_button.setEnabled(True)

    def set_downloading(self) -> None:
        self._set_optional_details_visible(True)
        self.status_value_label.setText(self._translator.text("update_downloading"))
        self.download_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

    def set_progress(self, completed: int, total: int) -> None:
        value = 0 if total <= 0 else max(0, min(100, int(completed * 100 / total)))
        self.progress.setVisible(True)
        self.progress.setValue(value)

    def set_ready(self) -> None:
        self.status_value_label.setText(self._translator.text("update_ready"))
        self.progress.setValue(100)

    def _set_optional_details_visible(self, visible: bool) -> None:
        self.latest_name_label.setVisible(visible)
        self.latest_value_label.setVisible(visible)
        self.notes_title.setVisible(visible)
        self.notes_edit.setVisible(visible)
        self.download_button.setVisible(visible)

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._translator.text("update_dialog_title"))
        self.updates_group.setTitle(self._translator.text("update_group"))
        self.current_name_label.setText(self._translator.text("update_current_version_label"))
        self.current_value_label.setText(self._current_version)
        self.status_name_label.setText(self._translator.text("update_status_label"))
        self.latest_name_label.setText(self._translator.text("update_latest_version_label"))
        self.notes_title.setText(self._translator.text("update_changelog"))
        self.download_button.setText(self._translator.text("update_download_install"))
        self.close_button.setText(self._translator.text("close"))
        button_width = max(
            150,
            self.download_button.sizeHint().width(),
            self.close_button.sizeHint().width(),
        )
        self.download_button.setFixedWidth(button_width)
        self.close_button.setFixedWidth(button_width)
