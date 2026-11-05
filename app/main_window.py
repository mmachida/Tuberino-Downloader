"""Janela principal PySide6 do Tuberino Downloader."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.about_dialog import AboutDialog
from app.content_widgets import ContentRowWidget
from app.i18n import Translator
from app.models import (
    AppState,
    ContentCollection,
    ContentItem,
    ContentSourceKind,
    DownloadProgress,
    DownloadResult,
    FormatOption,
    OutputProfile,
    PlaylistQuality,
    ProgressStage,
    ResultStatus,
    VideoInfo,
)
from app.paths import application_root, resource_root
from app.services.app_logger import AppLogger
from app.services.dependencies import DependencyChecker, DependencyReport
from app.services.download_service import DownloadService
from app.services.file_manager import reserve_output, validate_destination
from app.services.format_selector import (
    FormatPlanningError,
    build_audio_plan,
    build_playlist_audio_plan,
    build_playlist_video_plan,
    build_video_plan,
    is_mp4_compatible_choice,
)
from app.services.output_validator import OutputValidator
from app.services.url_validator import (
    is_valid_instagram_video_url,
    is_valid_twitch_clip_url,
    is_valid_twitch_vod_url,
    is_valid_twitter_video_url,
    is_valid_youtube_playlist_url,
    is_valid_youtube_url,
    validate_youtube_url,
)
from app.services.yt_dlp_service import YtDlpService
from app.settings import AppSettings, SettingsStore
from app.settings_dialog import SettingsDialog
from app.theme import theme_for
from app.ui_controls import StyledComboBox
from app.update_dialog import UpdateDialog
from app.updates.config import UPDATER_EXECUTABLE_NAME, UpdateConfig
from app.updates.installer import InstallError, check_install_prerequisites
from app.updates.service import PreparedUpdate, ReleaseInfo, UpdateService
from app.version import APP_VERSION
from app.workers import (
    AnalysisWorker,
    DependencyWorker,
    DownloadWorker,
    PlaylistDownloadWorker,
    ThumbnailWorker,
    UpdateCheckWorker,
    UpdateDownloadWorker,
)

_LARGE_COLLECTION_THRESHOLD = 100
_COLLECTION_BATCH_SIZE = 50


class MainWindow(QMainWindow):
    """Interface base; workers e serviços são conectados em etapas posteriores."""

    close_requested = Signal()

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        self._state = AppState.IDLE
        self._video_info: VideoInfo | None = None
        self._content: ContentCollection | None = None
        self._content_rows: dict[str, ContentRowWidget] = {}
        self._content_list_items: dict[str, QListWidgetItem] = {}
        self._active_item_id: str | None = None
        self._item_progress_max: dict[str, float] = {}
        self._item_progress_stage: dict[str, ProgressStage] = {}
        self._last_result_path: Path | None = None
        self._last_error_message: str | None = None
        default_project_root = application_root()
        self._project_root = project_root or default_project_root
        self._resource_root = resource_root()
        icon_path = self._resource_root / "icon" / "logo.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._analysis_service = YtDlpService()
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._analysis_threads: set[QThread] = set()
        self._collection_population_timer: QTimer | None = None
        self._pending_collection: ContentCollection | None = None
        self._pending_collection_index = 0
        self._content_clear_timer: QTimer | None = None
        self._content_clear_total = 0
        self._playlist_thumbnails_enabled = False
        self._thumbnail_threads: set[QThread] = set()
        self._thumbnail_workers: dict[QThread, ThumbnailWorker] = {}
        self._analysis_generation = 0
        self._dependencies_report: DependencyReport | None = None
        self._dependency_thread: QThread | None = None
        self._dependency_worker: DependencyWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._update_check_thread: QThread | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_download_thread: QThread | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None
        self._update_dialog: UpdateDialog | None = None
        self._update_release: ReleaseInfo | None = None
        self._prepared_update: PreparedUpdate | None = None
        self._update_check_automatic = False
        self._update_service = UpdateService(UpdateConfig(), APP_VERSION)
        self._closing = False
        self._active_site_index = 0
        self._last_source_kind = ContentSourceKind.VIDEO
        self._default_output_directory = self._project_root / "Output"
        self._default_output_directory.mkdir(parents=True, exist_ok=True)
        self._settings_store = SettingsStore(default_destination=self._default_output_directory)
        self._settings = self._settings_store.load()
        self._translator = Translator(self._settings.language)
        self._theme = theme_for(self._settings.theme)
        self._app_logger = AppLogger(self._project_root / "logs" / "log.txt")
        self._build_ui()
        self._apply_theme()
        self._resize_to_available_screen()
        self._apply_window_preferences()
        self._connect_signals()
        self._set_state(AppState.IDLE)
        self._update_mode_controls()
        self._on_url_changed(self.url_edit.text())
        self._start_dependency_check()
        if self._settings.check_updates:
            QTimer.singleShot(1500, self._check_for_updates_automatically)

    @property
    def state(self) -> AppState:
        return self._state

    def _t(self, key: str, **values: object) -> str:
        return self._translator.text(key, **values)

    @property
    def video_info(self) -> VideoInfo | None:
        return self._video_info

    def set_video_info(
        self, info: VideoInfo, source_kind: ContentSourceKind = ContentSourceKind.VIDEO
    ) -> None:
        """Compatibilidade para preencher a lista com um vídeo único."""
        self.set_content_collection(_collection_from_video_info(info, source_kind))

    def add_video_info(
        self, info: VideoInfo, *, source_kind: ContentSourceKind = ContentSourceKind.VIDEO
    ) -> None:
        """Adiciona um vídeo analisado à fila atual de vídeos individuais."""
        if self._content is None or self._content.source_kind is not source_kind:
            self.set_video_info(info, source_kind)
            return
        if any(item.video_id == info.video_id for item in self._content.items):
            self.set_error(self._t("duplicate_video"))
            return
        item = _content_item_from_video_info(info)
        self._content = replace(self._content, items=self._content.items + (item,))
        self._add_content_row(item, playlist=False)
        self._video_info = _first_video_info(self._content.items, selected_only=True)
        self._populate_video_quality_combo(self._content.items, prefer_highest=True)
        self._populate_profile_combo(source_kind)
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in self._content.items),
                len(self._content.items),
            )
        )
        self._refresh_selection_button()
        self._update_mode_controls()
        self._set_state(AppState.READY)
        self._start_thumbnail_load(self._analysis_generation, item.thumbnail, item.video_id)

    def set_content_collection(self, collection: ContentCollection) -> None:
        self._stop_collection_population()
        source_index = self.source_kind_combo.findData(collection.source_kind)
        if source_index >= 0 and source_index != self.source_kind_combo.currentIndex():
            self.source_kind_combo.blockSignals(True)
            self.source_kind_combo.setCurrentIndex(source_index)
            self.source_kind_combo.blockSignals(False)
        self._last_source_kind = collection.source_kind
        self._update_source_action_label()
        self._content = collection
        self._content_rows.clear()
        self._content_list_items.clear()
        self._item_progress_max.clear()
        self._item_progress_stage.clear()
        self.content_list.clear()

        self._video_info = None
        if _is_single_video_source(collection.source_kind):
            self._video_info = _first_video_info(collection.items)
        self._playlist_thumbnails_enabled = (
            collection.source_kind is ContentSourceKind.PLAYLIST
            and len(collection.items) <= self._settings.playlist_thumbnail_limit
        )

        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in collection.items),
                len(collection.items),
            )
        )
        if _is_single_video_source(collection.source_kind):
            self._populate_video_quality_combo(collection.items)
        else:
            self.quality_combo.clear()
        self._populate_profile_combo(collection.source_kind)
        self._update_mode_controls()

        if (
            collection.source_kind is ContentSourceKind.PLAYLIST
            and len(collection.items) > _LARGE_COLLECTION_THRESHOLD
        ):
            self._pending_collection = collection
            self._pending_collection_index = 0
            self._set_state(AppState.ANALYZING)
            self.status_label.setText(f"{self._t('analyzing_label')} 0%")
            timer = QTimer(self)
            timer.setInterval(1)
            timer.timeout.connect(self._append_collection_chunk)
            self._collection_population_timer = timer
            timer.start()
            return

        for item in collection.items:
            self._add_content_row(
                item,
                playlist=(
                    collection.source_kind is ContentSourceKind.PLAYLIST
                    and not self._playlist_thumbnails_enabled
                ),
            )
        self._finish_content_collection(collection)

    @Slot()
    def _append_collection_chunk(self) -> None:
        collection = self._pending_collection
        if collection is None:
            self._stop_collection_population()
            return
        try:
            start = self._pending_collection_index
            end = min(start + _COLLECTION_BATCH_SIZE, len(collection.items))
            for item in collection.items[start:end]:
                self._add_content_row(item, playlist=not self._playlist_thumbnails_enabled)
            self._pending_collection_index = end
            percentage = int(end * 100 / len(collection.items))
            self.status_label.setText(f"{self._t('analyzing_label')} {percentage}%")
            if end >= len(collection.items):
                self._finish_content_collection(collection)
        except Exception as exc:
            self._stop_collection_population()
            self.clear_content()
            self.set_error(self._t("playlist_load_error"), str(exc))

    def _finish_content_collection(self, collection: ContentCollection) -> None:
        self._stop_collection_population()
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in collection.items),
                len(collection.items),
            )
        )
        self._refresh_selection_button()
        self._update_mode_controls()
        self._set_state(AppState.READY)

        if _is_single_video_source(collection.source_kind) or self._playlist_thumbnails_enabled:
            for item in collection.items:
                self._start_thumbnail_load(self._analysis_generation, item.thumbnail, item.video_id)

    def _stop_collection_population(self) -> None:
        timer = self._collection_population_timer
        self._collection_population_timer = None
        self._pending_collection = None
        self._pending_collection_index = 0
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _stop_content_clear(self) -> None:
        timer = self._content_clear_timer
        self._content_clear_timer = None
        self._content_clear_total = 0
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _add_content_row(self, item: ContentItem, *, playlist: bool) -> None:
        row = ContentRowWidget(
            item,
            playlist=playlist,
            translator=self._translator,
            theme=self._theme,
        )
        row.selected_changed.connect(self._on_item_selection_changed)
        row.remove_requested.connect(self._on_remove_item_requested)
        row.open_requested.connect(self._open_content_url)
        list_item = QListWidgetItem()
        list_item.setSizeHint(row.sizeHint())
        self.content_list.addItem(list_item)
        self.content_list.setItemWidget(list_item, row)
        self._content_rows[item.video_id] = row
        self._content_list_items[item.video_id] = list_item

    def clear_video_info(self) -> None:
        self.clear_content()

    def clear_content(self) -> None:
        self._stop_collection_population()
        self._stop_content_clear()
        self._video_info = None
        self._content = None
        self._content_rows.clear()
        self._content_list_items.clear()
        self._active_item_id = None
        self._item_progress_max.clear()
        self._item_progress_stage.clear()
        self._last_result_path = None
        self._dependencies_report = None
        self._playlist_thumbnails_enabled = False
        self.content_list.clear()
        self.content_count_label.setText(self._t("no_content"))
        self.toggle_selection_button.setEnabled(False)
        self.clear_list_button.setEnabled(False)
        self._set_state(AppState.IDLE)

    def _on_item_selection_changed(self, video_id: str, selected: bool) -> None:
        if self._content is None:
            return
        self._content = replace(
            self._content,
            items=tuple(
                replace(item, selected=selected) if item.video_id == video_id else item
                for item in self._content.items
            ),
        )
        if _is_single_video_source(self._content.source_kind):
            self._video_info = _first_video_info(self._content.items, selected_only=True)
            self._populate_video_quality_combo(self._content.items)
            self._populate_profile_combo(self._content.source_kind)
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in self._content.items),
                len(self._content.items),
            )
        )
        self._refresh_selection_button()
        self._update_mode_controls()
        self._set_state(self._state)

    def _on_remove_item_requested(self, video_id: str) -> None:
        if self._content is None:
            return
        item = next(
            (candidate for candidate in self._content.items if candidate.video_id == video_id), None
        )
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            self._t("remove_item"),
            self._t("remove_item_prompt", title=self._translator.message(item.title)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        remaining = tuple(
            candidate for candidate in self._content.items if candidate.video_id != video_id
        )
        if not remaining:
            self.clear_content()
            return

        row = self._content_rows.pop(video_id, None)
        list_item = self._content_list_items.pop(video_id, None)
        if row is not None:
            row.deleteLater()
        if list_item is not None:
            row_index = self.content_list.row(list_item)
            if row_index >= 0:
                self.content_list.takeItem(row_index)
        self._content = replace(self._content, items=remaining)
        if _is_single_video_source(self._content.source_kind):
            self._video_info = _first_video_info(remaining, selected_only=True)
            self._populate_video_quality_combo(remaining)
        self._populate_profile_combo(self._content.source_kind)
        self._active_item_id = None
        self._last_result_path = None
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in remaining),
                len(remaining),
            )
        )
        self._refresh_selection_button()
        self._set_state(AppState.READY)

    @Slot(str)
    def _open_content_url(self, video_id: str) -> None:
        if self._content is None:
            return
        item = next(
            (candidate for candidate in self._content.items if candidate.video_id == video_id),
            None,
        )
        if item is None:
            return
        url = QUrl(item.webpage_url)
        if url.isValid() and url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)

    def _clear_content_with_confirmation(self) -> None:
        if self._confirm_clear_content(self._t("clear_list_prompt")):
            self._clear_content_smoothly()

    def _confirm_clear_content(self, reason: str) -> bool:
        if self._content is None or not self._content.items:
            return True
        count = len(self._content.items)
        item_label = self._t("item" if count == 1 else "items")
        answer = QMessageBox.question(
            self,
            self._t("clear_list_title"),
            f"{reason}\n\n{self._t('list_count_prompt', count=count, item_label=item_label)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _clear_content_smoothly(self) -> None:
        if self._content_clear_timer is not None:
            return
        if self.content_list.count() <= _LARGE_COLLECTION_THRESHOLD:
            self.clear_content()
            return

        self._stop_collection_population()
        self._video_info = None
        self._content = None
        self._content_rows.clear()
        self._content_list_items.clear()
        self._active_item_id = None
        self._item_progress_max.clear()
        self._item_progress_stage.clear()
        self._last_result_path = None
        self._dependencies_report = None
        self._playlist_thumbnails_enabled = False
        self._content_clear_total = self.content_list.count()
        self._set_state(AppState.ANALYZING)
        self.cancel_button.setEnabled(False)
        self.content_count_label.setText(self._t("list_clearing"))
        self.status_label.setText(f"{self._t('clear_progress')} 0%")

        timer = QTimer(self)
        timer.setInterval(1)
        timer.timeout.connect(self._clear_content_chunk)
        self._content_clear_timer = timer
        timer.start()

    @Slot()
    def _clear_content_chunk(self) -> None:
        if self._content_clear_timer is None:
            return
        try:
            for _ in range(min(_COLLECTION_BATCH_SIZE, self.content_list.count())):
                index = self.content_list.count() - 1
                list_item = self.content_list.item(index)
                row = self.content_list.itemWidget(list_item)
                if row is not None:
                    row.deleteLater()
                self.content_list.takeItem(index)
            remaining = self.content_list.count()
            cleared = self._content_clear_total - remaining
            percentage = (
                100
                if self._content_clear_total == 0
                else int(cleared * 100 / self._content_clear_total)
            )
            self.status_label.setText(f"{self._t('clear_progress')} {percentage}%")
            if remaining == 0:
                self._finish_content_clear()
        except Exception as exc:
            self._stop_content_clear()
            self.content_list.clear()
            self.content_count_label.setText(self._t("no_content"))
            self.toggle_selection_button.setEnabled(False)
            self.clear_list_button.setEnabled(False)
            self.set_error(self._t("list_clearing_error"), str(exc))

    def _finish_content_clear(self) -> None:
        self._stop_content_clear()
        self.content_count_label.setText(self._t("no_content"))
        self.toggle_selection_button.setEnabled(False)
        self.clear_list_button.setEnabled(False)
        self._set_state(AppState.IDLE)

    def _refresh_selection_button(self) -> None:
        if self._content is None:
            self.toggle_selection_button.setText(self._t("activate_all"))
            self.toggle_selection_button.setEnabled(False)
            self.clear_list_button.setEnabled(False)
            return
        selectable_items = tuple(item for item in self._content.items if item.available)
        all_selected = bool(selectable_items) and all(item.selected for item in selectable_items)
        self.toggle_selection_button.setText(
            self._t("deactivate_all" if all_selected else "activate_all")
        )
        self.toggle_selection_button.setEnabled(bool(selectable_items))
        self.clear_list_button.setEnabled(bool(self._content.items))

    def _toggle_all_items(self) -> None:
        if self._content is None:
            return
        selectable_items = tuple(item for item in self._content.items if item.available)
        if not selectable_items:
            return
        activate = not all(item.selected for item in selectable_items)
        self._content = replace(
            self._content,
            items=tuple(
                replace(item, selected=activate if item.available else False)
                for item in self._content.items
            ),
        )
        if _is_single_video_source(self._content.source_kind):
            self._video_info = _first_video_info(self._content.items, selected_only=True)
            self._populate_video_quality_combo(self._content.items)
            self._populate_profile_combo(self._content.source_kind)
        for item in self._content.items:
            row = self._content_rows.get(item.video_id)
            if row is not None:
                row.set_selected(item.selected)
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in self._content.items),
                len(self._content.items),
            )
        )
        self._refresh_selection_button()
        self._update_mode_controls()
        self._set_state(self._state)

    def _has_selected_content(self) -> bool:
        return self._content is not None and bool(self._content.selected_items)

    def set_error(self, message: str, technical_detail: str | None = None) -> None:
        del technical_detail
        self._set_state(AppState.ERROR)
        self._last_error_message = message
        localized = self._translator.message(message)
        self.status_label.setText(localized)
        self._app_logger.error(localized)

    def set_download_complete(self, path: Path) -> None:
        self._last_error_message = None
        self._last_result_path = path
        self.status_label.setText(self._t("completed_file", name=path.name))
        self._set_state(AppState.SUCCESS)

    def _build_ui(self) -> None:
        self.setWindowTitle(self._t("app_title"))
        self.setMinimumSize(720, 560)
        self.resize(860, 600)
        self._build_menu_bar()

        self.site_tabs = QTabWidget(self)
        self.site_tabs.setObjectName("siteTabs")
        self.site_tabs.setDocumentMode(True)
        self.site_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.site_tabs.setMovable(False)
        self.site_tabs.setStyleSheet(self._theme.tabs_stylesheet())

        youtube_page = QWidget()
        twitch_page = QWidget()
        twitter_page = QWidget()
        instagram_page = QWidget()
        self.youtube_page = youtube_page
        self.twitch_page = twitch_page
        self.twitter_page = twitter_page
        self.instagram_page = instagram_page
        self.site_tabs.addTab(youtube_page, self._t("youtube"))
        self.site_tabs.addTab(twitch_page, self._t("twitch"))
        self.site_tabs.addTab(twitter_page, self._t("twitter_x"))
        self.site_tabs.addTab(instagram_page, self._t("instagram"))
        self.setCentralWidget(self.site_tabs)
        self._page_layouts = {
            youtube_page: QVBoxLayout(youtube_page),
            twitch_page: QVBoxLayout(twitch_page),
            twitter_page: QVBoxLayout(twitter_page),
            instagram_page: QVBoxLayout(instagram_page),
        }
        for page_layout in self._page_layouts.values():
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)
        self._page_separators = {}
        for page, page_layout in self._page_layouts.items():
            separator = QFrame(page)
            separator.setObjectName("siteSeparator")
            separator.setFrameShape(QFrame.Shape.NoFrame)
            separator.setFixedHeight(1)
            page_layout.addWidget(separator)
            self._page_separators[page] = separator
        self._workspace = QWidget()
        self._page_layouts[youtube_page].addWidget(self._workspace)
        layout = QVBoxLayout(self._workspace)
        layout.setContentsMargins(18, 4, 18, 18)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.page_title = QLabel(self._t("youtube"))
        self.page_title.setObjectName("windowTitle")
        self.page_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(self.page_title)
        header.addStretch()
        layout.addLayout(header)

        url_row = QHBoxLayout()
        self.source_kind_combo = StyledComboBox()
        self.source_kind_combo.addItem(self._t("video"), ContentSourceKind.VIDEO)
        self.source_kind_combo.addItem(self._t("playlist"), ContentSourceKind.PLAYLIST)
        self.source_kind_combo.setMinimumWidth(92)
        self.source_kind_combo.setToolTip(self._t("choose_source_tooltip"))
        self.add_label = QLabel(self._t("add_label"))
        url_row.addWidget(self.add_label)
        url_row.addWidget(self.source_kind_combo)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(self._t("video_url_placeholder"))
        self.url_edit.setClearButtonEnabled(True)
        self.analyze_button = QPushButton(self._t("add"))
        self.analyze_button.setDefault(True)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.analyze_button)
        layout.addLayout(url_row)

        self.content_group = QGroupBox(self._t("content"))
        content_layout = QVBoxLayout(self.content_group)
        content_header = QHBoxLayout()
        self.content_count_label = QLabel(self._t("no_content"))
        self.toggle_selection_button = QPushButton(self._t("activate_all"))
        self.clear_list_button = QPushButton(self._t("clear_list"))
        self.toggle_selection_button.setEnabled(False)
        self.clear_list_button.setEnabled(False)
        content_header.addWidget(self.content_count_label)
        content_header.addStretch()
        content_header.addWidget(self.toggle_selection_button)
        content_header.addWidget(self.clear_list_button)
        content_layout.addLayout(content_header)
        self.content_list = QListWidget()
        self.content_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.content_list.setUniformItemSizes(True)
        self.content_list.setSpacing(2)
        self.content_list.setMinimumHeight(150)
        content_layout.addWidget(self.content_list, 1)
        layout.addWidget(self.content_group, 1)

        self.options_group = QGroupBox(self._t("output_options"))
        self.options_form = QFormLayout(self.options_group)
        form = self.options_form
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)
        self.video_radio = QRadioButton(self._t("video"))
        self.mp3_radio = QRadioButton(self._t("mp3"))
        self.video_radio.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(10)
        self.video_radio.setMinimumWidth(76)
        self.mp3_radio.setMinimumWidth(52)
        mode_row.addWidget(self.video_radio)
        mode_row.addWidget(self.mp3_radio)
        mode_row.addStretch()
        self.type_label = QLabel(self._t("type"))
        form.addRow(self.type_label, mode_row)

        self.video_quality_label = QLabel(self._t("quality"))
        self.quality_combo = StyledComboBox()
        self.quality_combo.setPlaceholderText(self._t("quality_placeholder"))
        form.addRow(self.video_quality_label, self.quality_combo)

        self.playlist_quality_label = QLabel(self._t("quality"))
        self.playlist_quality_combo = StyledComboBox()
        self.playlist_quality_combo.addItem(self._t("best_quality"), PlaylistQuality.BEST)
        self.playlist_quality_combo.addItem(self._t("worst_quality"), PlaylistQuality.WORST)
        form.addRow(self.playlist_quality_label, self.playlist_quality_combo)

        self.profile_label = QLabel(self._t("container"))
        self.profile_combo = StyledComboBox()
        self.profile_combo.setToolTip(self._t("mp4_tooltip"))
        form.addRow(self.profile_label, self.profile_combo)

        self.bitrate_label = QLabel(self._t("mp3_bitrate"))
        self.bitrate_combo = StyledComboBox()
        for bitrate in (128, 192, 320):
            self.bitrate_combo.addItem(f"{bitrate} kbps", bitrate)
        self.bitrate_combo.setCurrentIndex({128: 0, 192: 1, 320: 2}[self._settings.mp3_bitrate])
        self.bitrate_combo.setToolTip(self._t("bitrate_tooltip"))
        form.addRow(self.bitrate_label, self.bitrate_combo)
        for label in (
            self.type_label,
            self.video_quality_label,
            self.playlist_quality_label,
            self.profile_label,
            self.bitrate_label,
        ):
            label.setFixedWidth(112)
        self.options_group.setFixedHeight(120)
        layout.addWidget(self.options_group)

        destination_row = QHBoxLayout()
        self.destination_edit = QLineEdit(
            str(self._settings.destination or self._default_output_directory)
        )
        self.destination_edit.setToolTip(self._t("destination_tooltip"))
        self.browse_button = QPushButton(self._t("browse"))
        self.open_folder_button = QPushButton(self._t("open_folder"))
        destination_row.addWidget(self.destination_edit, 1)
        destination_row.addWidget(self.browse_button)
        destination_row.addWidget(self.open_folder_button)
        destination_form = QFormLayout()
        self.destination_label = QLabel(self._t("destination"))
        destination_form.addRow(self.destination_label, destination_row)
        layout.addLayout(destination_form)

        actions = QHBoxLayout()
        self.download_button = QPushButton(self._t("download"))
        self.download_button.setDefault(True)
        self.cancel_button = QPushButton(self._t("cancel"))
        actions.addWidget(self.download_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        layout.addLayout(actions)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel(self._t("ready"))
        footer.addWidget(self.status_label)
        footer.addStretch()
        version_number = APP_VERSION.rsplit(".", 1)[0]
        self.version_label = QLabel(f"v{version_number}")
        self.version_label.setObjectName("versionLabel")
        footer.addWidget(self.version_label)
        layout.addLayout(footer)

        # Vídeo é a configuração inicial; MP3 precisa ser escolhido na sessão.
        self.video_radio.setChecked(True)
        self.mp3_radio.setChecked(False)
        self._populate_profile_combo(ContentSourceKind.VIDEO)

    def _retranslate_ui(self) -> None:
        """Atualiza a interface inteira depois da troca de idioma."""
        self.setWindowTitle(self._t("app_title"))
        self.site_tabs.setTabText(0, self._t("youtube"))
        self.site_tabs.setTabText(1, self._t("twitch"))
        self.site_tabs.setTabText(2, self._t("twitter_x"))
        self.site_tabs.setTabText(3, self._t("instagram"))
        self.page_title.setText(self._t(self._current_site_key()))
        self.add_label.setText(self._t("add_label"))
        self.source_kind_combo.setToolTip(self._t("choose_source_tooltip"))
        for index in range(self.source_kind_combo.count()):
            source_kind = _coerce_source_kind(self.source_kind_combo.itemData(index))
            key = {
                ContentSourceKind.VIDEO: "video",
                ContentSourceKind.PLAYLIST: "playlist",
                ContentSourceKind.TWITCH_VOD: "vod",
                ContentSourceKind.TWITCH_CLIP: "clip",
                ContentSourceKind.TWITTER_VIDEO: "video",
                ContentSourceKind.INSTAGRAM_VIDEO: "video",
            }[source_kind]
            self.source_kind_combo.setItemText(index, self._t(key))
        self._update_url_placeholder()
        self._update_source_action_label()

        self.content_group.setTitle(self._t("content"))
        self.content_count_label.setText(self._content_count_label_text())
        self._refresh_selection_button()
        self.clear_list_button.setText(self._t("clear_list"))
        self.options_group.setTitle(self._t("output_options"))
        self.type_label.setText(self._t("type"))
        self.video_radio.setText(self._t("video"))
        self.mp3_radio.setText(self._t("mp3"))
        self.video_quality_label.setText(self._t("quality"))
        self.playlist_quality_label.setText(self._t("quality"))
        self.quality_combo.setPlaceholderText(self._t("quality_placeholder"))
        for index in range(self.playlist_quality_combo.count()):
            quality = self.playlist_quality_combo.itemData(index)
            label = "best_quality" if quality is PlaylistQuality.BEST else "worst_quality"
            self.playlist_quality_combo.setItemText(index, self._t(label))
        for index in range(self.quality_combo.count()):
            option = self.quality_combo.itemData(index)
            if isinstance(option, FormatOption):
                self.quality_combo.setItemText(index, self._quality_option_label(option))
        self.profile_label.setText(self._t("container"))
        self.profile_combo.setToolTip(self._t("mp4_tooltip"))
        self._populate_profile_combo(self._current_source_kind())
        self.bitrate_label.setText(self._t("mp3_bitrate"))
        self.bitrate_combo.setToolTip(self._t("bitrate_tooltip"))
        self.destination_label.setText(self._t("destination"))
        self.destination_edit.setToolTip(self._t("destination_tooltip"))
        self.browse_button.setText(self._t("browse"))
        self.open_folder_button.setText(self._t("open_folder"))
        self.download_button.setText(self._t("download"))
        self.cancel_button.setText(self._t("cancel"))

        self.file_menu.setTitle(self._t("file"))
        self.open_folder_action.setText(self._t("open_folder"))
        self.exit_action.setText(self._t("exit"))
        self.options_menu.setTitle(self._t("options"))
        self.settings_action.setText(self._t("settings"))
        self.about_menu.setTitle(self._t("about"))
        self.about_action.setText(self._t("about"))
        self.check_updates_action.setText(self._t("check_updates"))
        self.support_button.setText(self._t("support"))
        self.support_button.setToolTip(self._t("support_tooltip"))
        if self._update_dialog is not None:
            self._update_dialog.set_translator(self._translator)
        for row in self._content_rows.values():
            row.set_language(self._translator)

        if self._state is AppState.ERROR and self._last_error_message:
            self.status_label.setText(self._translator.message(self._last_error_message))
        elif self._state is AppState.SUCCESS and self._last_result_path is not None:
            self.status_label.setText(self._t("completed_file", name=self._last_result_path.name))
        else:
            self._set_state(self._state)

    def _content_count_label_text(self) -> str:
        if self._content is None:
            return self._t("no_content")
        return self._translator.content_count(
            sum(item.selected and item.available for item in self._content.items),
            len(self._content.items),
        )

    def _quality_option_label(self, option: FormatOption) -> str:
        label = (
            self._translator.message(option.label) if option.label else self._t("video_available")
        )
        format_label = (option.ext or self._t("unknown_format")).upper()
        return f"{label} • {format_label}"

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        menu_bar.setStyleSheet(self._theme.menu_stylesheet())

        self.file_menu = menu_bar.addMenu(self._t("file"))
        self.open_folder_action = self.file_menu.addAction(self._t("open_folder"))
        self.open_folder_action.triggered.connect(self._open_folder)
        self.file_menu.addSeparator()
        self.exit_action = self.file_menu.addAction(self._t("exit"))
        self.exit_action.triggered.connect(self.close)

        self.options_menu = menu_bar.addMenu(self._t("options"))
        self.settings_action = self.options_menu.addAction(self._t("settings"))
        self.settings_action.triggered.connect(self._show_settings)
        self.about_menu = menu_bar.addMenu(self._t("about"))
        self.about_action = self.about_menu.addAction(self._t("about"))
        self.about_action.triggered.connect(self._show_about)
        self.check_updates_action = self.about_menu.addAction(self._t("check_updates"))
        self.check_updates_action.triggered.connect(self._check_for_updates)

        self.support_button = QPushButton(self._t("support"))
        self.support_button.setFlat(True)
        self.support_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.support_button.setToolTip(self._t("support_tooltip"))
        self.support_button.clicked.connect(self._show_support)
        menu_bar.setCornerWidget(self.support_button, Qt.Corner.TopRightCorner)

    def _connect_signals(self) -> None:
        self.site_tabs.currentChanged.connect(self._on_site_tab_changed)
        self.url_edit.textChanged.connect(self._on_url_changed)
        self.source_kind_combo.currentIndexChanged.connect(self._on_source_kind_changed)
        self.video_radio.toggled.connect(self._update_mode_controls)
        self.mp3_radio.toggled.connect(self._update_mode_controls)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        self.toggle_selection_button.clicked.connect(self._toggle_all_items)
        self.browse_button.clicked.connect(self._choose_destination)
        self.analyze_button.clicked.connect(self._start_analysis)
        self.download_button.clicked.connect(self._start_download)
        self.clear_list_button.clicked.connect(self._clear_content_with_confirmation)
        self.cancel_button.clicked.connect(self._cancel_active_task)
        self.open_folder_button.clicked.connect(self._open_folder)

    def _current_source_kind(self) -> ContentSourceKind:
        return _coerce_source_kind(self.source_kind_combo.currentData())

    def _is_twitch_site(self) -> bool:
        return self.site_tabs.currentWidget() is self.twitch_page

    def _is_twitter_site(self) -> bool:
        return self.site_tabs.currentWidget() is self.twitter_page

    def _is_instagram_site(self) -> bool:
        return self.site_tabs.currentWidget() is self.instagram_page

    def _current_site_key(self) -> str:
        if self._is_twitch_site():
            return "twitch"
        if self._is_twitter_site():
            return "twitter_x"
        if self._is_instagram_site():
            return "instagram"
        return "youtube"

    def _on_site_tab_changed(self, index: int) -> None:
        if self._has_running_task():
            self.site_tabs.blockSignals(True)
            self.site_tabs.setCurrentIndex(self._active_site_index)
            self.site_tabs.blockSignals(False)
            return

        if not self._confirm_clear_content(self._t("switch_platform_prompt")):
            self.site_tabs.blockSignals(True)
            self.site_tabs.setCurrentIndex(self._active_site_index)
            self.site_tabs.blockSignals(False)
            return

        pages = (self.youtube_page, self.twitch_page, self.twitter_page, self.instagram_page)
        if not 0 <= index < len(pages):
            return
        page = pages[index]
        old_page = self._workspace.parentWidget()
        if old_page is not page:
            old_layout = self._page_layouts.get(old_page)
            if old_layout is not None:
                old_layout.removeWidget(self._workspace)
            self._workspace.setParent(page)
            self._page_layouts[page].addWidget(self._workspace)
            self._workspace.show()

        self.clear_content()
        self.page_title.setText(self._t(self._current_site_key()))
        self._set_source_options_for_site()
        self.url_edit.clear()
        self._active_site_index = index

    def _set_source_options_for_site(self) -> None:
        self.source_kind_combo.blockSignals(True)
        self.source_kind_combo.clear()
        if self._is_twitch_site():
            self.source_kind_combo.addItem(self._t("vod"), ContentSourceKind.TWITCH_VOD)
            self.source_kind_combo.addItem(self._t("clip"), ContentSourceKind.TWITCH_CLIP)
        elif self._is_twitter_site():
            self.source_kind_combo.addItem(self._t("video"), ContentSourceKind.TWITTER_VIDEO)
        elif self._is_instagram_site():
            self.source_kind_combo.addItem(self._t("video"), ContentSourceKind.INSTAGRAM_VIDEO)
        else:
            self.source_kind_combo.addItem(self._t("video"), ContentSourceKind.VIDEO)
            self.source_kind_combo.addItem(self._t("playlist"), ContentSourceKind.PLAYLIST)
        self.source_kind_combo.setCurrentIndex(0)
        self.source_kind_combo.blockSignals(False)
        self._last_source_kind = self._current_source_kind()
        self._update_source_action_label()
        self._update_url_placeholder()
        self._populate_profile_combo(self._current_source_kind())
        self._update_mode_controls()

    def _update_url_placeholder(self) -> None:
        source_kind = self._current_source_kind()
        if source_kind is ContentSourceKind.PLAYLIST:
            placeholder = self._t("playlist_url_placeholder")
        elif source_kind is ContentSourceKind.TWITCH_VOD:
            placeholder = self._t("vod_url_placeholder")
        elif source_kind is ContentSourceKind.TWITCH_CLIP:
            placeholder = self._t("clip_url_placeholder")
        elif source_kind is ContentSourceKind.TWITTER_VIDEO:
            placeholder = self._t("twitter_url_placeholder")
        elif source_kind is ContentSourceKind.INSTAGRAM_VIDEO:
            placeholder = self._t("instagram_url_placeholder")
        else:
            placeholder = self._t("video_url_placeholder")
        self.url_edit.setPlaceholderText(placeholder)

    def _populate_profile_combo(self, source_kind: ContentSourceKind) -> None:
        previous = self.profile_combo.currentData() if self.profile_combo.count() else None
        aggregate_video = source_kind is ContentSourceKind.PLAYLIST or (
            _is_single_video_source(source_kind)
            and self._content is not None
            and len(self._content.selected_items) > 1
        )
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        if aggregate_video:
            self.profile_combo.addItem(self._t("original_format"), OutputProfile.ORIGINAL)
            self.profile_combo.addItem(self._t("convert_mp4"), OutputProfile.CONVERT_MP4)
        else:
            self.profile_combo.addItem(self._t("mp4_compatible"), OutputProfile.MP4_COMPATIBLE)
            self.profile_combo.addItem(self._t("original_format"), OutputProfile.ORIGINAL)
            self.profile_combo.addItem(self._t("convert_mp4"), OutputProfile.CONVERT_MP4)
        if isinstance(previous, str):
            for index in range(self.profile_combo.count()):
                if self.profile_combo.itemData(index) == previous:
                    self.profile_combo.setCurrentIndex(index)
                    break
        self.profile_combo.blockSignals(False)
        self._update_mp4_profile_availability()

    def _update_mp4_profile_availability(self) -> None:
        profile_index = self.profile_combo.findData(OutputProfile.MP4_COMPATIBLE)
        if profile_index < 0:
            return

        available = True
        if self._video_info is not None:
            quality = self.quality_combo.currentData()
            available = isinstance(quality, FormatOption) and is_mp4_compatible_choice(
                self._video_info, quality
            )

        model_item = self.profile_combo.model().item(profile_index)
        if model_item is not None:
            model_item.setEnabled(available)
            model_item.setData(
                QColor(self._theme.text if available else self._theme.muted_text),
                Qt.ItemDataRole.ForegroundRole,
            )
            model_item.setToolTip(
                self._t("mp4_available") if available else self._t("mp4_unavailable")
            )

        current_profile = _coerce_output_profile(self.profile_combo.currentData())
        if not available and current_profile is OutputProfile.MP4_COMPATIBLE:
            fallback_index = self.profile_combo.findData(OutputProfile.ORIGINAL)
            if fallback_index >= 0:
                self.profile_combo.setCurrentIndex(fallback_index)

    @Slot(int)
    def _on_quality_changed(self, _index: int) -> None:
        self._update_mp4_profile_availability()

    def _on_source_kind_changed(self) -> None:
        source_kind = self._current_source_kind()
        if not self._confirm_clear_content(self._t("switch_content_prompt")):
            previous_index = self.source_kind_combo.findData(self._last_source_kind)
            if previous_index >= 0:
                self.source_kind_combo.blockSignals(True)
                self.source_kind_combo.setCurrentIndex(previous_index)
                self.source_kind_combo.blockSignals(False)
            return

        self.clear_content()
        self._last_source_kind = source_kind
        self._update_source_action_label()
        self._update_url_placeholder()
        self._populate_profile_combo(self._current_source_kind())
        self._update_mode_controls()
        self._on_url_changed(self.url_edit.text())

    def _on_url_changed(self, value: str) -> None:
        self._analysis_generation += 1
        if self._state is AppState.ANALYZING:
            self._set_state(AppState.IDLE)
        elif self._state in {AppState.ERROR, AppState.CANCELLED, AppState.SUCCESS}:
            self._set_state(AppState.IDLE)
        self.analyze_button.setEnabled(self._is_valid_source_url(value))

    def _update_source_action_label(self) -> None:
        self.analyze_button.setText(
            self._t("analyze")
            if self._current_source_kind() is ContentSourceKind.PLAYLIST
            else self._t("add")
        )

    def _populate_video_quality_combo(
        self, items: tuple[ContentItem, ...], *, prefer_highest: bool = False
    ) -> None:
        previous = None if prefer_highest else self.quality_combo.currentData()
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        selected_items = tuple(item for item in items if item.selected and item.available)
        candidates = selected_items or tuple(item for item in items if item.available)
        source_item = next((item for item in candidates if item.formats), None)
        if source_item is not None:
            for option in source_item.as_video_info().video_options:
                self.quality_combo.addItem(self._quality_option_label(option), option)
        if isinstance(previous, FormatOption):
            for index in range(self.quality_combo.count()):
                candidate = self.quality_combo.itemData(index)
                if (
                    isinstance(candidate, FormatOption)
                    and candidate.format_id == previous.format_id
                ):
                    self.quality_combo.setCurrentIndex(index)
                    break
        if self.quality_combo.count() and self.quality_combo.currentIndex() < 0:
            self.quality_combo.setCurrentIndex(0)
        self.quality_combo.blockSignals(False)

    def _uses_aggregate_video_options(self) -> bool:
        if self._current_source_kind() is ContentSourceKind.PLAYLIST:
            return True
        return self._content is not None and len(self._content.selected_items) > 1

    def _is_valid_source_url(self, value: str) -> bool:
        source_kind = self._current_source_kind()
        if source_kind is ContentSourceKind.PLAYLIST:
            return is_valid_youtube_playlist_url(value)
        if source_kind is ContentSourceKind.TWITCH_VOD:
            return is_valid_twitch_vod_url(value)
        if source_kind is ContentSourceKind.TWITCH_CLIP:
            return is_valid_twitch_clip_url(value)
        if source_kind is ContentSourceKind.TWITTER_VIDEO:
            return is_valid_twitter_video_url(value)
        if source_kind is ContentSourceKind.INSTAGRAM_VIDEO:
            return is_valid_instagram_video_url(value)
        return is_valid_youtube_url(value)

    def _update_mode_controls(self) -> None:
        video_mode = self.video_radio.isChecked()
        aggregate_video = self._uses_aggregate_video_options()
        self.options_form.setRowVisible(
            self.video_quality_label,
            video_mode and not aggregate_video,
        )
        self.options_form.setRowVisible(
            self.playlist_quality_label,
            video_mode and aggregate_video,
        )
        self.options_form.setRowVisible(self.profile_label, video_mode)
        self.options_form.setRowVisible(self.bitrate_label, not video_mode)
        if self._state in {AppState.READY, AppState.ERROR, AppState.CANCELLED, AppState.SUCCESS}:
            self.download_button.setEnabled(self._has_selected_content())

    def _set_state(self, state: AppState) -> None:
        self._state = state
        busy = state in {
            AppState.ANALYZING,
            AppState.DOWNLOADING,
            AppState.POSTPROCESSING,
            AppState.VALIDATING,
        }
        self.analyze_button.setEnabled(not busy and self._is_valid_source_url(self.url_edit.text()))
        self.url_edit.setEnabled(not busy)
        self.cancel_button.setEnabled(
            state
            in {
                AppState.ANALYZING,
                AppState.DOWNLOADING,
                AppState.POSTPROCESSING,
                AppState.VALIDATING,
            }
        )
        controls_locked = state in {
            AppState.ANALYZING,
            AppState.DOWNLOADING,
            AppState.POSTPROCESSING,
            AppState.VALIDATING,
        }
        for control in (
            self.video_radio,
            self.mp3_radio,
            self.quality_combo,
            self.playlist_quality_combo,
            self.profile_combo,
            self.bitrate_combo,
            self.destination_edit,
            self.browse_button,
            self.source_kind_combo,
            self.content_list,
            self.toggle_selection_button,
            self.clear_list_button,
        ):
            control.setEnabled(not controls_locked)
        has_content = self._content is not None and bool(self._content.items)
        has_selectable_content = has_content and any(item.available for item in self._content.items)
        self.toggle_selection_button.setEnabled(not controls_locked and has_selectable_content)
        self.clear_list_button.setEnabled(not controls_locked and has_content)
        self.download_button.setEnabled(
            state in {AppState.READY, AppState.ERROR, AppState.CANCELLED, AppState.SUCCESS}
            and self._has_selected_content()
        )
        self.open_folder_button.setEnabled(not controls_locked)
        self.open_folder_action.setEnabled(not controls_locked)
        if state is AppState.IDLE:
            self.status_label.setText(self._t("ready"))
        elif state is AppState.ANALYZING:
            self.status_label.setText(self._t("analyzing_content"))
        elif state is AppState.READY:
            self.status_label.setText(self._t("ready_to_download"))
        elif state is AppState.DOWNLOADING:
            self.status_label.setText(self._t("downloading"))
        elif state is AppState.POSTPROCESSING:
            self.status_label.setText(self._t("converting"))
        elif state is AppState.VALIDATING:
            self.status_label.setText(self._t("validating"))

    def _start_analysis(self) -> None:
        url = self.url_edit.text().strip()
        if not self._is_valid_source_url(url):
            source_kind = self._current_source_kind()
            if source_kind is ContentSourceKind.PLAYLIST:
                message = self._t("invalid_playlist_url")
            elif source_kind is ContentSourceKind.TWITCH_VOD:
                message = self._t("invalid_vod_url")
            elif source_kind is ContentSourceKind.TWITCH_CLIP:
                message = self._t("invalid_clip_url")
            elif source_kind is ContentSourceKind.TWITTER_VIDEO:
                message = self._t("invalid_twitter_url")
            elif source_kind is ContentSourceKind.INSTAGRAM_VIDEO:
                message = self._t("invalid_instagram_url")
            else:
                message = self._t("invalid_video_url")
            self.set_error(message)
            return
        self._analysis_generation += 1
        generation = self._analysis_generation
        source_kind = self._current_source_kind()
        if source_kind is ContentSourceKind.PLAYLIST:
            if not self._confirm_clear_content(self._t("replace_playlist_prompt")):
                return
            self.clear_content()
        self._set_state(AppState.ANALYZING)
        if source_kind is ContentSourceKind.PLAYLIST:
            self.status_label.setText(f"{self._t('analyzing_label')} 0%")
        thread = QThread(self)
        worker = AnalysisWorker(
            self._analysis_service,
            url,
            DependencyChecker(self._project_root, vendor_root=self._resource_root / "vendor"),
            source_kind=source_kind,
            generation=generation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.dependencies_ready.connect(self._set_dependencies)
        worker.progress.connect(self._receive_analysis_progress)
        worker.result_ready.connect(self._receive_analysis_result)
        worker.failed.connect(self._receive_analysis_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._analysis_finished)
        self._analysis_thread = thread
        self._analysis_worker = worker
        self._analysis_threads.add(thread)
        thread.start()

    def _handle_analysis_result(
        self, generation: int, result: VideoInfo | ContentCollection
    ) -> None:
        if generation != self._analysis_generation:
            return
        if isinstance(result, VideoInfo) and not result.video_options:
            self.set_error(self._t("no_quality"))
            return
        if isinstance(result, VideoInfo):
            self.add_video_info(result, source_kind=self._current_source_kind())
        elif isinstance(result, ContentCollection):
            self.set_content_collection(result)
        else:
            self.set_error(self._t("unrecognized_content"))

    def _set_dependencies(self, report: DependencyReport) -> None:
        self._dependencies_report = report

    def _start_dependency_check(self) -> None:
        thread = QThread(self)
        worker = DependencyWorker(
            DependencyChecker(self._project_root, vendor_root=self._resource_root / "vendor")
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result_ready.connect(self._set_dependencies)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._dependency_finished)
        self._dependency_thread = thread
        self._dependency_worker = worker
        thread.start()

    @Slot()
    def _dependency_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        if self._dependency_thread is thread:
            self._dependency_thread = None
            self._dependency_worker = None
        self._close_when_idle()

    @Slot(object)
    def _receive_analysis_result(self, result: VideoInfo | ContentCollection) -> None:
        worker = self.sender()
        generation = getattr(worker, "generation", None)
        if not isinstance(generation, int):
            generation = self._analysis_generation
        self._handle_analysis_result(generation, result)

    @Slot(int, int)
    def _receive_analysis_progress(self, processed: int, total: int) -> None:
        worker = self.sender()
        generation = getattr(worker, "generation", None)
        if isinstance(generation, int) and generation != self._analysis_generation:
            return
        percentage = 100 if total <= 0 else int(processed * 100 / total)
        self.status_label.setText(f"{self._t('analyzing_label')} {max(0, min(100, percentage))}%")

    @Slot(str, str)
    def _receive_analysis_error(self, message: str, detail: str) -> None:
        worker = self.sender()
        generation = getattr(worker, "generation", None)
        if not isinstance(generation, int):
            generation = self._analysis_generation
        self._handle_analysis_error(generation, message, detail)

    def _handle_analysis_error(self, generation: int, message: str, detail: str) -> None:
        if generation != self._analysis_generation:
            return
        if (
            self._current_source_kind() is ContentSourceKind.VIDEO
            and _looks_like_unavailable(message, detail)
            and self._add_unavailable_video(self.url_edit.text())
        ):
            self._last_error_message = "Vídeo não disponível."
            self.status_label.setText(self._t("video_unavailable"))
            self._app_logger.error(self._t("video_unavailable"))
            return
        self.set_error(message, detail or None)

    def _add_unavailable_video(self, raw_url: str) -> bool:
        validation = validate_youtube_url(raw_url)
        if not validation.valid or validation.video_id is None:
            return False
        item = ContentItem(
            video_id=validation.video_id,
            webpage_url=validation.normalized_url or raw_url.strip(),
            title="Vídeo não disponível",
            selected=False,
            available=False,
            availability_error="Não disponível",
        )
        if self._content is None or self._content.source_kind is not ContentSourceKind.VIDEO:
            self.set_content_collection(
                ContentCollection(
                    ContentSourceKind.VIDEO,
                    item.webpage_url,
                    item.title,
                    (item,),
                )
            )
            return True
        if any(candidate.video_id == item.video_id for candidate in self._content.items):
            self._mark_item_unavailable(item.video_id)
            return True
        self._content = replace(self._content, items=self._content.items + (item,))
        self._add_content_row(item, playlist=False)
        self._video_info = _first_video_info(self._content.items)
        self._populate_video_quality_combo(self._content.items)
        self._populate_profile_combo(ContentSourceKind.VIDEO)
        self.content_count_label.setText(
            self._translator.content_count(
                sum(item.selected and item.available for item in self._content.items),
                len(self._content.items),
            )
        )
        self._refresh_selection_button()
        self._update_mode_controls()
        self._set_state(AppState.READY)
        return True

    @Slot()
    def _analysis_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        self._analysis_threads.discard(thread)
        if self._analysis_thread is thread:
            self._analysis_thread = None
            self._analysis_worker = None
        self._close_when_idle()

    def _start_thumbnail_load(self, generation: int, url: str | None, video_id: str) -> None:
        if not url:
            return
        thread = QThread(self)
        worker = ThumbnailWorker(url, generation=generation, video_id=video_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result_ready_with_context.connect(self._set_thumbnail)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thumbnail_finished)
        self._thumbnail_threads.add(thread)
        self._thumbnail_workers[thread] = worker
        thread.start()

    def _set_thumbnail(self, generation: int, video_id: str, data: bytes) -> None:
        del generation
        row = self._content_rows.get(video_id)
        if row is not None:
            row.set_thumbnail(data)

    @Slot()
    def _thumbnail_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        self._thumbnail_threads.discard(thread)
        self._thumbnail_workers.pop(thread, None)
        self._close_when_idle()

    def _choose_destination(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, self._t("choose_destination"), self.destination_edit.text()
        )
        if selected:
            self.destination_edit.setText(selected)
            self._save_settings()

    def _start_download(self) -> None:
        if self._content is None:
            self.set_error(self._t("analyze_before_download"))
            return
        selected_items = self._content.selected_items
        if not selected_items:
            self.set_error(self._t("select_item_before_download"))
            return
        if self._dependencies_report is None:
            self.set_error(self._t("dependencies_pending"))
            return
        batch_mode = self._uses_aggregate_video_options()
        try:
            destination = validate_destination(self._destination_or_default(), create=False)
            if batch_mode:
                if self.mp3_radio.isChecked():
                    bitrate = self.bitrate_combo.currentData()
                    if not isinstance(bitrate, int):
                        raise FormatPlanningError(self._t("invalid_bitrate"))
                    plan = build_playlist_audio_plan(
                        bitrate,
                        destination,
                        ffmpeg_available=self._dependencies_report.ffmpeg_ready,
                    )
                else:
                    quality = _coerce_playlist_quality(self.playlist_quality_combo.currentData())
                    profile = _coerce_output_profile(self.profile_combo.currentData())
                    if quality is None:
                        raise FormatPlanningError(self._t("invalid_playlist_quality"))
                    if profile is None:
                        raise FormatPlanningError(self._t("invalid_profile"))
                    plan = build_playlist_video_plan(quality, profile, destination)
            else:
                if self._video_info is None:
                    raise FormatPlanningError(self._t("video_info_before_download"))
                if self.mp3_radio.isChecked():
                    bitrate = self.bitrate_combo.currentData()
                    if not isinstance(bitrate, int):
                        raise FormatPlanningError(self._t("invalid_bitrate"))
                    plan = build_audio_plan(
                        self._video_info,
                        bitrate,
                        destination,
                        ffmpeg_available=self._dependencies_report.ffmpeg_ready,
                    )
                else:
                    selected = self.quality_combo.currentData()
                    if not isinstance(selected, FormatOption):
                        raise FormatPlanningError(self._t("quality_unavailable"))
                    profile = _coerce_output_profile(self.profile_combo.currentData())
                    if profile is None:
                        raise FormatPlanningError(self._t("invalid_profile"))
                    plan = build_video_plan(self._video_info, selected, profile, destination)
        except (ValueError, FormatPlanningError) as exc:
            self.set_error(str(exc))
            return

        ffprobe = self._dependencies_report.by_key("ffprobe").path
        if batch_mode:
            worker = PlaylistDownloadWorker(
                DownloadService(),
                selected_items,
                plan,
                dependencies=self._dependencies_report,
                validator=OutputValidator(ffprobe),
            )
        else:
            item = selected_items[0]
            reservation = reserve_output(destination, item.title, item.video_id)
            worker = DownloadWorker(
                DownloadService(),
                item.webpage_url,
                plan,
                output_template=reservation.template,
                dependencies=self._dependencies_report,
                validator=OutputValidator(ffprobe),
                item_id=item.video_id,
            )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_download_progress)
        worker.result_ready.connect(self._handle_download_result)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._download_finished)
        self._download_thread = thread
        self._download_worker = worker
        self._active_item_id = selected_items[0].video_id
        self._item_progress_max.clear()
        self._item_progress_stage.clear()
        for item in selected_items:
            row = self._content_rows.get(item.video_id)
            if row is not None:
                row.clear_progress()
        self._set_state(AppState.DOWNLOADING)
        thread.start()

    def _on_download_progress(self, event: DownloadProgress) -> None:
        self.status_label.setText(self._translator.message(event.description))
        if event.item_id is not None:
            self._show_item_progress(event)
        if event.stage is ProgressStage.DOWNLOADING:
            self._set_state(AppState.DOWNLOADING)
        elif event.stage in {ProgressStage.MERGING, ProgressStage.CONVERTING}:
            self._set_state(AppState.POSTPROCESSING)
        elif event.stage is ProgressStage.VALIDATING:
            self._set_state(AppState.VALIDATING)
        elif event.stage is ProgressStage.DONE:
            self._set_state(AppState.DOWNLOADING)

    def _handle_download_result(self, result: DownloadResult) -> None:
        if result.status is ResultStatus.SUCCESS and result.final_paths:
            if self._content is not None:
                for item in self._content.selected_items:
                    row = self._content_rows.get(item.video_id)
                    if row is not None:
                        row.set_completed()
            self._last_result_path = result.primary_path
            if len(result.final_paths) == 1:
                self.status_label.setText(self._t("completed_file", name=result.primary_path.name))
            else:
                self.status_label.setText(self._t("completed_items", count=len(result.final_paths)))
            self._set_state(AppState.SUCCESS)
        elif result.status is ResultStatus.PARTIAL and result.final_paths:
            self._last_result_path = result.primary_path
            self.status_label.setText(self._t("partial_download", count=len(result.final_paths)))
            self._app_logger.error(self._t("partial_download", count=len(result.final_paths)))
            self._set_state(AppState.SUCCESS)
        elif result.status is ResultStatus.CANCELLED:
            self._mark_active_item_cancelled()
            self._set_state(AppState.CANCELLED)
            self.status_label.setText(self._t("download_cancelled"))
        else:
            error_message = result.error_message or self._t("download_failed_generic")
            if _looks_like_unavailable(error_message, result.technical_detail or ""):
                if self._active_item_id is not None:
                    self._mark_item_unavailable(self._active_item_id)
            else:
                self._mark_active_item_failed()
            self.set_error(
                error_message,
                result.technical_detail,
            )

    def _show_item_progress(self, event: DownloadProgress) -> None:
        if event.item_id is None:
            return
        row = self._content_rows.get(event.item_id)
        list_item = self._content_list_items.get(event.item_id)
        if row is None or list_item is None:
            return
        self._active_item_id = event.item_id
        phase_stages = {
            ProgressStage.DOWNLOADING,
            ProgressStage.MERGING,
            ProgressStage.CONVERTING,
            ProgressStage.VALIDATING,
        }
        previous_stage = self._item_progress_stage.get(event.item_id)
        if event.stage in phase_stages and previous_stage is not event.stage:
            self._item_progress_max[event.item_id] = 0.0
        self._item_progress_stage[event.item_id] = event.stage
        percentage = event.percentage
        if percentage is not None:
            if event.stage is not ProgressStage.DONE and not event.phase_complete:
                percentage = min(99.0, percentage)
            percentage = max(self._item_progress_max.get(event.item_id, 0.0), percentage)
            if event.stage is not ProgressStage.DONE and not event.phase_complete:
                percentage = min(99.0, percentage)
            self._item_progress_max[event.item_id] = percentage
        else:
            percentage = self._item_progress_max.get(event.item_id)
        self.content_list.scrollToItem(
            list_item,
            QListWidget.ScrollHint.PositionAtCenter,
        )
        if event.stage is ProgressStage.DONE:
            row.set_completed()
        elif event.stage is ProgressStage.FAILED:
            if _looks_like_unavailable(event.description, ""):
                self._mark_item_unavailable(event.item_id)
            else:
                row.set_failed()
        elif event.stage is ProgressStage.CANCELLED:
            row.set_cancelled()
        else:
            row.set_progress(percentage, event.stage)

    def _mark_active_item_failed(self) -> None:
        if self._active_item_id is None:
            return
        row = self._content_rows.get(self._active_item_id)
        if row is not None:
            row.set_failed()

    def _mark_item_unavailable(self, video_id: str, message: str = "Não disponível") -> None:
        if self._content is not None:
            self._content = replace(
                self._content,
                items=tuple(
                    replace(
                        item,
                        selected=False,
                        available=False,
                        availability_error=message,
                    )
                    if item.video_id == video_id
                    else item
                    for item in self._content.items
                ),
            )
            self.content_count_label.setText(
                self._translator.content_count(
                    sum(item.selected and item.available for item in self._content.items),
                    len(self._content.items),
                )
            )
            self._refresh_selection_button()
        row = self._content_rows.get(video_id)
        if row is not None:
            row.set_unavailable(message)

    def _mark_active_item_cancelled(self) -> None:
        if self._active_item_id is None:
            return
        row = self._content_rows.get(self._active_item_id)
        if row is not None:
            row.set_cancelled()

    @Slot()
    def _download_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        if self._download_thread is thread:
            self._download_thread = None
            self._download_worker = None
        self._close_when_idle()

    def _close_when_idle(self) -> None:
        self._prune_finished_threads()
        if (
            self._closing
            and not self._analysis_threads
            and not self._thumbnail_threads
            and self._dependency_thread is None
            and self._download_thread is None
            and self._update_check_thread is None
            and self._update_download_thread is None
            and self._collection_population_timer is None
            and self._content_clear_timer is None
        ):
            self.close()

    def _prune_finished_threads(self) -> None:
        for thread in tuple(self._analysis_threads):
            if _thread_is_finished(thread):
                self._analysis_threads.discard(thread)
        for thread in tuple(self._thumbnail_threads):
            if _thread_is_finished(thread):
                self._thumbnail_threads.discard(thread)
                self._thumbnail_workers.pop(thread, None)
        if self._dependency_thread is not None and _thread_is_finished(self._dependency_thread):
            self._dependency_thread = None
            self._dependency_worker = None
        if self._download_thread is not None and _thread_is_finished(self._download_thread):
            self._download_thread = None
            self._download_worker = None
        if self._update_check_thread is not None and _thread_is_finished(self._update_check_thread):
            self._update_check_thread = None
            self._update_check_worker = None
        if self._update_download_thread is not None and _thread_is_finished(
            self._update_download_thread
        ):
            self._update_download_thread = None
            self._update_download_worker = None

    def _cancel_active_task(self) -> None:
        if self._collection_population_timer is not None:
            self._analysis_generation += 1
            self._stop_collection_population()
            self.clear_content()
            self.set_error(self._t("analysis_cancelled"))
            return
        if self._state is AppState.ANALYZING:
            self._analysis_generation += 1
            self.set_error(self._t("analysis_cancelled"))
        elif self._download_worker is not None:
            self.status_label.setText(self._t("download_cancelling"))
            self._download_worker.cancel()

    def _show_dependency_placeholder(self) -> None:
        if self._dependencies_report is None:
            QMessageBox.information(
                self,
                self._t("dependencies"),
                self._t("dependency_running"),
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("dependency_diagnostic"))
        dialog.setMinimumWidth(620)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        for item in self._dependencies_report.items:
            status = (
                self._t("ready_status")
                if item.ready
                else self._translator.dependency_status(item.status.value)
            )
            value = "\n".join(
                (
                    f"{status} — {item.version or self._t('version_unavailable')}",
                    f"{self._t('path')}: {item.path or self._t('not_found')}",
                    self._translator.message(item.recommendation),
                )
            )
            label = QLabel(value)
            label.setWordWrap(True)
            form.addRow(f"{item.label}:", label)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(self._t("close"))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _show_settings(self) -> None:
        previous_settings = self._settings
        dialog = SettingsDialog(self._settings, self)
        dialog.settings_changed.connect(self._preview_settings_changed)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._apply_settings_state(previous_settings, save=False)
            return

        language, theme_name, always_on_top, check_updates, thumbnail_limit = dialog.values()
        self._apply_settings_state(
            replace(
                self._settings,
                language=language,
                theme=theme_name,
                always_on_top=always_on_top,
                check_updates=check_updates,
                playlist_thumbnail_limit=thumbnail_limit,
            ),
            save=True,
        )

    @Slot(str, str, bool, bool, int)
    def _preview_settings_changed(
        self,
        language: str,
        theme_name: str,
        always_on_top: bool,
        check_updates: bool,
        thumbnail_limit: int,
    ) -> None:
        self._apply_settings_state(
            replace(
                self._settings,
                language=language,
                theme=theme_name,
                always_on_top=always_on_top,
                check_updates=check_updates,
                playlist_thumbnail_limit=thumbnail_limit,
            ),
            save=False,
        )

    def _apply_settings_state(self, settings: AppSettings, *, save: bool) -> None:
        previous_settings = self._settings
        self._settings = settings

        language_changed = previous_settings.language != settings.language
        theme_changed = previous_settings.theme != settings.theme
        if language_changed or theme_changed:
            self._translator = Translator(self._settings.language)
            self._theme = theme_for(self._settings.theme)
            self._apply_theme()
            self._retranslate_ui()

        if previous_settings.always_on_top != settings.always_on_top:
            self._apply_window_preferences()
        if previous_settings.playlist_thumbnail_limit != self._settings.playlist_thumbnail_limit:
            self._apply_playlist_thumbnail_limit()
        if save:
            self._save_settings()

    def _apply_theme(self) -> None:
        """Aplica o tema à aplicação, aos controles customizados e às linhas da lista."""
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(self._theme.application_stylesheet())
        self.site_tabs.setStyleSheet(self._theme.tabs_stylesheet())
        self.menuBar().setStyleSheet(self._theme.menu_stylesheet())
        for row in self._content_rows.values():
            row.set_theme(self._theme)

    def _resize_to_available_screen(self) -> None:
        """Abre a janela dentro da área útil do monitor, com margem de segurança."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(self._settings.window_width, self._settings.window_height)
            return

        available = screen.availableGeometry()
        max_width = max(self.minimumWidth(), available.width() - 32)
        max_height = max(self.minimumHeight(), available.height() - 32)
        self.resize(
            min(self._settings.window_width, max_width),
            min(self._settings.window_height, max_height),
        )

    def _apply_window_preferences(self) -> None:
        was_visible = self.isVisible()
        desired_topmost = self._settings.always_on_top
        current_topmost = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if current_topmost == desired_topmost and not was_visible:
            return
        if was_visible and self._set_native_topmost(desired_topmost):
            return
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, desired_topmost)
        if was_visible:
            self.show()

    def _set_native_topmost(self, enabled: bool) -> bool:
        """Altera a ordem Z sem recriar a janela visível no Windows."""
        if sys.platform != "win32":
            return False
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            hwnd_insert_after = -1 if enabled else -2
            flags = 0x0001 | 0x0002 | 0x0010
            return bool(user32.SetWindowPos(hwnd, hwnd_insert_after, 0, 0, 0, 0, flags))
        except (AttributeError, OSError, TypeError, ValueError):
            return False

    def _apply_playlist_thumbnail_limit(self) -> None:
        if self._content is None or self._content.source_kind is not ContentSourceKind.PLAYLIST:
            return
        enabled = len(self._content.items) <= self._settings.playlist_thumbnail_limit
        if enabled == self._playlist_thumbnails_enabled:
            return

        self._analysis_generation += 1
        self._playlist_thumbnails_enabled = enabled
        for item in self._content.items:
            row = self._content_rows.get(item.video_id)
            if row is not None:
                row.set_thumbnail_policy(not enabled)
        if enabled:
            for item in self._content.items:
                self._start_thumbnail_load(self._analysis_generation, item.thumbnail, item.video_id)

    def _show_about(self) -> None:
        dialog = AboutDialog(
            self._translator,
            resource_root() / "icon" / "logo.png",
            self,
        )
        dialog.exec()

    def _check_for_updates_automatically(self) -> None:
        if self.isVisible() and self._settings.check_updates:
            self._start_update_check(automatic=True)

    def _check_for_updates(self, _checked: bool = False) -> None:
        self._start_update_check(automatic=False)

    def _start_update_check(self, *, automatic: bool) -> None:
        if self._update_check_thread is not None:
            if not automatic and self._update_dialog is not None:
                self._update_dialog.show()
                self._update_dialog.raise_()
                self._update_dialog.activateWindow()
            return
        self._update_check_automatic = automatic
        if not automatic:
            dialog = self._ensure_update_dialog()
            dialog.show_checking()
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

        thread = QThread(self)
        worker = UpdateCheckWorker(self._update_service)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result_ready.connect(self._handle_update_check_result)
        worker.failed.connect(self._handle_update_check_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_check_finished)
        self._update_check_thread = thread
        self._update_check_worker = worker
        thread.start()

    def _ensure_update_dialog(self) -> UpdateDialog:
        if self._update_dialog is None:
            dialog = UpdateDialog(self._translator, APP_VERSION, self)
            dialog.download_requested.connect(self._start_update_download)
            self._update_dialog = dialog
        return self._update_dialog

    @Slot(object)
    def _handle_update_check_result(self, release: ReleaseInfo | None) -> None:
        if release is None:
            if not self._update_check_automatic:
                self._ensure_update_dialog().show_no_update()
            return
        self._update_release = release
        dialog = self._ensure_update_dialog()
        dialog.show_release(release)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    @Slot(str)
    def _handle_update_check_error(self, _message: str) -> None:
        self._app_logger.error("Não foi possível verificar atualizações.")
        if not self._update_check_automatic:
            self._ensure_update_dialog().show_error(_message)

    @Slot()
    def _update_check_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        if self._update_check_thread is thread:
            self._update_check_thread = None
            self._update_check_worker = None
        self._close_when_idle()

    @Slot()
    def _start_update_download(self) -> None:
        release = self._update_release
        if release is None or self._update_download_thread is not None:
            return
        if self._has_running_task():
            QMessageBox.information(
                self,
                self._t("update_install_title"),
                self._t("update_active_task"),
            )
            return
        dialog = self._ensure_update_dialog()
        dialog.set_downloading()
        thread = QThread(self)
        worker = UpdateDownloadWorker(self._update_service, release)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.set_progress)
        worker.result_ready.connect(self._handle_update_download_result)
        worker.failed.connect(self._handle_update_download_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._update_download_finished)
        self._update_download_thread = thread
        self._update_download_worker = worker
        thread.start()

    @Slot(object)
    def _handle_update_download_result(self, prepared: PreparedUpdate) -> None:
        self._prepared_update = prepared
        dialog = self._ensure_update_dialog()
        dialog.set_ready()
        answer = QMessageBox.question(
            self,
            self._t("update_install_title"),
            self._t("update_install_prompt", version=prepared.release.version_text),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._launch_prepared_update()
        else:
            self._update_service.cleanup_prepared(prepared)
            self._prepared_update = None

    @Slot(str)
    def _handle_update_download_error(self, _message: str) -> None:
        self._app_logger.error("Não foi possível preparar a atualização.")
        self._ensure_update_dialog().show_error(_message)

    @Slot()
    def _update_download_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        if self._update_download_thread is thread:
            self._update_download_thread = None
            self._update_download_worker = None
        self._close_when_idle()

    def _launch_prepared_update(self) -> None:
        prepared = self._prepared_update
        if prepared is None:
            return
        if self._has_running_task():
            QMessageBox.information(
                self,
                self._t("update_install_title"),
                self._t("update_active_task"),
            )
            return
        frozen = bool(getattr(sys, "frozen", False))
        install_root = (
            Path(sys.executable).resolve().parent if frozen else self._project_root.resolve()
        )
        if frozen and not (install_root / UPDATER_EXECUTABLE_NAME).is_file():
            self._app_logger.error("O instalador auxiliar da atualização não foi encontrado.")
            QMessageBox.warning(
                self,
                self._t("update_install_title"),
                self._t("update_helper_missing"),
            )
            return
        try:
            check_install_prerequisites(prepared.archive_path, install_root)
        except (InstallError, OSError):
            self._app_logger.error("Não foi possível preparar a pasta para atualização.")
            QMessageBox.warning(
                self,
                self._t("update_install_title"),
                self._t("update_preflight_failed"),
            )
            return
        helper_args = [
            "--archive",
            str(prepared.archive_path),
            "--checksum",
            str(prepared.checksum_path),
            "--install-root",
            str(install_root),
            "--parent-pid",
            str(os.getpid()),
            "--version",
            prepared.release.version_text,
            "--package-id",
            self._update_service.config.package_id,
            "--launch-mode",
            "frozen" if frozen else "source",
            "--cleanup-root",
            str(prepared.work_dir),
        ]
        if frozen:
            updater_executable = install_root / UPDATER_EXECUTABLE_NAME
            command = (
                [str(updater_executable), *helper_args]
                if updater_executable.is_file()
                else [sys.executable, "--update-helper", *helper_args]
            )
        else:
            command = [sys.executable, "-m", "app.update_helper", *helper_args]
        try:
            self._start_hidden_process(command, install_root)
        except OSError:
            self._app_logger.error("Não foi possível iniciar o instalador auxiliar.")
            QMessageBox.warning(
                self,
                self._t("update_install_title"),
                self._t("update_launch_failed"),
            )
            return
        self._prepared_update = None
        if self._update_dialog is not None:
            self._update_dialog.close()
        self._save_settings()
        self.close()

    @staticmethod
    def _start_hidden_process(command: list[str], cwd: Path) -> None:
        flags = 0
        startupinfo = None
        if os.name == "nt":
            flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            )
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        subprocess.Popen(
            command,
            cwd=str(cwd),
            close_fds=True,
            creationflags=flags,
            startupinfo=startupinfo,
        )

    def _has_running_task(self) -> bool:
        self._prune_finished_threads()
        return bool(
            any(not _thread_is_finished(thread) for thread in self._analysis_threads)
            or (
                self._download_thread is not None and not _thread_is_finished(self._download_thread)
            )
            or self._collection_population_timer is not None
            or self._content_clear_timer is not None
            or (
                self._update_download_thread is not None
                and not _thread_is_finished(self._update_download_thread)
            )
        )

    def _has_background_work(self) -> bool:
        self._prune_finished_threads()
        return bool(
            self._analysis_threads
            or self._thumbnail_threads
            or self._dependency_thread is not None
            or self._download_thread is not None
            or self._update_check_thread is not None
            or self._update_download_thread is not None
            or self._collection_population_timer is not None
            or self._content_clear_timer is not None
        )

    def _show_support(self) -> None:
        QDesktopServices.openUrl(QUrl("https://ko-fi.com/mmachida"))

    def _save_settings(self) -> None:
        mode = type(self._settings.mode).VIDEO
        bitrate = self.bitrate_combo.currentData()
        if not isinstance(bitrate, int):
            bitrate = 192
        try:
            self._settings_store.save(
                AppSettings(
                    destination=self._destination_or_default(),
                    mode=mode,
                    mp3_bitrate=bitrate,
                    window_width=self.width(),
                    window_height=self.height(),
                    language=self._settings.language,
                    always_on_top=self._settings.always_on_top,
                    check_updates=self._settings.check_updates,
                    playlist_thumbnail_limit=self._settings.playlist_thumbnail_limit,
                    theme=self._settings.theme,
                )
            )
        except (OSError, ValueError):
            pass

    def _destination_or_default(self) -> Path:
        candidate = Path(self.destination_edit.text()).expanduser()
        if candidate.is_dir():
            return candidate
        self._default_output_directory.mkdir(parents=True, exist_ok=True)
        fallback = self._default_output_directory.resolve()
        self.destination_edit.setText(str(fallback))
        return fallback

    def _open_folder(self) -> None:
        folder = self._destination_or_default()
        self._save_settings()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def closeEvent(self, event: QCloseEvent) -> None:
        active = self._has_running_task()
        if active and not self._closing:
            answer = QMessageBox.question(
                self,
                self._t("close_title"),
                self._t("close_prompt"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing = True
            self._analysis_generation += 1
            self._stop_collection_population()
            self._stop_content_clear()
            if self._download_worker is not None:
                self._download_worker.cancel()
            if self._update_download_worker is not None:
                self._update_download_worker.cancel()
            self.status_label.setText(self._t("closing_tasks"))
            self.close_requested.emit()
            self._close_when_idle()
            event.ignore()
            return
        if self._has_background_work():
            self._closing = True
            self._analysis_generation += 1
            self._stop_collection_population()
            self._stop_content_clear()
            if self._update_download_worker is not None:
                self._update_download_worker.cancel()
            self._close_when_idle()
            event.ignore()
            return
        self._save_settings()
        event.accept()


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Duração indisponível"
    total = max(0, int(seconds))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes}:{remainder:02d}"


def _content_item_from_video_info(info: VideoInfo) -> ContentItem:
    return ContentItem(
        video_id=info.video_id,
        webpage_url=info.webpage_url,
        title=info.title,
        uploader=info.uploader,
        duration=info.duration,
        thumbnail=info.thumbnail,
        formats=info.formats,
    )


def _collection_from_video_info(
    info: VideoInfo, source_kind: ContentSourceKind = ContentSourceKind.VIDEO
) -> ContentCollection:
    return ContentCollection(
        source_kind=source_kind,
        source_url=info.webpage_url,
        title=info.title,
        items=(_content_item_from_video_info(info),),
    )


def _is_single_video_source(source_kind: ContentSourceKind) -> bool:
    return source_kind in {
        ContentSourceKind.VIDEO,
        ContentSourceKind.TWITCH_VOD,
        ContentSourceKind.TWITCH_CLIP,
        ContentSourceKind.TWITTER_VIDEO,
        ContentSourceKind.INSTAGRAM_VIDEO,
    }


def _is_twitch_source(source_kind: ContentSourceKind) -> bool:
    return source_kind in {
        ContentSourceKind.TWITCH_VOD,
        ContentSourceKind.TWITCH_CLIP,
    }


def _first_video_info(items: tuple[ContentItem, ...], *, selected_only: bool = False) -> VideoInfo:
    candidates = (
        tuple(item for item in items if item.selected and item.available)
        if selected_only
        else items
    )
    if not candidates:
        candidates = items
    source = next(
        (item for item in candidates if item.available and item.as_video_info().video_options),
        None,
    )
    if source is None:
        source = candidates[0]
    return source.as_video_info()


def _content_count_text(items: tuple[ContentItem, ...]) -> str:
    count = len(items)
    selected = sum(1 for item in items if item.selected and item.available)
    label = "Item" if count == 1 else "Itens"
    return f"{selected} / {count} {label}"


def _looks_like_unavailable(message: str, detail: str) -> bool:
    text = f"{message} {detail}".casefold()
    return any(
        marker in text
        for marker in (
            "não está disponível",
            "não disponível",
            "indisponível",
            "private video",
            "deleted video",
            "video unavailable",
            "exige autenticação",
            "requires authentication",
        )
    )


def _coerce_output_profile(value: object) -> OutputProfile | None:
    if isinstance(value, OutputProfile):
        return value
    if isinstance(value, str):
        try:
            return OutputProfile(value)
        except ValueError:
            return None
    return None


def _coerce_source_kind(value: object) -> ContentSourceKind:
    if isinstance(value, ContentSourceKind):
        return value
    if isinstance(value, str):
        try:
            return ContentSourceKind(value)
        except ValueError:
            pass
    return ContentSourceKind.VIDEO


def _coerce_playlist_quality(value: object) -> PlaylistQuality | None:
    if isinstance(value, PlaylistQuality):
        return value
    if isinstance(value, str):
        try:
            return PlaylistQuality(value)
        except ValueError:
            return None
    return None


def _thread_is_finished(thread: QThread) -> bool:
    try:
        return thread.isFinished()
    except RuntimeError:
        return True
