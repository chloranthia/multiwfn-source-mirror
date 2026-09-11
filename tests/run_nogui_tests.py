#!/usr/bin/env python3
"""Small, platform-neutral functional smoke tests for Multiwfn_noGUI."""

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

FLOAT_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"


def assert_contains(path: Path, text: str) -> None:
    content = path.read_text(encoding="utf-8", errors="replace")
    if text not in content:
        tail = "\n".join(content.splitlines()[-80:])
        raise AssertionError(f"{path} does not contain {text!r}\n--- tail ---\n{tail}")


def assert_matches(path: Path, pattern: str, description: str) -> Any:
    content = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(pattern, content, flags=re.MULTILINE)
    if match is None:
        tail = "\n".join(content.splitlines()[-80:])
        raise AssertionError(
            f"{path} does not contain {description}\n--- tail ---\n{tail}"
        )
    return match


def assert_number(
    path: Path,
    pattern: str,
    expected: float,
    description: str,
    tolerance: float = 5e-6,
) -> None:
    match = assert_matches(path, pattern, f"a numeric value for {description}")
    value = float(match.group(1))
    if not math.isclose(value, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise AssertionError(
            f"{description} was {value}, expected {expected} ± {tolerance}"
        )


def run_case(
    executable: Path,
    settings: Path,
    workdir: Path,
    input_name: str,
    commands: str,
    output_name: Optional[str],  # noqa: UP045 -- Rocky 8 uses Python 3.6.
) -> Path:
    case_dir = workdir / input_name.rsplit(".", 1)[0]
    case_dir.mkdir()
    shutil.copy2(settings, case_dir / "settings.ini")
    source_path = workdir / input_name
    if not source_path.is_file():
        raise AssertionError(f"Input fixture does not exist: {source_path}")
    input_path = case_dir / input_name
    shutil.copy2(source_path, input_path)
    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_STACKSIZE": "64M",
            "KMP_STACKSIZE": "64M",
        }
    )
    result = subprocess.run(  # noqa: UP022
        [str(executable), str(input_path)],
        input=commands,
        encoding="utf-8",
        errors="replace",
        cwd=case_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
        check=False,
    )
    (case_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (case_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise AssertionError(
            f"{executable.name} exited with {result.returncode} for {input_name}\n"
            f"stdout:\n{result.stdout[-4000:]}\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )
    if output_name is not None:
        output_path = case_dir / output_name
        if not output_path.exists():
            raise AssertionError(f"Expected output was not created: {output_path}")
    return case_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "settings.ini",
    )
    args = parser.parse_args()

    executable = args.executable.resolve()
    settings = args.settings.resolve()
    if not executable.is_file():
        raise SystemExit(f"Executable does not exist: {executable}")
    if not settings.is_file():
        raise SystemExit(f"settings.ini does not exist: {settings}")

    with tempfile.TemporaryDirectory(prefix="multiwfn-nogui-test-") as temporary:
        workdir = Path(temporary)
        water = workdir / "water.xyz"
        water.write_text(
            "3\nwater\nO 0 0 0\nH 0 0 0.96\nH 0.92 0 -0.24\n",
            encoding="ascii",
        )
        geometry_dir = run_case(
            executable,
            settings,
            workdir,
            "water.xyz",
            "26\n1\n\nq\n0\nq\n",
            None,
        )
        assert_contains(geometry_dir / "stdout.log", "water.xyz successfully!")
        assert_contains(geometry_dir / "stdout.log", "Formula: H2 O1")
        assert_number(
            geometry_dir / "stdout.log",
            rf"Mass of these atoms:\s*({FLOAT_PATTERN})\s*amu",
            18.015286,
            "water mass",
        )
        geometry_output = geometry_dir / "stdout.log"
        geometry_center = rf"Geometry center \(X/Y/Z\):\s*({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\s+Angstrom"
        center_match = assert_matches(
            geometry_output, geometry_center, "the geometry center"
        )
        center = tuple(float(value) for value in center_match.groups())
        expected_center = (0.30666667, 0.0, 0.24)
        if any(
            not math.isclose(value, expected, rel_tol=5e-6, abs_tol=5e-6)
            for value, expected in zip(center, expected_center)
        ):
            raise AssertionError(
                f"geometry center was {center}, expected {expected_center}"
            )
        assert_number(
            geometry_output,
            rf"Maximum distance is\s+({FLOAT_PATTERN})\s+Angstrom",
            1.512085,
            "maximum distance",
        )
        assert_number(
            geometry_output,
            rf"Minimum distance is\s+({FLOAT_PATTERN})\s+Angstrom",
            0.950789,
            "minimum distance",
        )

        geomparm_water = workdir / "water_geomparm.xyz"
        geomparm_water.write_text(water.read_text(encoding="ascii"), encoding="ascii")
        geomparm_dir = run_case(
            executable,
            settings,
            workdir,
            "water_geomparm.xyz",
            "geomparm\ngeomparm.txt\nq\n",
            "geomparm.txt",
        )
        geomparm_output = geomparm_dir / "geomparm.txt"
        assert_contains(geomparm_output, "Number of bonds:")
        assert_number(
            geomparm_output,
            rf"Atoms:\s+1\s+2\s+Distance:\s*({FLOAT_PATTERN})\s+Angstrom",
            0.96,
            "first exported bond distance",
        )
        assert_number(
            geomparm_output,
            rf"Angle:\s*({FLOAT_PATTERN})\s+degree",
            104.620872,
            "exported bond angle",
        )

        cube = workdir / "tiny.cub"
        cube.write_text(
            """Test cube
Generated for Multiwfn CI
    1    0.000000    0.000000    0.000000
    2    1.000000    0.000000    0.000000
    2    0.000000    1.000000    0.000000
    2    0.000000    0.000000    1.000000
    8    0.000000    0.000000    0.000000    0.000000
  1.000000E-01  2.000000E-01  3.000000E-01  4.000000E-01  5.000000E-01  6.000000E-01
  7.000000E-01  8.000000E-01
""",
            encoding="ascii",
        )
        cube_dir = run_case(
            executable,
            settings,
            workdir,
            "tiny.cub",
            "13\n0\nroundtrip.cub\n-1\nq\n",
            "roundtrip.cub",
        )
        assert_number(
            cube_dir / "stdout.log",
            r"Total number of grid points:\s*([0-9]+)",
            8,
            "cube grid-point count",
            tolerance=0,
        )
        assert_number(
            cube_dir / "stdout.log",
            rf"Global minimum value:\s*({FLOAT_PATTERN})",
            0.1,
            "cube global minimum",
        )
        assert_number(
            cube_dir / "stdout.log",
            rf"Global maximum value:\s*({FLOAT_PATTERN})",
            0.8,
            "cube global maximum",
        )
        roundtrip = cube_dir / "roundtrip.cub"
        lines = roundtrip.read_text(encoding="ascii").splitlines()
        try:
            atom_count = abs(int(lines[2].split()[0]))
            dimensions = tuple(int(lines[index].split()[0]) for index in (3, 4, 5))
            values = [
                float(value)
                for line in lines[6 + atom_count :]
                for value in line.split()
            ]
        except (IndexError, ValueError) as error:
            raise AssertionError(
                f"Invalid cube output: {roundtrip}: {error}"
            ) from error
        if dimensions != (2, 2, 2):
            raise AssertionError(
                f"cube grid dimensions were {dimensions}, expected (2, 2, 2)"
            )
        if len(values) != 8:
            raise AssertionError(
                f"cube grid contained {len(values)} values, expected 8"
            )
        for actual, expected in zip(values, (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)):
            if not math.isclose(actual, expected, rel_tol=5e-6, abs_tol=5e-6):
                raise AssertionError(
                    f"cube grid value was {actual}, expected {expected}"
                )

    print("Multiwfn noGUI functional tests passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
