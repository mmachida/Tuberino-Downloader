"""Controles visuais compartilhados pela interface."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import QCheckBox, QComboBox

from app.theme import Theme, theme_for


class StyledComboBox(QComboBox):
    """Combo compacto com seta triangular consistente nos dois temas."""

    def paintEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        del event
        palette = self.palette()
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        background = palette.color(group, QPalette.ColorRole.Base)
        text_color = palette.color(group, QPalette.ColorRole.Text)
        border_color = palette.color(group, QPalette.ColorRole.Mid)
        if self.hasFocus():
            border_color = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(border_color)
        painter.setBrush(background)
        painter.drawRect(bounds)

        text = self.currentText() or self.placeholderText()
        painter.setPen(text_color)
        text_left = 6
        icon = self.itemIcon(self.currentIndex())
        if not icon.isNull():
            mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
            pixmap = icon.pixmap(16, 12, mode)
            painter.drawPixmap(
                int(bounds.left() + 6),
                int(bounds.center().y() - pixmap.height() / 2),
                pixmap,
            )
            text_left = 28
        text_rect = bounds.adjusted(text_left, 0, -27, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, int(text_rect.width())
            ),
        )

        separator_x = bounds.right() - 21
        painter.setPen(border_color)
        painter.drawLine(separator_x, bounds.top() + 1, separator_x, bounds.bottom() - 1)

        arrow_center_x = bounds.right() - 11
        arrow_center_y = bounds.center().y()
        arrow = QPainterPath()
        arrow.moveTo(arrow_center_x - 4, arrow_center_y - 1)
        arrow.lineTo(arrow_center_x, arrow_center_y + 3)
        arrow.lineTo(arrow_center_x + 4, arrow_center_y - 1)
        painter.setPen(text_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(arrow)
        painter.end()


class StyledCheckBox(QCheckBox):
    """Checkbox com indicador visível e consistente nos dois temas."""

    def __init__(self, theme: Theme | None = None) -> None:
        super().__init__()
        self._theme = theme or theme_for("night")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - assinatura do Qt
        del event
        enabled = self.isEnabled()
        background = QColor(self._theme.field if enabled else self._theme.panel)
        border = QColor(
            self._theme.accent
            if self.isChecked()
            else (self._theme.border if enabled else self._theme.muted_text)
        )
        fill = QColor(self._theme.accent if self.isChecked() else background)
        text_color = QColor(self._theme.text if enabled else self._theme.muted_text)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = 14
        top = (self.height() - size) / 2
        indicator = QRectF(0.5, top + 0.5, size - 1, size - 1)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(indicator, 2, 2)

        if self.isChecked():
            check = QPainterPath()
            check.moveTo(4, top + 7)
            check.lineTo(6.5, top + 10)
            check.lineTo(11.5, top + 4)
            painter.setPen(QColor("#ffffff" if enabled else self._theme.text))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(check)

        painter.setPen(text_color)
        text_rect = QRectF(size + 8, 0, max(0, self.width() - size - 8), self.height())
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text()
        )
        painter.end()
