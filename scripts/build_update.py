"""Gera o ZIP e o checksum esperados pelo updater do Tuberino Downloader."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from posixpath import normpath

from app.updates.service import parse_version

PACKAGE_ID = "tuberino-downloader-windows-x64"
SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "output",
    "temp",
    "delete",
    "docs",
    "logs",
    "releases",
    "build",
    "dist",
}
SKIP_FILES = {"AGENTS.md", ".gitignore", "update-manifest.json"}


def build_update(source: Path, version: str, output: Path) -> tuple[Path, Path]:
    source = source.resolve()
    version_text = ".".join(str(value) for value in parse_version(version))
    output.mkdir(parents=True, exist_ok=True)
    files = _source_files(source)
    manifest = {
        "format": 1,
        "version": version_text,
        "package_id": PACKAGE_ID,
        "files": files,
    }
    archive_path = output / f"{PACKAGE_ID}.zip"
    checksum_path = output / f"{PACKAGE_ID}.sha256"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        archive.writestr("update-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if (source / "Output").is_dir():
            archive.writestr("Output/", b"")
        for relative in files:
            archive.write(source / Path(relative), relative)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, checksum_path


def _source_files(source: Path) -> list[str]:
    files: list[str] = []
    for path in source.rglob("*"):
        if not path.is_file() or _skip_path(path, source):
            continue
        relative = normpath(path.relative_to(source).as_posix())
        if relative not in files:
            files.append(relative)
    if not files:
        raise ValueError("A pasta de distribuição não contém arquivos.")
    return sorted(files)


def _skip_path(path: Path, source: Path) -> bool:
    relative_parts = path.relative_to(source).parts
    if any(part.casefold() in SKIP_DIRECTORIES for part in relative_parts[:-1]):
        return True
    if path.name in SKIP_FILES or path.suffix.casefold() in {".part", ".log"}:
        return True
    return path.name.casefold().endswith(".log.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive, checksum = build_update(args.source, args.version, args.output)
    print(f"Created: {archive}")
    print(f"Created: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
