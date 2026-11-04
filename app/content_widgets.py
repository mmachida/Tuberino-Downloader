"""Widgets de apresentação para itens de vídeo e playlist."""

from __future__ import annotations

import html

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import Translator
from app.models import ContentItem, ProgressStage
from app.theme import Theme, theme_for


class WideCheckBox(QCheckBox):
    """Caixa de seleção com toda a faixa do widget acionável."""

    def __init__(self, theme: Theme | None = None) -> None:
        super().__init__()
        self._theme = theme or theme_for("night")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.isChecked())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._theme.panel))
        painter.setPen(QColor(self._theme.border))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        size = 14
        left = (self.width() - size) // 2
        top = (self.height() - size) // 2
        indicator = QRectF(left, top, size, size)
        if self.isChecked():
            painter.setPen(QColor(self._theme.accent))
            painter.setBrush(QColor(self._theme.accent))
        else:
            indicator_color = self._theme.muted_text if not self.isEnabled() else self._theme.border
            painter.setPen(QColor(indicator_color))
            painter.setBrush(QColor(self._theme.field))
        painter.drawRoundedRect(indicator, 2, 2)

        if self.isChecked():
            painter.setPen(QColor("#ffffff"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            check = QPainterPath()
            check.moveTo(left + 3, top + 7)
            check.lineTo(left + 6, top + 10)
            check.lineTo(left + 11, top + 4)
            painter.drawPath(check)
        painter.end()


class ClickableLabel(QLabel):
    """QLabel simples que transforma clique esquerdo em sinal reutilizável."""

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ContentRowWidget(QWidget):
    """Linha selecionável com thumbnail, título, canal e duração."""

    selected_changed = Signal(str, bool)
    remove_requested = Signal(str)
    open_requested = Signal(str)

    def __init__(
        self,
        item: ContentItem,
        *,
        playlist: bool = False,
        translator: Translator | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__()
        self._translator = translator or Translator()
        self._theme = theme or theme_for("night")
        self._item_title = item.title
        self._uploader = item.uploader
        self._webpage_url = item.webpage_url
        self._duration_seconds = item.duration
        self._availability_source = item.availability_error or "Não disponível"
        self.item_id = item.video_id
        self.playlist = playlist
        self._unavailable = not item.available
        self._unavailable_text = self._translator.message(self._availability_source)
        self._duration_text = _format_duration(item.duration, self._translator)
        self._progress_percentage: float | None = None
        self._progress_stage: ProgressStage | None = None
        self.setMinimumHeight(104)

        self.checkbox = WideCheckBox(self._theme)
        self.checkbox.setChecked(item.selected and item.available)
        self.checkbox.setEnabled(item.available)
        self.checkbox.setFixedWidth(38)
        self.checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setToolTip(self._translator.text("include_item_tooltip"))
        self.checkbox.toggled.connect(
            lambda checked: self.selected_changed.emit(self.item_id, checked)
        )

        self.thumbnail_label = ClickableLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setWordWrap(True)
        self.thumbnail_label.setFixedSize(168, 94)
        self.thumbnail_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.thumbnail_label.setText(self._thumbnail_placeholder())
        self.thumbnail_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumbnail_label.setToolTip(self._translator.text("open_original_tooltip"))
        self.thumbnail_label.clicked.connect(lambda: self.open_requested.emit(self.item_id))

        title = html.escape(self._translator.message(item.title))
        webpage_url = html.escape(item.webpage_url, quote=True)
        self.title_label = QLabel(f'<a href="{webpage_url}">{title}</a>')
        self.title_label.setWordWrap(True)
        self.title_label.setFixedHeight(42)
        self.title_label.setOpenExternalLinks(False)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.setToolTip(
            f"{self._translator.message(item.title)}\n"
            f"{self._translator.text('open_original_tooltip')}"
        )
        self.title_label.linkActivated.connect(lambda _url: self.open_requested.emit(self.item_id))
        self.channel_label = QLabel(item.uploader or self._translator.text("channel_unavailable"))
        self.duration_label = QLabel(self._duration_text)

        self.remove_button = QPushButton("×")
        self.remove_button.setFixedWidth(40)
        self.remove_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.remove_button.setToolTip(self._translator.text("remove_item_tooltip"))
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_theme_styles()
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.item_id))

        metadata = QVBoxLayout()
        metadata.setSpacing(4)
        metadata.addWidget(self.title_label)
        metadata.addWidget(self.channel_label)
        metadata.addWidget(self.duration_label)
        metadata.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(10)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.thumbnail_label)
        layout.addLayout(metadata, 1)
        layout.addWidget(self.remove_button)

        if self._unavailable:
            self.set_unavailable(self._availability_source)

    def set_thumbnail(self, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        self.thumbnail_label.setPixmap(
            pixmap.scaled(
                self.thumbnail_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.thumbnail_label.setText("")

    def set_theme(self, theme: Theme) -> None:
        """Atualiza as cores da linha sem remover conteúdo ou progresso."""
        self._theme = theme
        self._apply_theme_styles()
        self.update()

    def _apply_theme_styles(self) -> None:
        self.checkbox.set_theme(self._theme)
        item_text = "#000000" if self._theme.name == "day" else self._theme.text
        self.thumbnail_label.setStyleSheet(
            f"background: {self._theme.thumbnail}; color: {item_text}; "
            "border-radius: 6px; font-size: 11px;"
        )
        self.title_label.setStyleSheet(
            f"QLabel {{ font-size: 15px; font-weight: 600; color: {item_text}; }}"
            f"QLabel a {{ color: {item_text}; text-decoration: underline; }}"
        )
        self._refresh_title_label()
        self.channel_label.setStyleSheet(f"color: {item_text};")
        self.duration_label.setStyleSheet(f"color: {item_text};")
        self.remove_button.setStyleSheet(
            f"QPushButton {{ color: {self._theme.error_text}; font-size: 18px; "
            "font-weight: 600; border: none; border-radius: 5px; }"
            f"QPushButton:hover {{ background: {self._theme.row_failed}; "
            f"color: {self._theme.error_text}; }}"
        )

    def set_thumbnail_policy(self, disabled: bool) -> None:
        """Atualiza o placeholder sem recriar a linha da lista."""
        self.playlist = disabled
        self.thumbnail_label.clear()
        self.thumbnail_label.setText(self._thumbnail_placeholder())

    def set_language(self, translator: Translator) -> None:
        """Atualiza textos fixos sem remover a miniatura já carregada."""
        self._translator = translator
        self._unavailable_text = self._translator.message(self._availability_source)
        self._duration_text = _format_duration(self._duration_seconds, self._translator)
        self.checkbox.setToolTip(self._translator.text("include_item_tooltip"))
        self.thumbnail_label.setToolTip(self._translator.text("open_original_tooltip"))
        if self.thumbnail_label.pixmap() is None or self.thumbnail_label.pixmap().isNull():
            self.thumbnail_label.setText(self._thumbnail_placeholder())
        self.title_label.setToolTip(
            f"{self._translator.message(self._item_title)}\n"
            f"{self._translator.text('open_original_tooltip')}"
        )
        self._refresh_title_label()
        if self._uploader is None:
            self.channel_label.setText(self._translator.text("channel_unavailable"))
        self.remove_button.setToolTip(self._translator.text("remove_item_tooltip"))
        if self._unavailable:
            self.duration_label.setText(self._unavailable_text)
        elif self._progress_stage is None:
            self.duration_label.setText(self._duration_text)
        elif self._progress_stage is ProgressStage.DONE:
            self.duration_label.setText(self._translator.text("completed"))
        elif self._progress_stage is ProgressStage.FAILED:
            self.duration_label.setText(self._translator.text("download_failed"))
        elif self._progress_stage is ProgressStage.CANCELLED:
            self.duration_label.setText(self._translator.text("cancelled"))
        else:
            self.duration_label.setText(
                _progress_text(self._progress_stage, self._progress_percentage, self._translator)
            )

    def _refresh_title_label(self) -> None:
        title = html.escape(self._translator.message(self._item_title))
        webpage_url = html.escape(self._webpage_url, quote=True)
        link_color = "#000000" if self._theme.name == "day" else self._theme.accent_hover
        self.title_label.setText(
            f'<a href="{webpage_url}" style="color: {link_color};">{title}</a>'
        )

    def _thumbnail_placeholder(self) -> str:
        return (
            self._translator.text("thumbnails_disabled")
            if self.playlist
            else self._translator.text("thumbnail")
        )

    def set_selected(self, selected: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(selected and not self._unavailable)
        self.checkbox.blockSignals(False)

    def set_unavailable(self, message: str = "Não disponível") -> None:
        self._unavailable = True
        self._availability_source = message
        message = self._translator.message(message)
        self._unavailable_text = message
        self.checkbox.setEnabled(False)
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(False)
        self.checkbox.blockSignals(False)
        self._progress_percentage = None
        self._progress_stage = ProgressStage.FAILED
        self.duration_label.setText(message)
        self.update()

    def set_progress(self, percentage: float | None, stage: ProgressStage) -> None:
        self._progress_percentage = percentage
        self._progress_stage = stage
        self.duration_label.setText(_progress_text(stage, percentage, self._translator))
        self.update()

    def set_completed(self) -> None:
        self._progress_percentage = 100
        self._progress_stage = ProgressStage.DONE
        self.duration_label.setText(self._translator.text("completed"))
        self.update()

    def set_failed(self) -> None:
        self._progress_percentage = None
        self._progress_stage = ProgressStage.FAILED
        self.duration_label.setText(self._translator.text("download_failed"))
        self.update()

    def set_cancelled(self) -> None:
        self._progress_percentage = None
        self._progress_stage = ProgressStage.CANCELLED
        self.duration_label.setText(self._translator.text("cancelled"))
        self.update()

    def clear_progress(self) -> None:
        if self._unavailable:
            self._progress_percentage = None
            self._progress_stage = ProgressStage.FAILED
            self.duration_label.setText(self._unavailable_text)
            self.update()
            return
        self._progress_percentage = None
        self._progress_stage = None
        self.duration_label.setText(self._duration_text)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        base_color, progress_color = _row_colors(self._progress_stage, self._theme)
        painter.setPen(QColor(self._theme.border))
        painter.setBrush(base_color)
        painter.drawRoundedRect(bounds, 8, 8)

        if self._progress_percentage is not None:
            percentage = max(0.0, min(100.0, self._progress_percentage))
            fill_width = bounds.width() * percentage / 100
            if fill_width > 0:
                path = QPainterPath()
                path.addRoundedRect(bounds, 8, 8)
                painter.save()
                painter.setClipPath(path)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(progress_color)
                painter.drawRect(QRectF(bounds.left(), bounds.top(), fill_width, bounds.height()))
                painter.restore()

        painter.end()


def _format_duration(seconds: float | None, translator: Translator | None = None) -> str:
    translator = translator or Translator()
    if seconds is None:
        return translator.text("duration_unavailable")
    total = max(0, int(seconds))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes}:{remainder:02d}"


def _progress_text(
    stage: ProgressStage, percentage: float | None, translator: Translator | None = None
) -> str:
    translator = translator or Translator()
    labels = {
        ProgressStage.DOWNLOADING: translator.text("downloading_label"),
        ProgressStage.MERGING: translator.text("merging_label"),
        ProgressStage.CONVERTING: translator.text("converting_label"),
        ProgressStage.VALIDATING: translator.text("validating_label"),
        ProgressStage.CANCELLED: translator.text("cancelled"),
        ProgressStage.FAILED: translator.text("download_failed"),
        ProgressStage.DONE: translator.text("completed"),
    }
    label = labels.get(stage, translator.text("processing_label"))
    return f"{label} {percentage:.0f}%" if percentage is not None else f"{label}..."


def _row_colors(stage: ProgressStage | None, theme: Theme | None = None) -> tuple[QColor, QColor]:
    theme = theme or theme_for("night")
    if stage is ProgressStage.DONE:
        return QColor(theme.row_done), QColor(theme.row_done_progress)
    if stage is ProgressStage.FAILED:
        return QColor(theme.row_failed), QColor(theme.row_failed_progress)
    if stage is ProgressStage.CANCELLED:
        return QColor(theme.row_cancelled), QColor(theme.row_cancelled_progress)
    if stage is not None:
        return QColor(theme.row_processing), QColor(theme.row_progress)
    return QColor(theme.row), QColor(theme.row_progress)
