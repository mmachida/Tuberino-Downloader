"""Workers Qt para operações que não podem bloquear a interface."""

from __future__ import annotations

import threading
import urllib.request
from dataclasses import replace

from PySide6.QtCore import QObject, Signal, Slot

from app.models import (
    ContentItem,
    ContentSourceKind,
    DownloadPlan,
    DownloadProgress,
    DownloadResult,
    ProgressStage,
    ResultStatus,
)
from app.services.dependencies import DependencyChecker, DependencyReport
from app.services.download_service import DownloadService
from app.services.file_manager import reserve_output
from app.services.output_validator import OutputValidator
from app.services.yt_dlp_service import AnalysisError, YtDlpService
from app.updates.service import ReleaseInfo, UpdateError, UpdateService


class AnalysisWorker(QObject):
    """Consulta metadados no thread da tarefa."""

    result_ready = Signal(object)
    progress = Signal(int, int)
    dependencies_ready = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        service: YtDlpService,
        url: str,
        dependency_checker: DependencyChecker | None = None,
        source_kind: ContentSourceKind = ContentSourceKind.VIDEO,
        generation: int | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.url = url
        self.dependency_checker = dependency_checker
        self.source_kind = source_kind
        self.generation = generation

    @Slot()
    def run(self) -> None:
        try:
            dependencies = self.dependency_checker.check() if self.dependency_checker else None
            if dependencies is not None:
                self.dependencies_ready.emit(dependencies)
            if self.source_kind is ContentSourceKind.PLAYLIST:
                result = self.service.analyze_playlist(
                    self.url,
                    dependencies,
                    progress_callback=self.progress.emit,
                )
            elif self.source_kind in {
                ContentSourceKind.TWITCH_VOD,
                ContentSourceKind.TWITCH_CLIP,
            }:
                result = self.service.analyze_twitch(self.url, self.source_kind, dependencies)
            elif self.source_kind is ContentSourceKind.TWITTER_VIDEO:
                result = self.service.analyze_twitter(self.url, dependencies)
            elif self.source_kind is ContentSourceKind.INSTAGRAM_VIDEO:
                result = self.service.analyze_instagram(self.url, dependencies)
            else:
                result = self.service.analyze_video(self.url, dependencies)
        except AnalysisError as exc:
            self.failed.emit(exc.user_message, exc.technical_detail or "")
        except Exception as exc:
            self.failed.emit("Não foi possível consultar o vídeo. Verifique sua conexão.", str(exc))
        else:
            self.result_ready.emit(result)
        finally:
            self.finished.emit()


class DependencyWorker(QObject):
    """Verifica executáveis/pacotes sem bloquear o início da janela."""

    result_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, checker: DependencyChecker) -> None:
        super().__init__()
        self.checker = checker

    @Slot()
    def run(self) -> None:
        try:
            self.result_ready.emit(self.checker.check())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class UpdateCheckWorker(QObject):
    """Consulta GitHub Releases sem bloquear a interface."""

    result_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: UpdateService) -> None:
        super().__init__()
        self.service = service

    @Slot()
    def run(self) -> None:
        try:
            self.result_ready.emit(self.service.check_latest())
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Não foi possível consultar atualizações.")
        finally:
            self.finished.emit()


class UpdateDownloadWorker(QObject):
    """Baixa e valida o pacote de atualização fora da thread principal."""

    progress = Signal(int, int)
    result_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: UpdateService, release: ReleaseInfo) -> None:
        super().__init__()
        self.service = service
        self.release = release
        self.cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            prepared = self.service.download_and_prepare(
                self.release,
                progress=self.progress.emit,
                cancel=self.cancel_event.is_set,
            )
            self.result_ready.emit(prepared)
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Não foi possível baixar a atualização.")
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self.cancel_event.set()


