"""Diálogo de informações e links do Tuberino Downloader."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.i18n import Translator
from app.version import APP_VERSION


class AboutDialog(QDialog):
    """Apresenta a identidade do aplicativo e seus links públicos."""

    def __init__(
        self, translator: Translator, logo_path: Path, parent: QDialog | None = None
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setFixedSize(510, 270)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        content = QHBoxLayout()
        content.setSpacing(10)
        logo = QLabel()
        logo.setFixedSize(84, 84)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        content.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        details = QVBoxLayout()
        details.setSpacing(4)
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.version_label = QLabel()
        self.description_label = QLabel()
        self.github_label = QLabel()
        self.support_label = QLabel()
        for link_label in (self.github_label, self.support_label):
            link_label.setOpenExternalLinks(True)
            link_label.setTextFormat(Qt.TextFormat.RichText)
        details.addWidget(self.name_label)
        details.addWidget(self.version_label)
        details.addWidget(self.description_label)
        details.addSpacing(2)
        details.addWidget(self.github_label)
        details.addWidget(self.support_label)
        details.addStretch()
        content.addLayout(details, 1)
        layout.addLayout(content, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton()
        self.close_button.setFixedWidth(72)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.retranslate(translator)

    def retranslate(self, translator: Translator) -> None:
        self._translator = translator
        self.setWindowTitle(translator.text("about_title"))
        self.name_label.setText(translator.text("app_title"))
        self.version_label.setText(f"{translator.text('version_label')} {APP_VERSION}")
        self.description_label.setText(translator.text("about_description"))
        self.github_label.setText(
            f'<a href="https://github.com/mmachida/Tuberino-Downloader">'
            f"{translator.text('github_link')}</a>"
        )
        self.support_label.setText(
            f'<a href="https://ko-fi.com/mmachida">{translator.text("support_project")}</a>'
        )
        self.close_button.setText(translator.text("close"))
