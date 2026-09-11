"""Behavior checks for source archive synchronization."""

import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sync_multiwfn import SyncError, synchronize


class SynchronizeTests(unittest.TestCase):
    def test_update_with_system_temp_on_another_filesystem(self) -> None:
        shared_memory = Path("/dev/shm")
        if not shared_memory.is_dir():
            self.skipTest("requires a separate temporary filesystem")

        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            if root.stat().st_dev == shared_memory.stat().st_dev:
                self.skipTest("temporary filesystems have the same device")

            repo = root / "repo"
            source = repo / "src"
            source.mkdir(parents=True)
            (source / "Multiwfn.f90").write_bytes(b"! Version 2026.9.13\n")
            (source / "obsolete.txt").write_bytes(b"old source file\n")
            manifest = repo / "upstream.json"
            manifest.write_text('{"source_version": "2026.9.13"}\n')

            archive = root / "source.zip"
            updated_source = b"! Version 2026.9.20\n"
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("Multiwfn_source/Multiwfn.f90", updated_source)

            # Reproduce runners whose system temp and checkout use different devices.
            with (
                tempfile.TemporaryDirectory(dir=shared_memory) as system_temp,
                patch("tempfile.tempdir", system_temp),
            ):
                result = synchronize(repo, source_url=archive.as_uri())

            self.assertTrue(result.source_changed)
            self.assertEqual((source / "Multiwfn.f90").read_bytes(), updated_source)
            self.assertFalse((source / "obsolete.txt").exists())
            recorded = json.loads(manifest.read_text())
            self.assertEqual(recorded["source_version"], "2026.9.20")
            self.assertEqual(
                recorded["download_sha256"],
                hashlib.sha256(archive.read_bytes()).hexdigest(),
            )

    def test_corrupt_deflate_preserves_existing_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            repo = root / "repo"
            source = repo / "src"
            (source / "nested").mkdir(parents=True)
            (source / "Multiwfn.f90").write_bytes(b"! Version 2026.9.13\n")
            (source / "nested" / "keep.bin").write_bytes(b"existing source\x00")
            manifest = repo / "upstream.json"
            manifest.write_bytes(
                b'{\n  "source_version": "2026.9.13",\n'
                b'  "download_sha256": "previous"\n}\n'
            )

            original_tree = {
                path.relative_to(source).as_posix(): (
                    path.read_bytes() if path.is_file() else None
                )
                for path in source.rglob("*")
            }
            original_manifest = manifest.read_bytes()

            archive = root / "source.zip"
            member_name = "Multiwfn_source/Multiwfn.f90"
            with zipfile.ZipFile(
                archive, "w", compression=zipfile.ZIP_DEFLATED
            ) as zip_file:
                zip_file.writestr(member_name, "! Version 2026.9.20\n")
                member_offset = zip_file.getinfo(member_name).header_offset

            archive_bytes = bytearray(archive.read_bytes())
            name_length, extra_length = struct.unpack_from(
                "<HH", archive_bytes, member_offset + 26
            )
            compressed_offset = member_offset + 30 + name_length + extra_length
            archive_bytes[compressed_offset] |= 0x06  # Reserved DEFLATE block type.
            archive.write_bytes(archive_bytes)

            with self.assertRaisesRegex(SyncError, "invalid ZIP archive"):
                synchronize(repo, source_url=archive.as_uri())

            self.assertEqual(
                {
                    path.relative_to(source).as_posix(): (
                        path.read_bytes() if path.is_file() else None
                    )
                    for path in source.rglob("*")
                },
                original_tree,
            )
            self.assertEqual(manifest.read_bytes(), original_manifest)


if __name__ == "__main__":
    unittest.main()
