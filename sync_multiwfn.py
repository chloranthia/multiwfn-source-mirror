#!/usr/bin/env python3
"""Synchronize the latest official Multiwfn Linux source archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_SOURCE_URL = "http://sobereva.com/multiwfn/misc/Multiwfn_latest_src_Linux.zip"
DEFAULT_TIMEOUT = 180.0
DEFAULT_MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
SOURCE_VERSION_RE = re.compile(r"\bVersion\s+(\d{4}\.\d{1,2}\.\d{1,2})\b")


class SyncError(RuntimeError):
    """Raised when the upstream archive cannot be safely synchronized."""


@dataclass(frozen=True)
class DownloadInfo:
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SyncResult:
    archive_changed: bool
    source_changed: bool
    manifest_changed: bool
    source_version: str
    archive_size_bytes: int
    download_sha256: str


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a Multiwfn YYYY.M.D version string."""

    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError(f"expected YYYY.M.D version, got {value!r}")
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"invalid version {value!r}") from exc


def download_archive(
    url: str,
    target: Path,
    *,
    timeout: float,
    max_bytes: int,
) -> DownloadInfo:
    """Download an archive while calculating its local byte fingerprint."""

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "multiwfn-source-mirror/1.0 (+https://github.com/)",
        },
    )
    digest = hashlib.sha256()
    size = 0

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise SyncError(
                        f"invalid Content-Length from {url}: {content_length!r}"
                    ) from exc
                if declared_size > max_bytes:
                    raise SyncError(
                        f"archive from {url} is too large: {declared_size} bytes"
                    )

            with target.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise SyncError(f"archive from {url} exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    output.write(chunk)
    except SyncError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SyncError(f"failed to download {url}: {exc}") from exc

    if size == 0:
        raise SyncError(f"downloaded archive from {url} is empty")

    return DownloadInfo(sha256=digest.hexdigest(), size_bytes=size)


def _member_parts(name: str) -> tuple[str, ...]:
    if not name or "\x00" in name:
        raise SyncError(f"invalid archive member name: {name!r}")
    if "\\" in name:
        raise SyncError(f"archive member uses a backslash path: {name!r}")

    path = PurePosixPath(name)
    parts = path.parts
    if (
        path.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise SyncError(f"unsafe archive member path: {name!r}")
    return parts


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def extract_archive(
    archive: Path,
    destination: Path,
    *,
    max_extracted_bytes: int = DEFAULT_MAX_EXTRACTED_BYTES,
) -> str:
    """Validate and extract a single-root source archive."""

    destination.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive) as zip_file:
            infos = zip_file.infolist()
            if not infos:
                raise SyncError("archive is empty")

            all_parts = [_member_parts(info.filename) for info in infos]
            top_levels = {parts[0] for parts in all_parts}
            if len(top_levels) != 1:
                raise SyncError(
                    "expected one top-level archive directory, found: "
                    + ", ".join(sorted(top_levels))
                )
            top_level = next(iter(top_levels))

            imported_files: set[str] = set()
            entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
            declared_size = 0
            for info, parts in zip(infos, all_parts, strict=True):
                if _is_symlink(info):
                    raise SyncError(f"symbolic links are not allowed: {info.filename}")
                if info.is_dir() or info.filename.endswith("/"):
                    continue
                if parts[0] != top_level or len(parts) == 1:
                    raise SyncError(f"invalid archive member path: {info.filename!r}")

                relative = PurePosixPath(*parts[1:]).as_posix()
                if relative in imported_files:
                    raise SyncError(f"duplicate archive member path: {relative}")
                imported_files.add(relative)
                declared_size += info.file_size
                if declared_size > max_extracted_bytes:
                    raise SyncError(
                        "archive expands beyond the maximum allowed size: "
                        f"{max_extracted_bytes} bytes"
                    )
                entries.append((info, parts))

            for info, parts in entries:
                target = destination.joinpath(*parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

    except (zipfile.BadZipFile, zlib.error, RuntimeError) as exc:
        raise SyncError(f"invalid ZIP archive: {exc}") from exc

    source_file = destination / "Multiwfn.f90"
    if not source_file.is_file():
        raise SyncError("archive does not contain Multiwfn.f90")

    source_text = source_file.read_text(encoding="utf-8", errors="replace")
    match = SOURCE_VERSION_RE.search(source_text)
    if match is None:
        raise SyncError("Multiwfn.f90 does not contain a Version YYYY.M.D line")
    return match.group(1)


def directory_digest(directory: Path) -> str:
    """Hash relative file names and bytes in a deterministic order."""

    digest = hashlib.sha256()
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    for path in files:
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def directories_equal(left: Path, right: Path) -> bool:
    if not left.is_dir() or not right.is_dir():
        return False
    if any(
        path.is_symlink()
        for directory in (left, right)
        for path in directory.rglob("*")
    ):
        return False
    return directory_digest(left) == directory_digest(right)


def load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SyncError(f"manifest {path} must contain a JSON object")
    return value


def replace_directory(current: Path, replacement: Path) -> None:
    """Replace a managed directory while keeping a rollback path on failure."""

    current.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if current.exists() or current.is_symlink():
        if current.is_symlink() or not current.is_dir():
            raise SyncError(f"managed source path is not a directory: {current}")
        backup = Path(
            tempfile.mkdtemp(prefix=f".{current.name}.backup-", dir=current.parent)
        )
        backup.rmdir()
        current.rename(backup)

    try:
        replacement.rename(current)
    except OSError:
        if backup is not None and not current.exists():
            backup.rename(current)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup)


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def synchronize(
    repo_root: Path,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    timeout: float = DEFAULT_TIMEOUT,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> SyncResult:
    """Synchronize one upstream archive into a repository checkout."""

    repo_root = repo_root.resolve()
    source_path = repo_root / "src"
    manifest_file = repo_root / "upstream.json"
    manifest = load_manifest(manifest_file)

    # Keep staged sources on the checkout's filesystem for the rename-based swap.
    with tempfile.TemporaryDirectory(
        prefix="multiwfn-source-mirror.", dir=repo_root
    ) as temporary_dir:
        temporary_root = Path(temporary_dir)
        archive_path = temporary_root / "source.zip"
        download = download_archive(
            source_url,
            archive_path,
            timeout=timeout,
            max_bytes=max_archive_bytes,
        )

        previous_hash = manifest.get("download_sha256") if manifest else None
        archive_changed = previous_hash != download.sha256

        staged_source = temporary_root / "src"
        source_version = extract_archive(archive_path, staged_source)

        previous_version = manifest.get("source_version") if manifest else None
        if isinstance(previous_version, str) and previous_version:
            try:
                if parse_version(source_version) < parse_version(previous_version):
                    raise SyncError(
                        f"upstream version moved backwards from "
                        f"{previous_version} to {source_version}"
                    )
            except ValueError as exc:
                raise SyncError(f"invalid version in existing manifest: {exc}") from exc

        source_changed = not directories_equal(source_path, staged_source)
        new_manifest: dict[str, Any] = {
            "source_url": source_url,
            "source_version": source_version,
            "archive_size_bytes": download.size_bytes,
            "download_sha256": download.sha256,
        }
        manifest_changed = manifest != new_manifest

        if source_changed:
            replace_directory(source_path, staged_source)
        if manifest_changed:
            write_manifest(manifest_file, new_manifest)

        return SyncResult(
            archive_changed=archive_changed,
            source_changed=source_changed,
            manifest_changed=manifest_changed,
            source_version=source_version,
            archive_size_bytes=download.size_bytes,
            download_sha256=download.sha256,
        )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        result = synchronize(
            Path(__file__).resolve().parent,
        )
    except (OSError, SyncError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