class ThumbnailWorker(QObject):
    """Carrega uma miniatura pequena fora da thread da interface."""

    result_ready = Signal(bytes)
    result_ready_with_context = Signal(int, str, bytes)
    finished = Signal()

    def __init__(
        self,
        url: str,
        *,
        max_bytes: int = 5_000_000,
        generation: int = 0,
        video_id: str = "",
    ) -> None:
        super().__init__()
        self.url = url
        self.max_bytes = max_bytes
        self.generation = generation
        self.video_id = video_id

    @Slot()
    def run(self) -> None:
        try:
            request = urllib.request.Request(
                self.url, headers={"User-Agent": "TuberinoDownloader/0.1"}
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(self.max_bytes + 1)
            if len(data) <= self.max_bytes:
                self.result_ready.emit(data)
                self.result_ready_with_context.emit(self.generation, self.video_id, data)
        except (OSError, ValueError):
            pass
        finally:
            self.finished.emit()


class DownloadWorker(QObject):
    """Executa transferência e pós-processamento fora da thread Qt principal."""

    progress = Signal(object)
    result_ready = Signal(object)
    finished = Signal()

    def __init__(
        self,
        service: DownloadService,
        url: str,
        plan: DownloadPlan,
        *,
        output_template: str | None = None,
        dependencies: DependencyReport | None = None,
        validator: OutputValidator | None = None,
        item_id: str | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.url = url
        self.plan = plan
        self.output_template = output_template
        self.dependencies = dependencies
        self.validator = validator
        self.item_id = item_id
        self.cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        result: DownloadResult
        try:
            result = self.service.download(
                self.url,
                self.plan,
                output_template=self.output_template,
                deps=self.dependencies,
                progress_callback=self._emit_progress,
                cancel_event=self.cancel_event,
                output_validator=self.validator,
            )
        except Exception as exc:
            result = DownloadResult(
                status=ResultStatus.ERROR,
                error_message="Não foi possível concluir o download.",
                technical_detail=str(exc),
            )
        try:
            self.result_ready.emit(result)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _emit_progress(self, event: DownloadProgress) -> None:
        if self.item_id is not None and event.item_id is None:
            event = replace(event, item_id=self.item_id)
        self.progress.emit(event)


class PlaylistDownloadWorker(QObject):
    """Baixa itens selecionados de uma playlist ou coleção em sequência."""

    progress = Signal(object)
    result_ready = Signal(object)
    finished = Signal()

    def __init__(
        self,
        service: DownloadService,
        items: tuple[ContentItem, ...],
        plan: DownloadPlan,
        *,
        dependencies: DependencyReport | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.items = items
        self.plan = plan
        self.dependencies = dependencies
        self.validator = validator
        self.cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        final_paths: list = []
        failures: list[str] = []
        total = len(self.items)
        cancelled = False
        for index, item in enumerate(self.items, start=1):
            if self.cancel_event.is_set():
                cancelled = True
                break
            try:
                reservation = reserve_output(self.plan.destination, item.title, item.video_id)
                item_result = self.service.download(
                    item.webpage_url,
                    self.plan,
                    output_template=reservation.template,
                    deps=self.dependencies,
                    progress_callback=lambda event, current=index, current_item_id=item.video_id: (
                        self._emit_progress(event, current, total, current_item_id)
                    ),
                    cancel_event=self.cancel_event,
                    output_validator=self.validator,
                )
            except Exception as exc:
                item_result = DownloadResult(
                    ResultStatus.ERROR,
                    error_message="Não foi possível concluir este item.",
                    technical_detail=str(exc),
                )

            if item_result.status is ResultStatus.SUCCESS:
                final_paths.extend(item_result.final_paths)
            if item_result.status is ResultStatus.CANCELLED:
                self._emit_progress(
                    DownloadProgress(
                        ProgressStage.CANCELLED,
                        "Item cancelado.",
                        item_id=item.video_id,
                    ),
                    index,
                    total,
                    item.video_id,
                )
                cancelled = True
                break
            if item_result.status is not ResultStatus.SUCCESS:
                failure_message = item_result.error_message or "Falha no item."
                failures.append(f"{item.title}: {failure_message}")
                self._emit_progress(
                    DownloadProgress(
                        ProgressStage.FAILED,
                        failure_message,
                        item_id=item.video_id,
                    ),
                    index,
                    total,
                    item.video_id,
                )
                continue
            self._emit_progress(
                DownloadProgress(
                    ProgressStage.DONE,
                    "Item concluído.",
                    percentage=100,
                    item_id=item.video_id,
                ),
                index,
                total,
                item.video_id,
            )

        if cancelled:
            result = DownloadResult(ResultStatus.CANCELLED, tuple(final_paths))
        elif failures:
            result_status = ResultStatus.PARTIAL if final_paths else ResultStatus.ERROR
            result = DownloadResult(
                result_status,
                tuple(final_paths),
                f"{len(failures)} item(ns) não puderam ser processados; os demais foram concluídos."
                if final_paths
                else "Nenhum item da fila pôde ser concluído.",
                "\n".join(failures),
            )
        else:
            result = DownloadResult(ResultStatus.SUCCESS, tuple(final_paths))
        try:
            self.result_ready.emit(result)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _emit_progress(
        self,
        event: DownloadProgress,
        index: int,
        total: int,
        item_id: str,
    ) -> None:
        self.progress.emit(
            DownloadProgress(
                stage=event.stage,
                description=f"[{index}/{total}] {event.description}",
                percentage=event.percentage,
                downloaded_bytes=event.downloaded_bytes,
                total_bytes=event.total_bytes,
                speed=event.speed,
                eta=event.eta,
                item_id=item_id,
                phase_complete=event.phase_complete,
            )
        )
