#!/usr/bin/env python3
"""Validate the build metadata shipped with a no-GUI artifact."""

import sys
from pathlib import Path

REQUIRED_KEYS = {
    "source_revision",
    "fortran_compiler",
    "c_compiler",
    "cmake_version",
    "build_type",
    "blas_vendor",
    "blas_libraries",
    "lapack_libraries",
    "openmp_requested",
    "openmp_enabled",
    "fractional_derivatives",
    "gnu_opt_level",
    "gnu_hot_opt_level",
    "gnu_extra_flags",
}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} METADATA")

    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"metadata file does not exist: {path}")

    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        key, separator, value = line.partition("=")
        if not separator:
            raise SystemExit(f"metadata line is not key/value data: {line!r}")
        entries[key] = value

    missing = sorted(REQUIRED_KEYS - entries.keys())
    if missing:
        raise SystemExit(f"metadata is missing keys: {', '.join(missing)}")
    if not entries["source_revision"]:
        raise SystemExit("metadata source_revision is empty")
    if entries["openmp_enabled"] not in {"ON", "OFF"}:
        raise SystemExit("metadata openmp_enabled must be ON or OFF")
    if entries["fractional_derivatives"] not in {"ON", "OFF"}:
        raise SystemExit("metadata fractional_derivatives must be ON or OFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
