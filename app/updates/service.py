"""Cliente seguro para consultar e preparar GitHub Releases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .config import UpdateConfig

CHUNK_SIZE = 64 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
HEX_SHA256 = re.compile(r"\b([0-9a-fA-F]{64})\b")
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


class UpdateError(RuntimeError):
    """Erro seguro para exibição sem expor traceback técnico na interface."""


class UpdateCancelled(UpdateError):
    """Download de atualização cancelado pelo usuário."""


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    name: str
    url: str
    size: int | None = None


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: tuple[int, int, int]
    version_text: str
    tag_name: str
    notes: str
    html_url: str
    package: ReleaseAsset
    checksum: ReleaseAsset
    published_at: str


@dataclass(frozen=True, slots=True)
class PreparedUpdate:
    release: ReleaseInfo
    archive_path: Path
    checksum_path: Path
    work_dir: Path
    manifest: dict[str, object]


def parse_version(value: object) -> tuple[int, int, int]:
    """Aceita tags estáveis no formato ``v1.2.3`` ou ``1.2.3``."""
    if (
        isinstance(value, tuple)
        and len(value) == 3
        and all(isinstance(item, int) and item >= 0 for item in value)
    ):
        return value
    text = str(value or "").strip()
    if text[:1].lower() == "v":
        text = text[1:].strip()
    match = VERSION_PATTERN.fullmatch(text)
    if match is None:
        raise UpdateError(f"Versão inválida: {value!s}")
    return tuple(int(group) for group in match.groups())


class UpdateService:
    """Consulta, baixa e valida um pacote sem bloquear a thread da UI."""

    def __init__(
        self,
        config: UpdateConfig,
        current_version: str,
        *,
        opener=None,
        timeout: float = 15.0,
    ) -> None:
        self.config = config
        self.current_version = parse_version(current_version)
        self._opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self._operation_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return self.config.configured

    def check_latest(self) -> ReleaseInfo | None:
        """Retorna somente um release estável mais novo que o aplicativo."""
        if not self.configured:
            raise UpdateError("Atualizações não estão configuradas.")
        self._acquire_operation()
        try:
            payload = self._get_json_payload(self.config.releases_url)
            if not isinstance(payload, list):
                raise UpdateError("A resposta do GitHub é inválida.")

            candidates: list[tuple[tuple[int, int, int], dict[str, object]]] = []
            for raw_release in payload:
                if not isinstance(raw_release, dict):
                    continue
                if raw_release.get("draft") or raw_release.get("prerelease"):
                    continue
                try:
                    version = parse_version(raw_release.get("tag_name"))
                except UpdateError:
                    continue
                if version > self.current_version:
                    candidates.append((version, raw_release))

            candidates.sort(key=lambda item: item[0], reverse=True)
            errors: list[UpdateError] = []
            for _version, release_payload in candidates:
                try:
                    release = self._parse_release(release_payload)
                except UpdateError as exc:
                    errors.append(exc)
                    continue
                if release is not None:
                    return release
            if errors:
                raise errors[0]
            return None
        finally:
            self._operation_lock.release()

    def download_and_prepare(
        self,
        release: ReleaseInfo,
        destination: Path | str | None = None,
        *,
        progress: ProgressCallback | None = None,
        cancel: CancelCallback | None = None,
    ) -> PreparedUpdate:
        """Baixa, confere e valida o release em uma pasta temporária."""
        self._acquire_operation()
        work_dir: Path | None = None
        try:
            base = Path(destination).expanduser() if destination else Path(tempfile.gettempdir())
            base.mkdir(parents=True, exist_ok=True)
            work_dir = Path(tempfile.mkdtemp(prefix="tuberino-update-", dir=str(base)))
            archive_path = work_dir / release.package.name
            checksum_path = work_dir / release.checksum.name
            self._download(release.package, archive_path, progress=progress, cancel=cancel)
            self._download(release.checksum, checksum_path, progress=None, cancel=cancel)
            self.verify_checksum(archive_path, checksum_path)
            manifest = self.validate_archive(archive_path, release.version)
            return PreparedUpdate(release, archive_path, checksum_path, work_dir, manifest)
        except UpdateCancelled:
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except UpdateError:
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)
            raise
        except (OSError, zipfile.BadZipFile, ValueError, json.JSONDecodeError) as exc:
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)
            raise UpdateError(f"Não foi possível preparar a atualização: {exc}") from exc
        finally:
            self._operation_lock.release()

    def cleanup_prepared(self, prepared: PreparedUpdate) -> None:
        """Remove o pacote temporário quando o usuário cancela a instalação."""
        shutil.rmtree(prepared.work_dir, ignore_errors=True)

    def validate_archive(
        self,
        archive_path: Path | str,
        expected_version: object,
        *,
        expected_package_id: str | None = None,
    ) -> dict[str, object]:
        version = parse_version(expected_version)
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
                raise UpdateError("O pacote de atualização é inválido.")
            if sum(max(0, info.file_size) for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise UpdateError("O pacote de atualização é grande demais.")

            files: dict[str, zipfile.ZipInfo] = {}
            folded_paths: set[str] = set()
            for info in infos:
                relative = self._safe_archive_path(info.filename)
                folded = relative.casefold()
                if folded in folded_paths:
                    raise UpdateError("O pacote contém caminhos duplicados.")
                folded_paths.add(folded)
                if info.is_dir():
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise UpdateError("O pacote contém um link simbólico bloqueado.")
                files[relative] = info

            manifest_info = files.get("update-manifest.json")
            if manifest_info is None:
                raise UpdateError("O manifesto da atualização está ausente.")
            with archive.open(manifest_info) as stream:
                raw_manifest = stream.read(MAX_METADATA_BYTES + 1)
            if len(raw_manifest) > MAX_METADATA_BYTES:
                raise UpdateError("O manifesto da atualização é grande demais.")
            try:
                manifest = json.loads(raw_manifest.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise UpdateError("O manifesto da atualização é inválido.") from exc
            self._validate_manifest(
                manifest,
                set(files),
                version,
                expected_package_id or self.config.package_id,
            )
            return manifest

    @staticmethod
    def verify_checksum(archive_path: Path | str, checksum_path: Path | str) -> None:
        try:
            checksum_text = Path(checksum_path).read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            raise UpdateError("Não foi possível ler o checksum do pacote.") from exc
        match = HEX_SHA256.search(checksum_text)
        if match is None:
            raise UpdateError("O checksum publicado é inválido.")
        digest = hashlib.sha256()
        try:
            with Path(archive_path).open("rb") as stream:
                for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise UpdateError("Não foi possível calcular o checksum do pacote.") from exc
        if digest.hexdigest() != match.group(1).lower():
            raise UpdateError("O checksum SHA-256 do pacote não confere.")

    def _acquire_operation(self) -> None:
        if not self._operation_lock.acquire(blocking=False):
            raise UpdateError("Já existe uma operação de atualização em andamento.")

    def _get_json_payload(self, url: str) -> object:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Tuberino-Downloader-Updater/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            with response:
                self._ensure_https(str(getattr(response, "geturl", lambda: url)()))
                status = getattr(response, "status", 200)
                if status != 200:
                    raise UpdateError(f"GitHub respondeu com HTTP {status}.")
                raw = response.read(MAX_METADATA_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpdateError("Nenhum release publicado foi encontrado.") from exc
            if exc.code in (403, 429):
                raise UpdateError("O limite temporário do GitHub foi atingido.") from exc
            raise UpdateError(f"GitHub respondeu com HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError(f"Não foi possível consultar atualizações: {exc}") from exc
        if len(raw) > MAX_METADATA_BYTES:
            raise UpdateError("A resposta do GitHub é maior que o esperado.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateError("A resposta do GitHub é inválida.") from exc
        return payload

    def _get_json(self, url: str) -> dict[str, object]:
        payload = self._get_json_payload(url)
        if not isinstance(payload, dict):
            raise UpdateError("A resposta do GitHub é inválida.")
        return payload

    def _parse_release(self, payload: dict[str, object]) -> ReleaseInfo | None:
        if payload.get("draft") or payload.get("prerelease") or not payload.get("published_at"):
            raise UpdateError("O release mais recente não é uma versão estável publicada.")
        tag_name = str(payload.get("tag_name") or "").strip()
        version = parse_version(tag_name)
        if version <= self.current_version:
            return None
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("O release não contém uma lista de pacotes.")
        by_name: dict[str, ReleaseAsset] = {}
        for raw_asset in assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name") or "").strip()
            browser_url = str(raw_asset.get("browser_download_url") or "").strip()
            if not name or not browser_url or raw_asset.get("state", "uploaded") != "uploaded":
                continue
            parsed_url = urlparse(browser_url)
            if parsed_url.scheme != "https" or not parsed_url.hostname:
                continue
            size = raw_asset.get("size")
            by_name[name] = ReleaseAsset(name, browser_url, size if isinstance(size, int) else None)
        package = by_name.get(self.config.package_name)
        checksum = by_name.get(self.config.checksum_name)
        if package is None:
            raise UpdateError(
                f"Não há pacote compatível ({self.config.package_name}) neste release."
            )
        if checksum is None:
            raise UpdateError(
                f"O checksum obrigatório ({self.config.checksum_name}) não foi publicado."
            )
        return ReleaseInfo(
            version=version,
            version_text=".".join(str(value) for value in version),
            tag_name=tag_name,
            notes=str(payload.get("body") or "Sem notas da versão."),
            html_url=str(payload.get("html_url") or self.config.repository_url),
            package=package,
            checksum=checksum,
            published_at=str(payload["published_at"]),
        )

    def _download(
        self,
        asset: ReleaseAsset,
        destination: Path,
        *,
        progress: ProgressCallback | None,
        cancel: CancelCallback | None,
    ) -> None:
        request = urllib.request.Request(
            asset.url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "Tuberino-Downloader-Updater/1",
            },
        )
        temporary = destination.with_name(destination.name + ".part")
        total = asset.size or 0
        written = 0
        try:
            response = self._opener(request, timeout=self.timeout)
            with response:
                self._ensure_https(str(getattr(response, "geturl", lambda: asset.url)()))
                status = getattr(response, "status", 200)
                if status != 200:
                    raise UpdateError(f"Download respondeu com HTTP {status}.")
                if not total:
                    try:
                        total = int(response.headers.get("Content-Length", 0))
                    except (AttributeError, TypeError, ValueError):
                        total = 0
                destination.parent.mkdir(parents=True, exist_ok=True)
                with temporary.open("wb") as stream:
                    if progress:
                        progress(0, total)
                    while True:
                        if cancel and cancel():
                            raise UpdateCancelled("Download cancelado.")
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        stream.write(chunk)
                        written += len(chunk)
                        if progress:
                            progress(written, total)
            if total and written != total:
                raise UpdateError("O download foi interrompido antes de terminar.")
            temporary.replace(destination)
        except urllib.error.HTTPError as exc:
            raise UpdateError(f"Download respondeu com HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateError(f"Não foi possível baixar {asset.name}: {exc}") from exc
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

    @classmethod
    def _validate_manifest(
        cls,
        manifest: object,
        archive_files: set[str],
        expected_version: tuple[int, int, int],
        expected_package_id: str,
    ) -> None:
        if not isinstance(manifest, dict) or manifest.get("format") != 1:
            raise UpdateError("O manifesto da atualização é incompatível.")
        if parse_version(manifest.get("version")) != expected_version:
            raise UpdateError("A versão do manifesto não corresponde ao release.")
        package_id = manifest.get("package_id")
        if package_id != expected_package_id:
            raise UpdateError("O pacote não é compatível com esta instalação.")
        files = manifest.get("files")
        if (
            not isinstance(files, list)
            or not files
            or any(not isinstance(item, str) for item in files)
        ):
            raise UpdateError("O manifesto não lista os arquivos do programa.")
        normalized_files: set[str] = set()
        for item in files:
            relative = cls._safe_archive_path(item)
            if relative == "update-manifest.json" or relative not in archive_files:
                raise UpdateError("O manifesto aponta para um arquivo ausente.")
            if cls._is_user_path(relative):
                raise UpdateError("O pacote tenta atualizar dados do usuário.")
            if relative in normalized_files:
                raise UpdateError("O manifesto contém arquivos duplicados.")
            normalized_files.add(relative)
        expected_files = archive_files - {"update-manifest.json"}
        if normalized_files != expected_files:
            raise UpdateError("O manifesto não corresponde ao conteúdo do pacote.")

    @staticmethod
    def _safe_archive_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not path.parts
            or normalized.startswith("/")
            or path.is_absolute()
            or "\x00" in normalized
            or ":" in path.parts[0]
        ):
            raise UpdateError("O pacote contém um caminho absoluto inseguro.")
        if any(part in ("", ".", "..") for part in path.parts):
            raise UpdateError("O pacote contém um caminho inseguro.")
        return "/".join(path.parts)

    @staticmethod
    def _is_user_path(relative: str) -> bool:
        parts = PurePosixPath(relative).parts
        first = parts[0].casefold() if parts else ""
        return first in {
            "output",
            "temp",
            "logs",
            "delete",
            ".venv",
        } or relative.casefold().endswith((".log", ".log.txt"))

    @staticmethod
    def _ensure_https(url: str) -> None:
        if urlparse(url).scheme.lower() != "https":
            raise UpdateError("A operação de atualização não permaneceu em HTTPS.")
