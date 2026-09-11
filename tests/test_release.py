"""Behavior checks for the release publishing step without changing GitHub state."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PUBLISH = Path(__file__).resolve().parents[1] / "scripts" / "publish_release.sh"

CURL = """#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then shift; output="$1"; fi
  shift
done
printf '{"message":"test response"}' > "$output"
printf '%s' "$TEST_STATUS"
"""

GH = """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

args = sys.argv[1:]
assets = Path(os.environ["TEST_ASSETS_FILE"])
with open(os.environ["TEST_CALLS"], "a", encoding="utf-8") as calls:
    calls.write(" ".join(args) + "\\n")
names = assets.read_text(encoding="utf-8").splitlines()
if args[:2] == ["release", "view"]:
    print("\\n".join(names))
elif args[:2] in (["release", "upload"], ["release", "create"]):
    if args[1] == "create":
        names = []
    for arg in args:
        if arg.startswith("release-assets/"):
            name = Path(arg).name
            if name != os.environ.get("TEST_DROP") and name not in names:
                names.append(name)
    assets.write_text("".join(name + "\\n" for name in names), encoding="utf-8")
elif args[:2] == ["release", "delete-asset"]:
    names.remove(args[3])
    assets.write_text("".join(name + "\\n" for name in names), encoding="utf-8")
"""


class PublishReleaseTests(unittest.TestCase):
    def publish(self, status: str, existing: list[str], drop: str = ""):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binaries = root / "bin"
            binaries.mkdir()
            packages = root / "release-assets"
            packages.mkdir()
            for name in ("a.tar.gz", "b.zip"):
                (packages / name).write_text("package", encoding="utf-8")
            (root / "release-notes.md").write_text("notes", encoding="utf-8")
            for name, content in (("curl", CURL), ("gh", GH)):
                command = binaries / name
                command.write_text(content, encoding="utf-8")
                command.chmod(0o755)

            asset_file = root / "assets.txt"
            asset_file.write_text(
                "".join(name + "\n" for name in existing), encoding="utf-8"
            )
            calls_file = root / "calls.txt"
            environment = os.environ | {
                "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
                "RUNNER_TEMP": temporary,
                "GITHUB_API_URL": "https://api.github.test",
                "GITHUB_REPOSITORY": "example/repo",
                "GH_TOKEN": "test-token",
                "RELEASE_TAG": "test-tag",
                "RELEASE_TITLE": "Test",
                "TARGET_SHA": "abc",
                "TEST_STATUS": status,
                "TEST_DROP": drop,
                "TEST_ASSETS_FILE": str(asset_file),
                "TEST_CALLS": str(calls_file),
            }
            result = subprocess.run(
                ["bash", str(PUBLISH)],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = (
                calls_file.read_text(encoding="utf-8") if calls_file.exists() else ""
            )
            return result, calls, asset_file.read_text(encoding="utf-8").splitlines()

    def test_existing_release_removes_extra_asset(self) -> None:
        result, calls, assets = self.publish("200", ["a.tar.gz", "b.zip", "extra.txt"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release delete-asset test-tag extra.txt --yes", calls)
        self.assertEqual(sorted(assets), ["a.tar.gz", "b.zip"])

    def test_only_404_creates_release(self) -> None:
        missing, calls, assets = self.publish("404", [])
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("release create test-tag", calls)
        self.assertEqual(sorted(assets), ["a.tar.gz", "b.zip"])

        forbidden, calls, _ = self.publish("403", [])
        self.assertNotEqual(forbidden.returncode, 0)
        self.assertEqual(calls, "")

    def test_missing_uploaded_asset_fails_final_check(self) -> None:
        result, _, _ = self.publish("200", ["a.tar.gz"], drop="b.zip")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected release assets:", result.stderr)


if __name__ == "__main__":
    unittest.main()
